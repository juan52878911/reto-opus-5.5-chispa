"""Paridad con el runtime (revisión RM4): hallazgos 1, 2, 3, 5 y 6."""
import unittest
from unittest import mock

import torch

from model.l2 import calibrar as C
from model.l2 import exportar as E
from model.l2.modelo import ModeloL2
from model.l2.tests.falso import CodificadorFalso, fila


class Rm4(unittest.TestCase):
    def test_1_tau_global_con_parametros_por_cabeza(self):
        filas = [fila(i, "choice", n=3, tarea="a" if i < 3 else "b") for i in range(6)]
        vistos = []
        orig = C.probs_de

        def espia(clave, s, p):
            vistos.append(p["T"])
            return orig(clave, s, p)

        with mock.patch.object(C, "simil", lambda m, e, fs, l=64: [torch.tensor([1.0, 0.5, 0.2])] * len(fs)), \
                mock.patch.object(C, "cabeza_inicial", lambda m, k: {"T": 1.0}), \
                mock.patch.object(C, "ajustar", lambda k, ss, ys, p0: ({"T": float(len(ss))}, True)), \
                mock.patch.object(C, "probs_de", espia):
            C._calibrar(mock.Mock(), None, filas)
        self.assertEqual(vistos[-6:], [6.0] * 6)  # T de la cabeza (n=6), no la de la tarea (n=3)

    def test_2_noul_regla_theta(self):
        ps = [torch.tensor([0.6, 0.4])]
        conf, ok = C._conf_ok(ps, [1], "noul", 0.3)
        self.assertAlmostEqual(conf[0], 0.4, places=6)
        self.assertEqual(ok, [True])
        conf, ok = C._conf_ok(ps, [0], "noul", 0.5)
        self.assertAlmostEqual(conf[0], 0.6)
        self.assertEqual(ok, [True])

    def test_3_score_confianza_de_la_mediana(self):
        conf, ok = C._conf_ok([torch.tensor([.40, .15, .45])], [1], "score3")
        self.assertAlmostEqual(conf[0], 0.15)
        self.assertEqual(ok, [True])

    def test_5_soporte_score_por_nivel(self):
        torch.manual_seed(0)
        m, enc = ModeloL2().eval(), CodificadorFalso()
        a, b = fila(0, "score", k=3), fila(0, "score", k=3)
        a["opciones"], b["opciones"] = ["1", "2", "3"], ["3", "2", "1"]
        sp = {"1": 0.9, "2": 0.1, "3": -0.4}  # soporte por id
        res = []
        for f in (a, b):
            with mock.patch.object(ModeloL2, "_simproto", lambda *x, f=f: [torch.tensor([sp[o] for o in f["opciones"]])]):
                p = m.forward([f], enc, entrenar=False, protos={})[0][0]
            res.append({o: float(v) for o, v in zip(f["opciones"], p)})
        for o in "123":
            self.assertAlmostEqual(res[0][o], res[1][o], places=6)

    def test_6_calib_incluye_score_extra(self):
        m = E.modelo_aleatorio()
        m.asegurar_cabeza("score6")
        r = E.calib_completa(m, {"tipos": {}, "tau_escalate": 0.5})
        self.assertIn("score6", r["tipos"])
        self.assertIn("score6#4", r["tipos"])


if __name__ == "__main__":
    unittest.main()
