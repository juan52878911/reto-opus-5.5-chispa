"""T2.2d: cabeza por pliegues de test, calibración fuera de pliegue y --desde-cache, con datos sintéticos (sin S3, sin GPU)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from model.cascada import cascada as K
from model.l2 import conjunta as C
from model.l2.tests.test_conjunta import sinteticas
from model.l2.tests.falso import fila


def cache_y_filas(n=400, c=6, noul=False):
    l0, sp, l2, y = sinteticas(n, c)
    if noul:
        c, y = 2, (y >= 3).astype(int)
        l0, l2, sp = np.stack([1 - l0[:, 0], l0[:, 0]], 1), np.stack([1 - l2[:, 0], l2[:, 0]], 1), sp[:, :2]
    ids = ["t:test:%d" % i for i in range(n)]
    filas = [dict(fila(i, n=c), id=ids[i], tipo="noul" if noul else "choice", etiqueta="op%d" % y[i]) for i in range(n)]
    cache = {"te_l0": l0, "te_sp": sp, "te_l2": l2, "te_y": y, "r_sp": sp, "r_l2": l2, "te_ms": np.zeros(n)}
    return cache, filas, ids


class Particion(unittest.TestCase):
    def test_es_la_de_la_cascada(self):
        self.assertIs(C.pliegue, K.pliegue)

    def test_ninguna_fila_se_predice_con_una_cabeza_que_la_vio(self):
        c, _, ids = cache_y_filas(300)
        clave = lambda x: [r.tobytes() for r in np.round(x, 9)]   # cada fila de L0 es única (ruido continuo)
        orig_aj, orig_pr = C.Cabeza.ajustar, C.Cabeza.probs
        llamadas = []

        def ajustar(self, l0, sp, l2, y):
            self.vistas = set(clave(l0))
            return orig_aj(self, l0, sp, l2, y)

        def probs(self, l0, sp, l2):
            vistas = clave(l0)
            self.assertion = not (set(vistas) & self.vistas)
            llamadas.append((len(vistas), self.assertion))
            return orig_pr(self, l0, sp, l2)
        with mock.patch.object(C.Cabeza, "ajustar", ajustar), mock.patch.object(C.Cabeza, "probs", probs):
            a = C.ajustar_y_predecir_cvtest(c, ids, lambdas=(1e-2,))
        self.assertTrue(llamadas)
        self.assertTrue(all(ok for _, ok in llamadas))
        self.assertEqual(a["probs"].shape, c["te_l0"].shape)
        self.assertTrue(np.allclose(a["probs"].sum(1), 1, atol=1e-6))
        self.assertEqual(sum(a["pliegues_test"]), 300)

    def test_cada_fila_la_predice_la_cabeza_del_otro_pliegue(self):
        c, _, ids = cache_y_filas(300)
        pl = np.array([K.pliegue(i) for i in ids])
        ajustes = []
        orig = C.ajustar_y_predecir

        def espia(sub, *a, **k):
            ajustes.append(len(sub["tr_y"]))
            return orig(sub, *a, **k)
        with mock.patch.object(C, "ajustar_y_predecir", espia):
            C.ajustar_y_predecir_cvtest(c, ids, lambdas=(1e-2,))
        self.assertEqual(sorted(ajustes), sorted([int((pl == 1).sum()), int((pl == 0).sum())]))  # ajusta f con el otro pliegue

    def test_supera_a_las_capas_y_es_determinista(self):
        c, _, ids = cache_y_filas(600)
        a1, a2 = (C.ajustar_y_predecir_cvtest(c, ids, lambdas=(1e-2, 1e-1)) for _ in range(2))
        acc = lambda p: float((p.argmax(1) == c["te_y"]).mean())
        self.assertGreater(acc(a1["probs"]), max(acc(c["te_l0"]), acc(c["te_l2"])) + 0.03)
        self.assertTrue(np.array_equal(a1["probs"], a2["probs"]))


class Calibracion(unittest.TestCase):
    def sobreconfiado(self, n=800, c=5, noul=False):
        rng = np.random.default_rng(3)
        y = rng.integers(0, 2 if noul else c, n)
        k = 2 if noul else c
        z = rng.normal(0, 1.5, (n, k))
        z[np.arange(n), y] += 1.0
        z *= 4   # sobreconfianza
        p = np.exp(z - z.max(1, keepdims=True))
        return p / p.sum(1, keepdims=True), y

    def test_no_empeora_el_logloss_ni_el_ece(self):
        for noul in (False, True):
            p, y = self.sobreconfiado(noul=noul)
            ids = ["t:%d" % i for i in range(len(y))]
            pc, prms = C.calibrar_oof(p, y, ids, "noul" if noul else "choice")
            m = C.metricas_calibracion(p, pc, y)
            self.assertLessEqual(m["despues"]["nll"], m["antes"]["nll"] + 1e-9, noul)
            self.assertLess(m["despues"]["ece"], m["antes"]["ece"], noul)
            self.assertTrue(np.allclose(pc.sum(1), 1, atol=1e-5))
            self.assertEqual(len(prms), 2)
            self.assertTrue(all(q["ajustado"] for q in prms))
            if not noul:
                self.assertTrue(all(q["T"] > 1 for q in prms))   # había que enfriar

    def test_los_parametros_de_un_pliegue_salen_del_otro(self):
        p, y = self.sobreconfiado()
        ids = ["t:%d" % i for i in range(len(y))]
        pl = np.array([K.pliegue(i) for i in ids])
        y2 = y.copy()
        y2[pl == 0] = (y2[pl == 0] + 1) % p.shape[1]   # estropear las etiquetas del pliegue 0 no debe tocar su propia calibración
        pc1, _ = C.calibrar_oof(p, y, ids, "choice")
        pc2, _ = C.calibrar_oof(p, y2, ids, "choice")
        self.assertFalse(np.allclose(pc1[pl == 1], pc2[pl == 1]))   # el pliegue 1 usa las etiquetas del 0
        self.assertTrue(np.allclose(pc1[pl == 0], pc2[pl == 0]))                  # el pliegue 0 solo usa las del 1

    def test_auroc_escalate_solo_si_hay_escalate(self):
        p, y = self.sobreconfiado()
        filas = [{"etiqueta": "escalate" if v == 0 else "x"} for v in y]
        self.assertIn("auroc_escalate", C.metricas_calibracion(p, p, y, filas)["despues"])
        self.assertNotIn("auroc_escalate", C.metricas_calibracion(p, p, y, [{"etiqueta": "x"}] * len(y))["despues"])


class Extremo(unittest.TestCase):
    def test_cvtest_calibrar_desde_cache(self):
        c, filas, _ = cache_y_filas(300)
        train = filas[:20]
        c.update({"tr_" + k: c["te_" + k][:200] for k in ("l0", "sp", "l2", "y")}, tr_fold=np.arange(200) % 5)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(C, "referencias", lambda: {"t": {"l0": 0.5, "knn32": 0.4, "mejor": 0.6}}):
            d = Path(d)
            C.evaluar_tareas({"t": (train, filas)}, {"t": c}, d / "tr", True)
            C.evaluar_tareas({"t": (train, filas)}, {"t": c}, d / "cv", True, "cvtest", True, d / "tr")
            for f in ("calibracion.json", "calibracion.md", "h1.md", "pred_cal/t.jsonl", "pred/t.jsonl", "cabezas.json"):
                self.assertTrue((d / "cv" / f).exists(), f)
            cal = json.loads((d / "cv" / "calibracion.json").read_text())
            self.assertEqual(cal["modo_cabeza"], "cvtest")
            self.assertIn("H2", (d / "cv" / "calibracion.md").read_text())
            self.assertIn("H1", (d / "cv" / "h1.md").read_text())


if __name__ == "__main__":
    unittest.main()
