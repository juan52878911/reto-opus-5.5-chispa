import unittest

import numpy as np

from model.cascada import cascada as K
from model.evaluacion import metricas as M


def capa(nombre, top, conf):
    c = K.Capa.__new__(K.Capa)
    c.nombre, c.top, c.conf = nombre, np.array(top), np.array(conf, float)
    return c


def filas(n):
    return [{"id": "t:test:%d" % i} for i in range(n)]


class Basicos(unittest.TestCase):
    def test_pliegue_fijo_y_repartido(self):
        a = [K.pliegue("x:%d" % i) for i in range(400)]
        self.assertEqual(a, [K.pliegue("x:%d" % i) for i in range(400)])
        self.assertTrue(150 < sum(a) < 250)
        self.assertNotEqual(a, [K.pliegue("x:%d" % i, semilla=1) for i in range(400)])

    def test_macro_f1_igual_que_metricas(self):
        rng = np.random.default_rng(0)
        y, p = rng.integers(0, 5, 200), rng.integers(0, 6, 200)
        self.assertAlmostEqual(K.macro_f1(y, p, 6), M.macro_f1(list(y), list(p)))

    def test_decidir_pasa_por_tau_y_la_ultima_responde(self):
        a = capa("A", [0, 0, 0, 0], [0.9, 0.5, 0.0, 0.7])
        b = capa("B", [1, 1, 1, 1], [0.1, 0.2, 0.3, 0.4])
        dec, resp, coste = K.decidir([a, b], [0.7], {"A": 1, "B": 10})
        self.assertEqual(list(dec), [0, 1, 1, 0])
        self.assertEqual(list(resp), [0, 1, 1, 0])    # conf 0 = sin opinión: nunca responde, aunque τ = 0
        self.assertEqual(list(coste), [1, 11, 11, 1])
        _, resp0, _ = K.decidir([a, b], [0.0], {"A": 1, "B": 10})
        self.assertEqual(list(resp0), [0, 0, 1, 0])
        _, respi, _ = K.decidir([a, b], [np.inf], {"A": 1, "B": 10})
        self.assertEqual(list(respi), [1, 1, 1, 1])

    def test_oraculo_techo(self):
        cl = ["a", "b"]
        f = [{"etiqueta": "a"}, {"etiqueta": "b"}, {"etiqueta": "a"}]
        c1 = capa("1", [0, 0, 1], [1, 1, 1])
        c2 = capa("2", [0, 1, 1], [1, 1, 1])
        self.assertAlmostEqual(K.oraculo([c1, c2], f, cl)["exactitud"], 2 / 3)
        for c in (c1, c2):
            self.assertLessEqual(K.sola(c, f, cl)["macro_f1"], K.oraculo([c1, c2], f, cl)["macro_f1"])


class Eleccion(unittest.TestCase):
    def datos(self, n=400, semilla=0):
        """L0 acierta cuando está seguro; L1 acierta siempre pero casi nunca está seguro."""
        rng = np.random.default_rng(semilla)
        y = rng.integers(0, 3, n)
        seguro = rng.random(n) < 0.5
        top0 = np.where(seguro, y, (y + 1) % 3)
        conf0 = np.where(seguro, rng.uniform(0.8, 1, n), rng.uniform(0.2, 0.6, n))
        return y, capa("L0", top0, conf0), capa("L1", y, rng.uniform(0.3, 0.9, n))

    def test_calidad_y_rapida_aceptan_lo_seguro(self):
        y, c0, c1 = self.datos()
        costos = {"L0": 1, "L1": 10}
        for modo in ("calidad", "rapida"):
            tau = K.elegir([c0, c1], y, 3, costos, modo)[0]
            self.assertTrue(0.5 <= tau <= 0.85, (modo, tau))
        d, _, _ = K.decidir([c0, c1], [0.7], costos)
        self.assertEqual(K.macro_f1(y, d, 3), 1.0)

    def test_rapida_sin_precision_no_responde(self):
        y = np.zeros(100, int)
        mala = capa("L0", np.ones(100, int), np.linspace(0.5, 1, 100))
        ult = capa("L1", y, np.ones(100))
        self.assertEqual(K.elegir([mala, ult], y, 2, {"L0": 1, "L1": 2}, "rapida"), [np.inf])

    def test_validar_no_mira_el_pliegue_evaluado(self):
        y, c0, c1 = self.datos(300)
        fs = [{"id": "t:test:%d" % i, "etiqueta": str(v)} for i, v in enumerate(y)]
        clases = ["0", "1", "2"]
        pl = np.array([K.pliegue(r["id"]) for r in fs])
        costos = {"L0": 1, "L1": 10}
        for modo in ("calidad", "rapida"):
            base = K.validar([c0, c1], fs, clases, costos, modo)
            # cambiar la confianza de L0 solo en el pliegue 1 no puede mover el τ con que se evalúa el pliegue 1
            c0b = capa("L0", c0.top.copy(), np.where(pl == 1, 1 - c0.conf, c0.conf))
            alt = K.validar([c0b, c1], fs, clases, costos, modo)
            self.assertEqual(base["taus"][1], alt["taus"][1], modo)   # τ del evaluado en 1 = ajustado en 0
            self.assertNotEqual(base["taus"][0], alt["taus"][0], modo)
            self.assertAlmostEqual(sum(base["fraccion"].values()), 1.0)
            self.assertEqual(sum(base["pliegues"]), 300)

    def test_tres_capas_y_coste(self):
        y, c0, c1 = self.datos(200)
        c2 = capa("L2", y, np.ones(200))
        v = K.validar([c0, c1, c2], [{"id": "t:%d" % i, "etiqueta": str(x)} for i, x in enumerate(y)], ["0", "1", "2"],
                      {"L0": 1, "L1": 10, "L2": 100}, "calidad")
        self.assertEqual(len(v["taus"][0]), 2)
        self.assertLessEqual(v["ms_medio"], 111)
        self.assertGreaterEqual(v["ms_medio"], 1)


if __name__ == "__main__":
    unittest.main()
