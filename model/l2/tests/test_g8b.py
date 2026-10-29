"""G.8b: mediana CORAL en score, λ = ∞, τ para esquemas nuevos y L1 con shrinkage."""
import math
import unittest

import numpy as np
import torch

from model.cascada import capas as L
from model.evaluacion import chispa_eval as CE
from model.evaluacion import metricas as M
from model.evaluacion.jevbench_informe import top1
from model.l2 import barrido as B
from model.l2.modelo import Coral, mezcla_prototipos


class MedianaCoral(unittest.TestCase):
    def test_acumuladas_no_monotonas(self):
        sup = torch.tensor([[0.9, 0.3, 0.6, 0.2]])   # no monótona: dos umbrales > 0,5 (el 1.º y el 3.º)
        self.assertEqual(int(Coral.etiqueta(sup)[0]), 2)
        self.assertEqual(M.contar_umbrales(sup[0].numpy()), 2)
        self.assertEqual(M.contar_umbrales([0.6, 0.4, 0.7]), 2)   # el primer cruce daría 1
        self.assertEqual(int(Coral.etiqueta(torch.tensor([[0.4, 0.9]]))[0]), 1)

    def test_difiere_del_argmax(self):
        sup = [0.7, 0.45, 0.4]            # P(y=k) = [0,3 · 0,25 · 0,05 · 0,4]: el argmax es el nivel 4, la mediana el 2
        p = [1 - sup[0], sup[0] - sup[1], sup[1] - sup[2], sup[2]]
        ops = ["1", "2", "3", "4"]
        probs = dict(zip(ops, p))
        self.assertEqual(M.top1(probs)[0], "4")
        self.assertEqual(M.top1(probs, "score", ops)[0], "2")
        self.assertEqual(M.top1(probs, "score", ops)[1], 0.4)   # la confianza sigue siendo la máxima
        self.assertEqual(top1(probs, ops, "score"), "2")
        self.assertEqual(top1(probs, ops), "4")

    def test_coral_forward_y_etiqueta_coinciden(self):
        c = Coral(5)
        sim = torch.linspace(-1, 2, 7)
        p = c(sim)
        n = Coral.etiqueta(c.acumuladas(sim))
        self.assertTrue(torch.allclose(p.sum(1), torch.ones(7), atol=1e-5))
        for i in range(7):
            self.assertEqual(M.etiqueta_coral(p[i].detach().numpy()), int(n[i]))

    def test_evaluar_usa_la_mediana_solo_en_score(self):
        ops = ["1", "2", "3", "4"]
        probs = {"1": 0.3, "2": 0.25, "3": 0.05, "4": 0.4}
        filas = [{"id": "a", "tarea": "t", "tipo": "score", "opciones": ops, "etiqueta": "2"},
                 {"id": "b", "tarea": "t", "tipo": "choice", "opciones": ops, "etiqueta": "2"}]
        r = CE.metricas_grupo(filas, {"a": {"probs": probs}, "b": {"probs": probs}})
        self.assertEqual(r["exactitud"], 0.5)


class Lambda(unittest.TestCase):
    def test_lambda_infinito_es_la_descripcion(self):
        suma = torch.randn(2, 3, 4)
        h = torch.nn.functional.normalize(torch.randn(2, 4), dim=-1)
        P = mezcla_prototipos(suma, torch.tensor([3.0, 5.0]), h, math.inf)
        self.assertTrue(torch.allclose(P, h.unsqueeze(1).expand_as(P), atol=1e-6))

    def test_tabla_de_equivalencia(self):
        # peso de los ejemplos n/(n+λ) = 1 − κ/(κ+n) con κ = λ
        for n in (1, 8, 32):
            for lam in (1, 4, 16):
                self.assertAlmostEqual(n / (n + lam), 1 - lam / (lam + n))


class Tau(unittest.TestCase):
    def test_abstencion_maxima(self):
        conf = np.linspace(0.1, 1.0, 10)
        ok = conf > 0.5
        tau, ab, prec = B.tau_abstencion(conf, ok, 0.2)
        self.assertLessEqual(ab, 0.2)
        self.assertAlmostEqual(tau, conf[2])
        self.assertAlmostEqual(prec, 5 / 8)

    def test_empates_no_pasan_de_la_abstencion(self):
        tau, ab, _ = B.tau_abstencion([0.5] * 10, [True] * 10, 0.2)
        self.assertEqual((tau, ab), (0.5, 0.0))

    def test_p95(self):
        r = B.resumen_tau([0.9] * 20 + [0.5] * 20, [True] * 20 + [False] * 20)
        self.assertEqual((r["tau_p95"], r["abstencion_p95"], r["precision_p95"]), (0.9, 0.5, 1.0))


class FalsoPotion:
    def encode(self, textos):
        return [np.random.default_rng(abs(hash(t)) % 2**32).normal(size=8) for t in textos]


class L1Lambda(unittest.TestCase):
    def setUp(self):
        self.m = FalsoPotion()
        ops = ["a", "b"]
        self.fila = lambda i, e: {"id": str(i), "pregunta": "q", "texto": "t%d%s" % (i, e), "opciones": ops, "etiqueta": e,
                                  "descripciones": {"a": "da", "b": "db"}, "tipo": "choice"}
        self.train = [self.fila(i, "ab"[i % 2]) for i in range(6)]
        self.test = [self.fila(10 + i, "ab"[i % 2]) for i in range(4)]

    def test_lambda_cero_es_prototipos(self):
        P0 = L.prototipos(self.m, self.train)
        P = L.prototipos_lam(self.m, self.train, {"a": np.ones(8, np.float32), "b": np.ones(8, np.float32)}, 0)
        for c in P0:
            self.assertTrue(np.allclose(P0[c], P[c], atol=1e-6))

    def test_lambda_infinito_es_zero_shot(self):
        a = L.l1_lam(self.m, self.train, self.test, math.inf)
        b = L.l1_zs(self.m, self.test)
        for k in a:
            self.assertEqual(a[k]["probs"], b[k]["probs"])


if __name__ == "__main__":
    unittest.main()
