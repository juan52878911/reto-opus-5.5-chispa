"""G.8: shrinkage de los prototipos, reparto por tarea del meta, --max-tok y --excluir-fuera en el entrenamiento."""
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch
import torch.nn.functional as F

from model.l2 import datos as D
from model.l2 import entrenar
from model.l2.modelo import ModeloL2, SoporteEval, mezcla_prototipos, prototipos, texto_opcion
from model.l2.tests.falso import CodificadorFalso, fila
from model.meta import muestreo


def tarea(nombre, n, vias=3, tipo="choice"):
    return [fila(i, tipo, vias, nombre) for i in range(n)]


def coseno_medio(a, b):
    return float((a * b).sum(-1).mean())


class Shrinkage(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(0)
        self.m, self.enc = ModeloL2().eval(), CodificadorFalso()

    def descripcion(self, sop, idx):
        with torch.no_grad():
            return self.m.torre(self.enc.pasaje([texto_opcion(sop[0], e) for e in sorted(idx)]))

    def test_kappa_cero_es_lo_de_hoy(self):
        sop = tarea("a", 12)
        i0, P0 = prototipos(self.m, self.enc, sop)
        i1, P1 = prototipos(self.m, self.enc, sop, kappa=0.0)
        self.assertEqual(i0, i1)
        self.assertTrue(torch.equal(P0, P1))
        C = len(i0)
        S = torch.cat([self.m.ranuras(*[x for x in self.enc.tokens([r["texto"]])]) for r in sop])
        suma = torch.zeros(C, *S.shape[1:]).index_add(0, torch.tensor([i0[r["etiqueta"]] for r in sop]), S)
        self.assertTrue(torch.allclose(P0, F.normalize(suma, dim=-1), atol=1e-5))

    def test_un_ejemplo_queda_cerca_de_la_descripcion(self):
        sop = [r for r in tarea("a", 30) if r["id"].endswith(("0", "1", "2"))][:3]   # un ejemplo por clase
        sop = [fila(i, "choice", 3, "a") for i in range(3)]
        idx, P = prototipos(self.m, self.enc, sop, kappa=100.0)    # λ ≈ 0,99
        h = self.descripcion(sop, idx)
        self.assertTrue(torch.allclose(P.norm(dim=-1), torch.ones(3, P.shape[1]), atol=1e-5))
        self.assertGreater(coseno_medio(P, h.unsqueeze(1).expand_as(P)), 0.98)
        _, P0 = prototipos(self.m, self.enc, sop)
        self.assertLess(coseno_medio(P0, h.unsqueeze(1).expand_as(P0)), 0.5)   # sin shrinkage, la descripción no pesa

    def test_con_muchos_ejemplos_queda_cerca_de_la_media(self):
        sop = tarea("a", 600)   # 200 por clase
        _, P0 = prototipos(self.m, self.enc, sop)
        _, Pk = prototipos(self.m, self.enc, sop, kappa=4.0)     # λ = 4/204 ≈ 0,02
        self.assertGreater(coseno_medio(Pk, P0), 0.99)

    def test_lambda_decrece_con_n(self):
        h = F.normalize(torch.randn(2, 256), dim=-1)
        suma = torch.zeros(2, 4, 256)
        suma[:] = F.normalize(torch.ones(4, 256), dim=-1)
        suma = suma.clone()
        P = mezcla_prototipos(suma * torch.tensor([1.0, 100.0]).view(-1, 1, 1), torch.tensor([1.0, 100.0]), h, 4.0)
        media = F.normalize(torch.ones(4, 256), dim=-1)
        c = lambda i: coseno_medio(P[i], media)
        self.assertLess(c(0), c(1))
        d = lambda i: coseno_medio(P[i], h[i].expand(4, 256))
        self.assertGreater(d(0), d(1))

    def test_soporte_eval_y_cache_distinguen_kappa(self):
        tr = {"a": tarea("a", 30)}
        s0, s1 = SoporteEval(tr, k=2), SoporteEval(tr, k=2, kappa=4.0)
        p0 = s0.protos(self.m, self.enc, {"a"})["a"][1]
        p1 = s1.protos(self.m, self.enc, {"a"})["a"][1]
        self.assertFalse(torch.allclose(p0, p1))
        self.assertEqual(s1.cache.calculos, 1)


def escribir_meta(raiz, fuentes):
    """fuentes: {fuente: [(tarea, n)]} -> <raiz>/<fuente>/train-00000.jsonl.gz"""
    for fuente, tareas in fuentes.items():
        d = Path(raiz) / fuente
        d.mkdir(parents=True)
        with gzip.open(d / "train-00000.jsonl.gz", "wt", encoding="utf-8") as f:
            for t, n in tareas:
                for i in range(n):
                    r = fila(i, "choice", 3, t)
                    r["id"] = "%s:train:%s-%d" % (fuente, t, i)
                    f.write(json.dumps(r) + "\n")


class RepartoPorTarea(unittest.TestCase):
    def test_tope_por_tarea_y_fuera(self):
        fuera = next("demo/%d" % i for i in range(1000) if muestreo.tarea_fuera("demo/%d" % i))
        with tempfile.TemporaryDirectory() as d:
            escribir_meta(d, {"tsjev": [("grande", 500), ("chica", 20), (fuera, 50)], "synzs": [("sint", 300)]})
            filas, cuentas, cupo, quit_ = D.submuestrear_meta_tareas(d, 10_000, tope_tarea=100, fuera=muestreo.es_fuera)
            por = {}
            for r in filas:
                por[r["tarea"]] = por.get(r["tarea"], 0) + 1
            self.assertEqual(por, {"grande": 100, "chica": 20, "sint": 100})     # synzs no es de tasksource: nunca «fuera»
            self.assertEqual(quit_, {"filas": 50, "tareas": 1})
            self.assertNotIn(fuera, cuentas)
            # el tope baja si el total no cabe, y la elección es estable
            f2, _, c2, _ = D.submuestrear_meta_tareas(d, 100, tope_tarea=100, fuera=muestreo.es_fuera)
            self.assertLessEqual(len(f2), 100)
            self.assertEqual(c2["chica"], 20)
            self.assertEqual(f2, D.submuestrear_meta_tareas(d, 100, tope_tarea=100, fuera=muestreo.es_fuera)[0])

    def test_alfa_03_reparte_mas_parejo_que_05(self):
        filas = tarea("g", 1000) + tarea("p", 10)
        m3, m5 = D.Muestreador(filas, alfa=0.3), D.Muestreador(filas, alfa=0.5)
        self.assertGreater(m3.p[m3.tareas.index("p")], m5.p[m5.tareas.index("p")])


class Evaluacion(unittest.TestCase):
    def test_filas_fuera_solo_dev_test_de_tareas_fuera(self):
        from model.l2.evaluar import filas_fuera
        fuera = next("demo/%d" % i for i in range(1000) if muestreo.tarea_fuera("demo/%d" % i))
        dentro = next("demo/%d" % i for i in range(1000) if not muestreo.tarea_fuera("demo/%d" % i))
        with tempfile.TemporaryDirectory() as d:
            for tarea_, split in ((fuera, "dev"), (fuera, "test"), (fuera, "train"), (dentro, "dev")):
                (Path(d) / tarea_.replace("/", "_")).mkdir(exist_ok=True)
                with gzip.open(Path(d) / tarea_.replace("/", "_") / (split + "-0.jsonl.gz"), "at", encoding="utf-8") as f:
                    for i in range(10):
                        r = fila(i, "choice", 3, tarea_)
                        r.update(id="tsjev:%s:%s-%d" % (split, tarea_.replace("/", "_"), i), split=split)
                        f.write(json.dumps(r) + "\n")
            out = filas_fuera(d, por_tarea=7)
        self.assertEqual(len(out), 7)
        self.assertEqual({r["tarea"] for r in out}, {fuera})
        self.assertTrue(all(r["split"] in ("dev", "test") for r in out))


class Comparador(unittest.TestCase):
    def test_sin_datos_no_se_da_por_cumplido(self):
        import importlib.util
        ruta = Path(__file__).resolve().parents[2] / "evaluacion" / "aws" / "comparar_g8.py"
        spec = importlib.util.spec_from_file_location("comparar_g8", ruta)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with tempfile.TemporaryDirectory() as d:
            t = mod.comparar(d, d, 4.0, {"massive"})
        self.assertIn("sin datos", t)
        self.assertNotIn("se cumple", t)


class Entrenamiento(unittest.TestCase):
    def test_flags_de_g8_de_punta_a_punta(self):
        fuera = next("demo/%d" % i for i in range(1000) if muestreo.tarea_fuera("demo/%d" % i))
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            escribir_meta(d / "meta", {"tsjev": [("uno", 40), ("dos", 40), (fuera, 40)]})
            with open(d / "d.jsonl", "w") as f:
                for r in tarea("a", 30) + tarea("massive", 20):
                    f.write(json.dumps(r) + "\n")
            enc = CodificadorFalso()
            capturado = {}

            def falso(**kw):
                capturado.update(kw)
                return enc
            with mock.patch.object(entrenar, "Codificador", falso):
                rc = entrenar.main(["--salida", str(d / "s"), "--datos", str(d / "d.jsonl"), "--meta", str(d / "meta"), "--pasos", "4",
                                    "--lote", "8", "--device", "cpu", "--ckpt-cada", "0", "--tope-tarea", "25", "--alfa", "0.3",
                                    "--max-tok", "256", "--excluir-fuera", "--excluir-tareas", "massive", "--episodios",
                                    "--elegir-kappa", "2", "4"])
            self.assertEqual(rc, 0)
            self.assertEqual(capturado["max_tok"], 256)
            ent = json.loads((d / "s" / "entrenamiento.json").read_text())
            meta = ent["info"]["meta"]
            self.assertEqual((meta["tareas"], meta["elegidas"], meta["fuera"]["tareas"]), (2, 50, 1))
            self.assertEqual(meta["tareas_fuera"], [fuera])
            self.assertIn(ent["kappa_dev"] and ent["kappa_dev"]["kappa"], [0.0, 2.0, 4.0, None])
            ck = torch.load(d / "s" / "mejor.pt", weights_only=False)
            self.assertEqual(ck["max_tok"], enc.max_tok)

    def test_elegir_kappa_devuelve_uno_de_la_rejilla(self):
        torch.manual_seed(0)
        filas = tarea("a", 40)
        a = mock.Mock(elegir_kappa=[2.0, 8.0], semilla=0)
        r = entrenar.elegir_kappa(ModeloL2().eval(), CodificadorFalso(), filas[:20], filas, a)
        self.assertEqual(set(r["rejilla"]), {"0.0", "2.0", "8.0"})
        self.assertIn(r["kappa"], (0.0, 2.0, 8.0))
        self.assertIn(r["kappa_pos"], (2.0, 8.0))
        self.assertEqual(r["rejilla"][str(r["kappa"])], max(r["rejilla"].values()))


if __name__ == "__main__":
    unittest.main()
