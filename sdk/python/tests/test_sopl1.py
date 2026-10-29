import unittest
from pathlib import Path

import numpy as np

from chispa import formato

TESTDATA = Path(__file__).resolve().parents[3] / "format/chispa3/testdata/soporte.chispa"
DIM = 4


def entradas():
    esc, q = formato.cuantizar_media([[0.5, -0.25, 0.0, 0.125], [0, 0, 0, 0]])
    return [{"hash": formato.clave_conj("¿p?", ["b", "a"]), "ids": ["a", "b"], "k": [3, 0], "escala": esc, "media": q}]


def fichero() -> bytes:
    return formato.escribir({formato.META: formato.meta(["q"]), formato.CALIB: formato.calib({}, 0.5),
                             formato.SOPL1: formato.sopl1(DIM, entradas())})


class TestSOPL1(unittest.TestCase):
    def test_cuantizar(self):
        esc, q = formato.cuantizar_media([[0.5, -0.25, 0.0, 0.125], [0, 0, 0, 0]])
        self.assertEqual(q.tolist(), [[127, -64, 0, 32], [0, 0, 0, 0]])  # -63,5 y 31,75 redondean a par/al más cercano
        self.assertEqual(esc.tolist(), [np.float32(0.5) / np.float32(127), 0.0])

    def test_layout(self):
        b = formato.sopl1(DIM, entradas())
        self.assertEqual(b[:12].hex(), "01000000" "04000000" "01000000")
        self.assertEqual(b[44:48].hex(), "02000000")  # C = 2 tras el hash

    def test_ida_y_vuelta(self):
        got = formato.leer_sopl1(formato.leer(fichero())[formato.SOPL1])
        e = got["entradas"][0]
        self.assertEqual((got["dim"], e["ids"], e["k"].tolist()), (DIM, ["a", "b"], [3, 0]))
        self.assertEqual(e["media"].tolist(), [[127, -64, 0, 32], [0, 0, 0, 0]])

    def test_rechaza(self):
        e = entradas()[0]
        for mal in ({"ids": ["b", "a"]}, {"k": [1]}, {"hash": b"x"}, {"media": np.zeros((2, 3), np.int8)}):
            with self.assertRaises(ValueError):
                formato.sopl1(DIM, [{**e, **mal}])
        with self.assertRaises(ValueError):
            formato.leer_sopl1(b"\0" * 8)

    def test_el_fichero_guardado_es_el_que_se_genera(self):
        self.assertTrue(TESTDATA.is_file(), "falta " + str(TESTDATA))
        self.assertEqual(TESTDATA.read_bytes(), fichero())


if __name__ == "__main__":
    unittest.main()
