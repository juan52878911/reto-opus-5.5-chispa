"""L0MULTI: paridad con el lector/escritor Go (golden de format/chispa3/testdata/l0multi.chispa)."""
import os
import unittest

from chispa import formato

GOLDEN = os.path.join(os.path.dirname(__file__), "..", "..", "..", "format", "chispa3", "testdata", "l0multi.chispa")


@unittest.skipUnless(os.path.exists(GOLDEN), "falta el golden de format/chispa3")
class L0MultiTest(unittest.TestCase):
    def test_lee_el_golden_de_go_y_lo_reescribe_igual(self):
        datos = open(GOLDEN, "rb").read()
        secs = formato.leer(datos)
        self.assertIn(formato.L0MULTI, secs)
        es = formato.leer_l0multi(secs[formato.L0MULTI])
        self.assertEqual([e[0] for e in es], [formato.L0, formato.L0TF, formato.L0])
        self.assertEqual([e[2] for e in es], ["urgencia", "tf", "injection"])
        self.assertEqual(formato.l0multi(es), secs[formato.L0MULTI])
        self.assertEqual(formato.escribir(secs), datos)

    def test_invalidas(self):
        b = formato.l0multi([(formato.L0, b"abc", "x")])
        for malo in (b"", b[:-1], b + b"\0", b"\2\0\0\0" + b[4:], b[:4] + b"\0\0\0\0"):
            with self.assertRaises(ValueError):
                formato.leer_l0multi(malo)
        with self.assertRaises(ValueError):
            formato.l0multi([])
        with self.assertRaises(ValueError):
            formato.l0multi([(formato.CALIB, b"")])


if __name__ == "__main__":
    unittest.main()
