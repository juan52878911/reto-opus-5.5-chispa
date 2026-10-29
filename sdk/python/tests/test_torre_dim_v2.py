import struct
import unittest
from pathlib import Path

from chispa import formato
from chispa.cliente import ChispaError
from chispa.torre import comprobar_dim_l2

FIXTURE = Path(__file__).resolve().parents[3] / "server" / "decide" / "testdata" / "conj-v2.chispa"


class TestDimTorreConEsquemasV2(unittest.TestCase):
    def test_v1_y_v2_leen_la_misma_dim(self):
        for u in (256, (2 << 16) | 256):
            comprobar_dim_l2({formato.ESQUEMAS: struct.pack("<II", u, 0)}, 256)
        with self.assertRaises(ChispaError):
            comprobar_dim_l2({formato.ESQUEMAS: struct.pack("<II", (2 << 16) | 256, 0)}, 384)

    def test_version_desconocida(self):
        with self.assertRaises(ChispaError):
            comprobar_dim_l2({formato.ESQUEMAS: struct.pack("<II", (7 << 16) | 256, 0)}, 256)

    def test_version_1_en_bits_altos_se_rechaza(self):
        with self.assertRaises(ChispaError):
            comprobar_dim_l2({formato.ESQUEMAS: struct.pack("<II", (1 << 16) | 256, 0)}, 256)

    def test_ablacion_rechaza_version_1_en_bits_altos(self):
        import importlib.util
        ab = Path(__file__).resolve().parents[3] / "server" / "deploy" / "ablacion" / "ablacion.py"
        try:
            spec = importlib.util.spec_from_file_location("ablacion", ab)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
        except ImportError:
            self.skipTest("ablacion.py no importable aquí")
        with self.assertRaises(ValueError):
            m.leer_esquemas(struct.pack("<II", (1 << 16) | 4, 0))

    @unittest.skipUnless(FIXTURE.exists(), "falta el fixture conj-v2.chispa")
    def test_fixture_v2_real(self):
        secs = formato.leer(FIXTURE.read_bytes())
        self.assertEqual(formato.version_esquemas(secs[formato.ESQUEMAS]), 2)
        dim = struct.unpack("<I", secs[formato.ESQUEMAS][:4])[0] & 0xFFFF
        comprobar_dim_l2(secs, dim)


if __name__ == "__main__":
    unittest.main()
