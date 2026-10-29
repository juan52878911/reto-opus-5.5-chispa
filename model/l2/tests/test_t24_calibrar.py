import json
import math
import unittest

import numpy as np
import torch

from model.evaluacion import metricas as M
from model.l2 import calibrar as C
from model.l2.modelo import Coral, ModeloL2
from model.l2.tests.falso import CodificadorFalso, fila


class ECEConocida(unittest.TestCase):
    def test_ece_a_mano(self):
        # confianza 0,9 con exactitud 0,6 → ECE = 0,3
        ok = [1] * 6 + [0] * 4
        self.assertAlmostEqual(M.ece([0.9] * 10, ok), 0.3, places=6)

    def test_choice_recupera_t_y_baja_ece(self):
        g = torch.Generator().manual_seed(0)
        T_real, n = 0.2, 4000
        ss = [torch.rand(4, generator=g) * 2 for _ in range(n)]
        ys = [int(torch.multinomial(torch.softmax(s / T_real, -1), 1, generator=g)) for s in ss]
        mal = {"T": 0.02}  # sobreconfiada
        antes = C._conf_ok([C.probs_de("choice", s, mal) for s in ss], ys)
        p, aj = C.ajustar("choice", ss, ys, mal)
        despues = C._conf_ok([C.probs_de("choice", s, p) for s in ss], ys)
        self.assertTrue(aj)
        self.assertAlmostEqual(p["T"], T_real, delta=0.03)
        self.assertGreater(M.ece(*antes), 0.2)
        self.assertLessEqual(M.ece(*despues), 0.05)

    def test_noul_platt(self):
        g = torch.Generator().manual_seed(1)
        s = [torch.rand(1, generator=g) * 2 - 0.5 for _ in range(4000)]
        ys = [int(torch.rand(1, generator=g) < torch.sigmoid(3.0 * x[0] - 1.0)) for x in s]
        p, aj = C.ajustar("noul", s, ys, {"a": 12.0, "b": -9.0})
        self.assertTrue(aj)
        self.assertAlmostEqual(p["a"], 3.0, delta=0.5)
        self.assertAlmostEqual(p["b"], -1.0, delta=0.4)
        antes = C._conf_ok([C.probs_de("noul", x, {"a": 12.0, "b": -9.0}) for x in s], ys)
        despues = C._conf_ok([C.probs_de("noul", x, p) for x in s], ys)
        self.assertLessEqual(M.ece(*despues), 0.05)
        self.assertGreater(M.ece(*antes), M.ece(*despues))

    def test_score_temperatura(self):
        g = torch.Generator().manual_seed(2)
        ini = {"a": 4.0, "b": [1.0, 2.0, 3.0, 4.0]}
        T_real = 3.0
        s = [torch.rand(1, generator=g) * 1.5 for _ in range(3000)]
        ys = [int(torch.multinomial(C.probs_de("score5", x, {**ini, "T": T_real}), 1, generator=g)) for x in s]
        p, aj = C.ajustar("score5", s, ys, ini)
        self.assertTrue(aj)
        self.assertAlmostEqual(p["a"], 4.0 / T_real, delta=0.3)
        self.assertAlmostEqual(p["b"][0], 1.0 / T_real, delta=0.15)

    def test_pocas_filas_o_una_clase_no_se_ajusta(self):
        ini = {"a": 4.0, "b": -4.0}
        self.assertEqual(C.ajustar("noul", [torch.rand(1)] * 5, [0, 1] * 2 + [1], ini), (ini, False))
        self.assertEqual(C.ajustar("noul", [torch.rand(1)] * 50, [1] * 50, ini), (ini, False))


class Escalate(unittest.TestCase):
    def test_tau_maxima_cobertura(self):
        conf = [0.99, 0.95, 0.9, 0.8, 0.7, 0.6]
        ok = [1, 1, 1, 1, 0, 1]
        # prefijos: 1,1,1,1,0,1 → precisión ≥ 0,95 solo hasta 0,8 (4/4); con 0,6: 5/6 = 0,83
        tau, cob, prec = C.tau_escalate(conf, ok)
        self.assertEqual((tau, cob, prec), (0.8, 4 / 6, 1.0))

    def test_empates_no_parten_un_grupo(self):
        tau, cob, _ = C.tau_escalate([0.9, 0.9, 0.9, 0.5], [1, 1, 0, 1], precision=0.6)
        self.assertEqual((tau, cob), (0.5, 1.0))  # 3/4 ≥ 0,6
        tau, cob, _ = C.tau_escalate([0.9, 0.9, 0.9, 0.5], [1, 0, 1, 1], precision=0.9)
        self.assertEqual((tau, cob), (1.0, 0.0))  # el grupo de 0,9 entero da 2/3

    def test_nada_alcanza(self):
        self.assertEqual(C.tau_escalate([0.9, 0.8], [0, 0])[:2], (1.0, 0.0))

    def test_auroc(self):
        self.assertEqual(C.auroc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]), 1.0)
        self.assertEqual(C.auroc([0.1, 0.2, 0.8, 0.9], [1, 1, 0, 0]), 0.0)
        self.assertEqual(C.auroc([0.5] * 4, [1, 0, 1, 0]), 0.5)
        self.assertTrue(math.isnan(C.auroc([0.5, 0.6], [1, 1])))


class DeExtremoAExtremo(unittest.TestCase):
    def test_modelo_aleatorio(self):
        torch.manual_seed(0)
        m, enc = ModeloL2().eval(), CodificadorFalso()
        filas = [fila(i, t, 4 if t == "choice" else 2, tarea="tarea_" + t, k=5) for t in ("choice", "noul", "score") for i in range(60)]
        inf = C.calibrar(m, enc, filas)
        self.assertEqual(set(inf["tareas"]), {"tarea_choice", "tarea_noul", "tarea_score"})
        self.assertEqual(set(inf["tipos"]), {"choice", "noul", "score5"})
        for r in inf["tareas"].values():
            self.assertLessEqual(r["ece_despues"], r["ece_antes"] + 1e-9)
            self.assertTrue(0 <= r["tau"] <= 1 and 0 <= r["cobertura"] <= 1)
        # coincide con la cabeza del modelo cuando no se ajusta: «antes» == ModeloL2.forward
        with torch.no_grad():
            probs, _ = m(filas[:60], enc, entrenar=False)
        ss = C.simil(m, enc, filas[:60])
        for p, s in zip(probs, ss):
            self.assertTrue(torch.allclose(p, C.probs_de("choice", s, C.cabeza_inicial(m, "choice")), atol=1e-5))
        # la sección CALIB cumple las reglas de format/chispa3 (T>0, θ y τ en [0,1])
        cs = C.a_calib_chispa(inf)
        json.dumps(cs)
        self.assertTrue(0 <= cs["tau_escalate"] <= 1)
        for k, v in cs["tipos"].items():
            self.assertTrue(v["T"] > 0 and 0 <= v["theta"] <= 1, k)
        self.assertIn("score5#3", cs["tipos"])
        self.assertNotIn("score5#4", cs["tipos"])


class ScoreComoLista(unittest.TestCase):
    def test_probs_de_coincide_con_coral(self):
        for K in (3, 5):
            torch.manual_seed(K)
            c = Coral(K)
            with torch.no_grad():
                c.w.fill_(3.0), c.theta1.fill_(0.7), c.delta.normal_()
            ini = {"a": float(c.w), "b": [float(x) for x in c.umbrales()]}
            for s in (0.0, 0.4, 1.3):
                x = torch.tensor([s])
                p = C.probs_de("score%d" % K, x, ini)
                self.assertEqual(len(p), K)
                self.assertAlmostEqual(float(p.sum()), 1.0, places=5)
                self.assertTrue(torch.allclose(p, c(x)[0], atol=1e-6))
                self.assertEqual(C.M.etiqueta_coral(p), int(Coral.etiqueta(c.acumuladas(x))[0]))

    def test_ida_y_vuelta_calib(self):
        for K in (3, 5):
            torch.manual_seed(10 + K)
            c = Coral(K)
            with torch.no_grad():
                c.w.fill_(2.5), c.theta1.fill_(0.5), c.delta.normal_()
            clave = "score%d" % K
            inf = {"tipos": {clave: {"a": float(c.w), "b": [float(x) for x in c.umbrales()], "T": 1.0, "theta": 0.5}},
                   "tau_escalate": 0.5}
            t = C.a_calib_chispa(inf)["tipos"]
            b = [t[clave]["b"]]
            for j in range(1, K - 1):  # b_j = b_{j-1} + incremento de scoreK#j
                b.append(b[-1] + t["%s#%d" % (clave, j)]["a"])
            self.assertEqual(len(t), K - 1)
            for s in (0.1, 0.9):
                x = torch.tensor([s])
                p = C.probs_de(clave, x, {"a": t[clave]["a"], "b": b})
                self.assertTrue(torch.allclose(p, c(x)[0], atol=1e-5))

    def test_tarea_con_dos_cabezas(self):
        # misma tarea con score3 y score5 (y noul): el τ global usa los parámetros de cada cabeza
        m, enc = ModeloL2().eval(), CodificadorFalso()
        filas = [fila(i, "score", tarea="mixta", k=k) for k in (3, 5) for i in range(40)]
        filas += [fila(i, "noul", 2, tarea="mixta") for i in range(40)]
        inf = C.calibrar(m, enc, filas)
        self.assertEqual(set(inf["tipos"]), {"score3", "score5", "noul"})
        self.assertIn("score3#1", C.a_calib_chispa(inf)["tipos"])


if __name__ == "__main__":
    unittest.main()
