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

    def test_layout_v2(self):
        # misma cabecera que format/chispa3 (TestTORRV2Layout): versión 2 y u32 con el texto (2 = v2_sin_id) tras len_prefijo
        b = formato.torr(ONNX, texto_torre="v2_sin_id")
        self.assertEqual(b[:20].hex(), "02000000" "00010000" "80000000" "09000000" "02000000")
        self.assertEqual(b[20:], b"passage: " + ONNX)
        self.assertEqual(formato.leer_torr(b), {"dim": 256, "max_len": 128, "prefijo": "passage: ", "texto_torre": "v2_sin_id", "onnx": ONNX})
        self.assertEqual(formato.torr(ONNX, texto_torre="v1"), formato.torr(ONNX))  # v1 sigue siendo TORR v1

    def test_v2_rechazos(self):
        with self.assertRaisesRegex(ValueError, "texto_torre.*v9"):
            formato.torr(ONNX, texto_torre="v9")
        b = formato.torr(ONNX, texto_torre="v2_sin_id")
        for malo, msg in ((struct.pack("<I", 3) + b[4:], "versión desconocida"), (b[:16] + struct.pack("<I", 7) + b[20:], "texto de torre"),
                          (b[:18], "truncada")):
            with self.assertRaisesRegex(ValueError, msg):
                formato.leer_torr(malo)

    def test_ida_y_vuelta(self):
        sec = formato.leer(fichero())
        self.assertEqual(formato.leer_torr(sec[formato.TORR]),
                         {"dim": 256, "max_len": 128, "prefijo": "passage: ", "texto_torre": "v1", "onnx": ONNX})

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
