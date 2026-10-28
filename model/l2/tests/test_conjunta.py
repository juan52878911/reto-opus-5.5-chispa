import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import torch

from model.l2 import conjunta as C
from model.l2.modelo import ModeloL2, prototipos
from model.l2.tests.falso import CodificadorFalso, fila


def tarea(n_train=40, n_test=12, n_ops=4):
    train = [fila(i, n=n_ops) for i in range(n_train)]
    test = [dict(fila(1000 + i, n=n_ops), id="f:test:%d" % i, split="test") for i in range(n_test)]
    return train, test


class SinFuga(unittest.TestCase):
    def test_pliegues_particionan(self):
        train, _ = tarea(53)
        f = C.pliegues(train, 5)
        self.assertEqual(len(f), 53)
        self.assertEqual(set(f), set(range(5)))
        # cada clase se reparte: ningún pliegue se queda sin una clase que tiene ≥ 5 filas
        for c in {r["etiqueta"] for r in train}:
            self.assertEqual({f[i] for i, r in enumerate(train) if r["etiqueta"] == c}, set(range(5)))

    def test_l0_nunca_predice_una_fila_que_vio(self):
        train, _ = tarea(53)
        fold = C.pliegues(train, 5)
        vistas = []

        def falso(entrenar, objetivo):
            ids_e, ids_o = {r["id"] for r in entrenar}, [r["id"] for r in objetivo]
            self.assertFalse(ids_e & set(ids_o))
            vistas.extend(ids_o)
            return np.full((len(objetivo), 4), 0.25), np.zeros(len(objetivo))
        with mock.patch.object(C, "probs_l0", falso):
            C.l0_fuera_de_pliegue(train, fold, 5)
        self.assertEqual(sorted(vistas), sorted(r["id"] for r in train))  # cada fila se predice una vez, en su pliegue

    def test_l2_soporte_sin_la_propia_fila(self):
        train, _ = tarea(40)
        torch.manual_seed(0)
        modelo, enc = ModeloL2().eval(), CodificadorFalso()
        sop = [r for _, r in C.D.soporte_t17a(train, 3)]
        ps = C.ProtosSinPropia(modelo, enc, sop)
        # completos == modelo.prototipos
        idx, P = ps.completos()
        idx2, P2 = prototipos(modelo, enc, sop)
        self.assertEqual(idx, idx2)
        self.assertTrue(torch.allclose(P, P2, atol=1e-5))
        for r in sop:
            idx_s, P_s = ps.sin(r["id"])
            resto = [x for x in sop if x["id"] != r["id"]]
            idx_r, P_r = prototipos(modelo, enc, resto)
            self.assertEqual(idx_s, idx_r)
            self.assertTrue(torch.allclose(P_s, P_r, atol=1e-5))
            self.assertFalse(torch.allclose(P_s[idx_s[r["etiqueta"]]], P[idx[r["etiqueta"]]], atol=1e-6))  # sí cambió su clase

    def test_clase_con_una_sola_fila_se_queda_sin_prototipo(self):
        train, _ = tarea(40)
        train = [r for r in train if r["etiqueta"] != "op0"] + [r for r in train if r["etiqueta"] == "op0"][:1]
        modelo, enc = ModeloL2().eval(), CodificadorFalso()
        sop = [r for _, r in C.D.soporte_t17a(train, 3)]
        ps = C.ProtosSinPropia(modelo, enc, sop)
        unica = [r for r in sop if r["etiqueta"] == "op0"][0]
        idx, P = ps.sin(unica["id"])
        self.assertNotIn("op0", idx)
        self.assertEqual(P.shape[0], len(idx))

    def test_caracteristicas_extremo_a_extremo(self):
        train, test = tarea(40, 12)
        torch.manual_seed(0)
        modelo, enc = ModeloL2().eval(), CodificadorFalso()
        c = C.caracteristicas(modelo, enc, train, test, k=5, soporte_k=3)
        self.assertEqual(c["tr_l0"].shape, (40, 4))
        self.assertEqual(c["te_sp"].shape, (12, 4))
        for k in ("tr_l0", "tr_l2", "te_l0", "te_l2", "r_l2"):
            self.assertTrue(np.allclose(c[k].sum(1), 1, atol=1e-5), k)
        # la fila del soporte no ve su propio ejemplo: su simproto con su clase no es el de las filas que no están en el soporte
        self.assertTrue(np.isfinite(c["tr_sp"]).all())
        # renombrar no mueve L0 ni simproto (por posición); L2 con nombres A/B/C sí puede cambiar
        self.assertTrue(np.allclose(c["r_sp"], c["te_sp"], atol=1e-5))


def sinteticas(n, c=6, semilla=0):
    """L0 acierta (confiado) las clases 0..c/2-1 y se equivoca en el resto; L2 al revés. Nadie sabe a priori en cuál está."""
    rng = np.random.default_rng(semilla)
    y = rng.integers(0, c, n)

    def capa(buena):
        p = np.full((n, c), 0.02)
        for i in range(n):
            bien = (y[i] < c // 2) == buena
            if bien:
                p[i, y[i]] = 0.8
            else:
                p[i, (y[i] + 1 + rng.integers(0, c - 1)) % c] = 0.5
                p[i, y[i]] = 0.2
        p += rng.uniform(0, 0.01, p.shape)
        return p / p.sum(1, keepdims=True)
    l0, l2 = capa(True), capa(False)
    sp = rng.normal(0, 0.3, (n, c))
    sp[np.arange(n), y] += 0.5
    return l0, sp, l2, y


class Cabeza(unittest.TestCase):
    def datos(self):
        l0, sp, l2, y = sinteticas(900)
        c = {"tr_l0": l0[:600], "tr_sp": sp[:600], "tr_l2": l2[:600], "tr_y": y[:600], "tr_fold": np.arange(600) % 5,
             "te_l0": l0[600:], "te_sp": sp[600:], "te_l2": l2[600:], "te_y": y[600:],
             "r_sp": sp[600:], "r_l2": l2[600:]}
        return c

    def test_supera_a_las_dos_capas(self):
        c = self.datos()
        a = C.ajustar_y_predecir(c, lambdas=(1e-3, 1e-1))
        acc = lambda p: float((p.argmax(1) == c["te_y"]).mean())
        self.assertGreater(acc(a["probs"]), acc(c["te_l0"]) + 0.05)
        self.assertGreater(acc(a["probs"]), acc(c["te_l2"]) + 0.05)
        for t in C.CABEZAS:
            self.assertGreater(acc(a["probs_tipo"][t]), max(acc(c["te_l0"]), acc(c["te_l2"])), t)
        self.assertTrue(np.allclose(a["probs"].sum(1), 1, atol=1e-6))

    def test_determinismo(self):
        c = self.datos()
        a1 = C.ajustar_y_predecir(c, lambdas=(1e-2, 1e-1))
        a2 = C.ajustar_y_predecir(c, lambdas=(1e-2, 1e-1))
        self.assertEqual((a1["elegida"], a1["lambda"]), (a2["elegida"], a2["lambda"]))
        self.assertTrue(np.array_equal(a1["probs"], a2["probs"]))
        train, _ = tarea(53)
        self.assertEqual(C.pliegues(train), C.pliegues(train))

    def test_la_eleccion_no_mira_test(self):
        c = self.datos()
        a1 = C.ajustar_y_predecir(c, lambdas=(1e-2, 1e-1))
        c2 = dict(c, te_y=(c["te_y"] + 1) % 6, te_l0=c["te_l2"], te_l2=c["te_l0"])  # test cambiado
        a2 = C.ajustar_y_predecir(c2, lambdas=(1e-2, 1e-1))
        self.assertEqual((a1["elegida"], a1["lambda"], a1["cv_nll"]), (a2["elegida"], a2["lambda"], a2["cv_nll"]))


class Informe(unittest.TestCase):
    def test_evaluar_tareas_escribe_todo(self):
        train, test = tarea(40, 12)
        torch.manual_seed(0)
        modelo, enc = ModeloL2().eval(), CodificadorFalso()
        c = C.caracteristicas(modelo, enc, train, test, k=5, soporte_k=3)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(C, "referencias", lambda: {"t": {"l0": 0.5, "knn32": 0.4, "mejor": 0.6}}):
            C.evaluar_tareas({"t": (train, test)}, {"t": c}, d, renombrar=True)
            d = Path(d)
            for f in ("delta.md", "caida.md", "resultados.json", "cabezas.json", "pred/t.jsonl", "pred_renombrado/t.jsonl"):
                self.assertTrue((d / f).exists(), f)
            p = [json.loads(l) for l in open(d / "pred" / "t.jsonl")]
            self.assertEqual(len(p), 12)
            self.assertEqual(set(p[0]), {"id", "probs", "ms"})
            self.assertIn("listón", (d / "delta.md").read_text())
            self.assertIn("conjunta:t", (d / "caida.md").read_text())


if __name__ == "__main__":
    unittest.main()
