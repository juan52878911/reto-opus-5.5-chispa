import math
import unittest

import torch
import torch.nn.functional as F

from model.l2.modelo import Coral, ModeloL2, Ranuras, Torre, K_RANURAS, D, maxsim, blanda_vector
from model.l2.tests.falso import CodificadorFalso, fila


class Formas(unittest.TestCase):
    def test_ranuras_y_torre(self):
        S = Ranuras()(torch.randn(3, 7, 384), torch.ones(3, 7, dtype=torch.bool))
        self.assertEqual(S.shape, (3, K_RANURAS, D))
        self.assertTrue(torch.allclose(S.norm(dim=-1), torch.ones(3, K_RANURAS), atol=1e-5))
        h = Torre()(torch.randn(5, 384))
        self.assertEqual(h.shape, (5, D))
        self.assertTrue(torch.allclose(h.norm(dim=-1), torch.ones(5), atol=1e-5))

    def test_mascara_ignora_relleno(self):
        r = Ranuras().eval()
        H = torch.randn(1, 6, 384)
        m = torch.tensor([[1, 1, 1, 0, 0, 0]], dtype=torch.bool)
        H2 = H.clone()
        H2[:, 3:] = 99
        self.assertTrue(torch.allclose(r(H, m), r(H2, m), atol=1e-5))

    def test_probs_suman_uno(self):
        m, enc = ModeloL2(), CodificadorFalso()
        filas = [fila(0, "choice", 5), fila(1, "choice", 3, "u"), fila(2, "noul"), fila(3, "score", k=5), fila(4, "score", k=4)]
        probs, ps = m(filas, enc)
        for r, p in zip(filas, probs):
            self.assertEqual(p.shape, (len(r["opciones"]),))
            self.assertAlmostEqual(float(p.sum()), 1.0, places=5)
            self.assertTrue(bool((p >= 0).all()))
        self.assertTrue(all(math.isfinite(float(v)) for v in ps.values()))
        ps["total"].backward()
        self.assertIsNotNone(m.ranuras.q.grad)
        self.assertIsNotNone(m.coral["score5"].w.grad)


class MaxSim(unittest.TestCase):
    def test_a_mano(self):
        S = torch.tensor([[[1.0, 0.0], [0.0, 1.0]]])  # una fila, K=2
        h = torch.tensor([[1.0, 0.0], [0.6, 0.8]])
        esperado = torch.tensor([[max(math.log1p(math.exp(1.0)), math.log1p(math.exp(0.0))),
                                  max(math.log1p(math.exp(0.6)), math.log1p(math.exp(0.8)))]])
        self.assertTrue(torch.allclose(maxsim(S, h), esperado, atol=1e-6))
        self.assertTrue(torch.allclose(maxsim(S, h), F.softplus(S[0] @ h.T).max(0).values[None], atol=1e-6))


class CoralMonotonia(unittest.TestCase):
    def test_umbrales_ordenados_y_distribucion(self):
        for semilla in range(5):
            torch.manual_seed(semilla)
            c = Coral(6)
            with torch.no_grad():
                c.delta.normal_(0, 3)
                c.theta1.normal_(0, 2)
                c.w.normal_(0, 3)
            th = c.umbrales()
            self.assertEqual(len(th), 5)
            self.assertTrue(bool((th[1:] > th[:-1]).all()))
            sim = torch.linspace(0, 2, 9)
            p = c(sim)
            self.assertTrue(torch.allclose(p.sum(1), torch.ones(9), atol=1e-5))
            sup = torch.sigmoid(c.w * sim.unsqueeze(1) - th)
            # P(y>j) decrece en j para cualquier sim (monotonía); y si w>0 el valor esperado crece con sim
            self.assertTrue(bool((sup[:, 1:] <= sup[:, :-1] + 1e-7).all()))
            e = Coral.esperado(p)
            self.assertTrue(bool(((e >= 1 - 1e-5) & (e <= 6 + 1e-5)).all()))
            sg = 1 if c.w > 0 else -1
            self.assertTrue(bool((sg * (e[1:] - e[:-1]) >= -1e-5).all()))


class Cache(unittest.TestCase):
    def test_mismo_texto_mismo_vector(self):
        enc = CodificadorFalso()
        a = enc.pasaje(["passage: x", "passage: y"])
        pases = enc.pases
        b = enc.pasaje(["passage: y", "passage: x", "passage: y"])
        self.assertEqual(enc.pases, pases, "todo debía salir de la caché")
        self.assertTrue(torch.equal(b[0], a[1]) and torch.equal(b[1], a[0]) and torch.equal(b[2], a[1]))
        self.assertEqual((enc.fallos, enc.aciertos), (2, 3))
        self.assertTrue(torch.allclose(a.norm(dim=-1), torch.ones(2), atol=1e-5))

    def test_duplicados_en_la_misma_llamada(self):
        enc = CodificadorFalso()
        enc.pasaje(["passage: z", "passage: z"])
        self.assertEqual(enc.fallos, 1)

    def test_el_modelo_codifica_cada_opcion_una_vez(self):
        m, enc = ModeloL2(), CodificadorFalso()
        filas = [fila(i, "choice", 4) for i in range(8)]  # misma pregunta y opciones en todas
        m(filas, enc, entrenar=False)
        self.assertEqual(enc.fallos, 4)
        m(filas, enc, entrenar=False)
        self.assertEqual(enc.fallos, 4)


class KLParcial(unittest.TestCase):
    def test_solo_filas_con_blanda(self):
        torch.manual_seed(0)
        m, enc = ModeloL2(), CodificadorFalso()
        bl = {"op0": 0.7, "op1": 0.3}  # parcial: faltan op2 y op3 (valen 0)
        con = fila(0, "choice", 4, blanda=bl)
        sin = fila(1, "choice", 4)
        _, p_con = m([con], enc)
        _, p_mixto = m([con, sin], enc)
        self.assertGreater(float(p_con["kl"]), 0)
        # la KL del lote mixto es la de la fila con blanda (no se diluye con la que no la tiene)
        self.assertAlmostEqual(float(p_con["kl"]), float(p_mixto["kl"]), places=5)
        _, p_sin = m([sin, fila(2, "choice", 4)], enc)
        self.assertEqual(float(p_sin["kl"]), 0.0)
        # a mano
        p, _ = m([con], enc, entrenar=False)
        q = blanda_vector(con)
        kl = sum(float(q[i]) * math.log(float(q[i]) / float(p[0][i])) for i in range(4) if q[i] > 0)
        self.assertAlmostEqual(kl, float(p_con["kl"]), places=4)

    def test_blanda_fuera_de_las_opciones_se_ignora(self):
        self.assertIsNone(blanda_vector(fila(0, blanda={"otra": 1.0})))
        v = blanda_vector(fila(0, blanda={"op0": 2.0, "op1": 2.0, "zzz": 5.0}))
        self.assertAlmostEqual(float(v.sum()), 1.0)
        self.assertEqual(float(v[0]), 0.5)

    def test_noul_y_score_con_blanda(self):
        m, enc = ModeloL2(), CodificadorFalso()
        _, ps = m([fila(0, "noul", blanda={"false": 0.4, "true": 0.6}), fila(1, "score", k=3, blanda={"1": 0.2, "2": 0.5, "3": 0.3})], enc)
        self.assertGreater(float(ps["kl"]), 0)


if __name__ == "__main__":
    unittest.main()
