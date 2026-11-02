import json
import os
import unittest

from model.l2.modelo import normalizar_mayusculas as N

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "normalizacion.json")


class Normalizacion(unittest.TestCase):
    def test_siete_letras_no_cambia(self):
        self.assertEqual(N("ABCDEFG"), "ABCDEFG")

    def test_ocho_letras_cambia(self):
        self.assertEqual(N("ABCDEFGH"), "abcdefgh")

    def test_exactamente_70_no_cambia(self):
        self.assertEqual(N("ABCDEFGhij"), "ABCDEFGhij")

    def test_71_cambia(self):
        t = "A" * 71 + "a" * 29
        self.assertEqual(N(t), t.lower())

    def test_sin_letras(self):
        for t in ("", "12345 !!! 678", "😀 123"):
            self.assertEqual(N(t), t)

    def test_acentos_y_enie(self):
        self.assertEqual(N("ÁRBOL ÑANDÚ ÉXITO"), "árbol ñandú éxito")

    def test_numeros_y_emojis(self):
        self.assertEqual(N("HOLA 😀 QUIERO 123 CANCELAR 💳"), "hola 😀 quiero 123 cancelar 💳")
        self.assertEqual(N("Hola 😀 123 QUIERO cancelar"), "Hola 😀 123 QUIERO cancelar")

    def test_idempotente(self):
        for t in ("ABCDEFGH", "ÁRBOL ÑANDÚ", "Hola mundo", "A" * 71 + "a" * 29):
            self.assertEqual(N(N(t)), N(t))

    def test_fixture(self):
        d = json.load(open(FIX, encoding="utf-8"))["casos"]
        self.assertEqual(len(d), 16)
        for c in d:
            self.assertEqual(N(c["entrada"]), c["salida"], c["entrada"])


if __name__ == "__main__":
    unittest.main()
