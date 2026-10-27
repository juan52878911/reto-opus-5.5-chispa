import unittest

import numpy as np

from model.lineas_base import correr


def fila(i, c):
    return {"id": "t:train:%d" % i, "etiqueta": c, "texto": "x%d" % i}


class TestCorrer(unittest.TestCase):
    def test_soporte_32_por_clase_y_reproducible(self):
        train = [fila(i, "ab"[i % 2]) for i in range(200)]
        a, b = correr.soporte(train), correr.soporte(train)
        self.assertEqual([r["id"] for _, r in a], [r["id"] for _, r in b])
        for c in "ab":
            self.assertEqual(sum(1 for _, r in a if r["etiqueta"] == c), 32)
            self.assertEqual(sorted(i for i, r in a if r["etiqueta"] == c), list(range(32)))

    def test_vecinos_suma_uno_y_elige_el_cercano(self):
        sims = np.array([0.9, 0.5, 0.4])
        p = correr.vecinos(sims, np.array(["a", "b", "b"]), ["a", "b", "c"], 0.05)
        self.assertAlmostEqual(p.sum(), 1.0)
        self.assertGreater(p[0], 0.9)
        self.assertEqual(p[2], 0.0)

    def test_submuestra_fija(self):
        filas = [fila(i, "a") for i in range(1000)]
        self.assertEqual(correr.submuestra(filas, 300), correr.submuestra(filas, 300))
        self.assertEqual(len(correr.submuestra(filas, 300)), 300)


if __name__ == "__main__":
    unittest.main()
