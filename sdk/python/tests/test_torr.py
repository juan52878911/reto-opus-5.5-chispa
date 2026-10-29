import struct
import unittest
from pathlib import Path

from chispa import formato

ONNX = b"ONNX-torre-falso"
TESTDATA = Path(__file__).resolve().parents[3] / "format/chispa3/testdata/torre.chispa"


def fichero() -> bytes:
    return formato.escribir({formato.META: formato.meta(["q"]), formato.CALIB: formato.calib({}, 0.5),
                             formato.TORR: formato.torr(ONNX)})


class TestTORR(unittest.TestCase):
    def test_layout(self):
        b = formato.torr(ONNX)
        self.assertEqual(b[:16].hex(), "01000000" "00010000" "80000000" "09000000")
        self.assertEqual(b[16:], b"passage: " + ONNX)

    def test_ida_y_vuelta(self):
        sec = formato.leer(fichero())
        self.assertEqual(formato.leer_torr(sec[formato.TORR]),
                         {"dim": 256, "max_len": 128, "prefijo": "passage: ", "onnx": ONNX})

    def test_max_len_menor_de_3_se_rechaza(self):
        for ml in (-1, 0, 1, 2):
            with self.assertRaises(ValueError):
                formato.torr(ONNX, max_len=ml)
        b = formato.torr(ONNX, max_len=3)
        self.assertEqual(formato.leer_torr(b)["max_len"], 3)
        for ml in (1, 2):
            with self.assertRaises(ValueError):
                formato.leer_torr(b[:8] + struct.pack("<I", ml) + b[12:])

    def test_max_len_256_y_tope(self):
        b = formato.torr(ONNX, max_len=256)
        self.assertEqual(formato.leer_torr(b)["max_len"], 256)
        self.assertEqual(formato.leer_torr(formato.torr(ONNX, max_len=512))["max_len"], 512)
        malo = b[:8] + (513).to_bytes(4, "little") + b[12:]
        with self.assertRaises(ValueError):
            formato.leer_torr(malo)

    def test_rechaza(self):
        for kw in ({"onnx": b""}, {"dim": 0}, {"max_len": 513}, {"prefijo": "x" * 257}):
            with self.assertRaises(ValueError):
                formato.torr(**{"onnx": ONNX, **kw})
        with self.assertRaises(ValueError):
            formato.leer_torr(b"\0" * 8)

    def test_el_fichero_guardado_es_el_que_se_genera(self):
        self.assertTrue(TESTDATA.is_file(), "falta " + str(TESTDATA))
        self.assertEqual(TESTDATA.read_bytes(), fichero())


if __name__ == "__main__":
    unittest.main()
