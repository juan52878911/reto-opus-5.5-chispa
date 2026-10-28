import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

from model.l2 import datos as D
from model.l2 import entrenar
from model.l2.modelo import K_RANURAS, CachePrototipos, ModeloL2, SoporteEval, prototipos, simproto
from model.l2.tests.falso import CodificadorFalso, fila


def tarea(nombre, n=60, vias=4, tipo="choice"):
    return [fila(i, tipo, vias, nombre) for i in range(n)]


class Prototipo(unittest.TestCase):
    def test_forma_y_normalizacion(self):
        torch.manual_seed(0)
        m, enc = ModeloL2(), CodificadorFalso()
        sop = tarea("a", 20)
        idx, P = prototipos(m, enc, sop)
        self.assertEqual(idx, {"op0": 0, "op1": 1, "op2": 2, "op3": 3})
        self.assertEqual(tuple(P.shape), (4, K_RANURAS, 256))
        self.assertTrue(torch.allclose(P.norm(dim=-1), torch.ones(4, K_RANURAS), atol=1e-5))
        S = torch.nn.functional.normalize(torch.randn(3, K_RANURAS, 256), dim=-1)
        self.assertEqual(tuple(simproto(S, P).shape), (3, 4))

    def test_beta_cero_reproduce_la_ronda_1(self):
        torch.manual_seed(0)
        m, enc = ModeloL2().eval(), CodificadorFalso()
        filas = tarea("a", 8) + tarea("b", 6, tipo="noul") + [fila(i, "score", tarea="c", k=4) for i in range(6)]
        protos = {t: prototipos(m, enc, [r for r in tarea(t, 40, 2 if t == "b" else 4, "noul" if t == "b" else "choice")]) for t in "ab"}
        protos["c"] = prototipos(m, enc, [fila(i, "score", tarea="c", k=4) for i in range(40)])
        sin, _ = m(filas, enc, entrenar=False)
        con, _ = m(filas, enc, entrenar=False, protos=protos)
        self.assertTrue(any(not torch.allclose(a, b, atol=1e-6) for a, b in zip(sin, con)))  # β = 1: el soporte cambia algo
        for k in m.beta:
            m.beta[k].data.zero_()
        cero, _ = m(filas, enc, entrenar=False, protos=protos)
        for a, b in zip(sin, cero):
            self.assertTrue(torch.allclose(a, b, atol=1e-7))

    def test_checkpoint_sin_beta_carga(self):
        m = ModeloL2()
        viejo = {k: v for k, v in m.state_dict().items() if not k.startswith("beta.")}
        ModeloL2().load_state_dict(viejo)

    def test_renombrado_usa_los_prototipos_originales(self):
        torch.manual_seed(0)
        m, enc = ModeloL2().eval(), CodificadorFalso()
        protos = {"a": prototipos(m, enc, tarea("a", 40))}
        r = tarea("a", 4)
        o, _ = m(r, enc, entrenar=False, protos=protos)
        n, _ = m([D.renombrar_fila(x) for x in r], enc, entrenar=False, protos=protos)
        self.assertEqual(D.renombrar_fila(r[0])["origen"], r[0]["opciones"])
        self.assertTrue(torch.isfinite(torch.stack(n)).all())
        sp_o = m._simproto(torch.randn(4, K_RANURAS, 256), r, protos)
        sp_n = m._simproto(torch.randn(4, K_RANURAS, 256), [D.renombrar_fila(x) for x in r], protos)
        self.assertEqual(sp_o[0].shape, sp_n[0].shape)
        self.assertTrue(all((x != 0).any() for x in sp_n))  # no se pierde el soporte al renombrar


class EpisodiosTest(unittest.TestCase):
    def setUp(self):
        self.locales = tarea("a", 80, 4) + tarea("b", 200, 30) + tarea("c", 40, 2, "noul")
        self.meta = [fila(i, tarea="m%d" % (i % 3)) for i in range(100)]

    def test_sin_fuga_y_k_en_rango(self):
        ep = D.Episodios(self.locales, self.meta, lote=16, k_min=4, k_max=8, vias=5, semilla=3)
        n_ep = 0
        for p in range(200):
            e = ep.paso(p)
            if e["soporte"] is None:
                continue
            n_ep += 1
            ids = {r["id"] for r in e["soporte"]}
            self.assertFalse(ids & {r["id"] for r in e["filas"]})
            self.assertEqual({r["tarea"] for r in e["filas"] + e["soporte"]}, {e["tarea"]})
            por = {}
            for r in e["soporte"]:
                por[r["etiqueta"]] = por.get(r["etiqueta"], 0) + 1
            self.assertTrue(4 <= max(por.values()) <= 8 and min(por.values()) >= 1)
            if e["tarea"] == "b":  # 30 clases → 5 vías: las consultas solo ven esas opciones
                self.assertEqual(len(por), 5)
                for r in e["filas"]:
                    self.assertEqual(set(r["opciones"]), set(por))
                    self.assertIn(r["etiqueta"], r["opciones"])
        self.assertGreater(n_ep, 120)

    def test_mezcla_y_determinismo(self):
        ep = D.Episodios(self.locales, self.meta, lote=8, semilla=1)
        pasos = [ep.paso(p) for p in range(400)]
        sin = [e for e in pasos if e["soporte"] is None]
        self.assertAlmostEqual(len(sin) / 400, 0.25, delta=0.06)
        self.assertTrue(all(e["meta"] for e in sin))  # frac_meta 0.5 ≥ frac_zeroshot: todo el zero-shot sale de meta
        self.assertTrue(all(r["tarea"].startswith("m") for e in sin for r in e["filas"]))
        self.assertGreaterEqual(1 - sum(e["meta"] for e in pasos) / 400, 0.5)
        self.assertEqual([r["id"] for r in ep.paso(9)["filas"]], [r["id"] for r in ep.paso(9)["filas"]])
        tope = D.Episodios(self.locales, self.meta, lote=8, frac_meta=0.1, frac_zeroshot=0.4, semilla=1)
        self.assertLess(sum(tope.paso(p)["meta"] for p in range(400)) / 400, 0.2)

    def test_soporte_igual_que_kNN32(self):
        from model.lineas_base import correr
        train = tarea("a", 200, 5)
        self.assertEqual([(i, r["id"]) for i, r in D.soporte_t17a(train)], [(i, r["id"]) for i, r in correr.soporte(train)])


class CacheTest(unittest.TestCase):
    def test_se_calcula_una_vez_por_tarea_y_hash(self):
        torch.manual_seed(0)
        m, enc = ModeloL2().eval(), CodificadorFalso()
        sop = SoporteEval({"a": tarea("a", 60), "b": tarea("b", 60, 3)}, k=5)
        filas = tarea("a", 10) + tarea("b", 10, 3)
        with mock.patch("model.l2.modelo.prototipos", wraps=prototipos) as espia:
            p1 = sop.protos(m, enc, {"a", "b"})
            p2 = sop.protos(m, enc, {"a"})
            self.assertEqual(espia.call_count, 2)
            self.assertIs(p1["a"], p2["a"])
            self.assertEqual(sop.cache.calculos, 2)
            sop.cache.limpiar()
            sop.protos(m, enc, {"a"})
            self.assertEqual(espia.call_count, 3)
        self.assertEqual(len(sop.filas["a"]), 4 * 5)
        c = CachePrototipos()
        a, b = tarea("z", 20), tarea("z", 20)[:-2]
        with torch.no_grad():
            c.obtener(m, enc, "z", a); c.obtener(m, enc, "z", list(a)); c.obtener(m, enc, "z", b)
        self.assertEqual(c.calculos, 2)  # otro soporte → otro hash


class EntrenarEpisodios(unittest.TestCase):
    def test_entrena_y_evalua_con_soporte(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            with open(t / "d.jsonl", "w") as f:
                for r in tarea("a", 60) + tarea("b", 40, 2, "noul") + [fila(i, "score", tarea="c", k=4) for i in range(40)]:
                    f.write(json.dumps(r) + "\n")
                for r in tarea("a", 12):
                    r = dict(r, id=r["id"].replace("train", "dev"), split="dev")
                    f.write(json.dumps(r) + "\n")
            enc = CodificadorFalso()
            with mock.patch.object(entrenar, "Codificador", lambda **kw: enc):
                rc = entrenar.main(["--salida", str(t / "s"), "--datos", str(t / "d.jsonl"), "--pasos", "6", "--lote", "8", "--device", "cpu",
                                    "--episodios", "--k-max", "6", "--eval-cada", "3", "--renombrar", "0.5"])
            self.assertEqual(rc, 0)
            ck = torch.load(t / "s" / "ultimo.pt", weights_only=False)
            self.assertEqual(ck["paso"], 6)
            self.assertIn("beta.choice", ck["modelo"])


if __name__ == "__main__":
    unittest.main()
