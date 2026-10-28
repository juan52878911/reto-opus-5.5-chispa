"""Tests de exportar.py --vocab. `python -m unittest test_exportar -v` (los que necesitan el modelo se saltan si falta)."""
import glob
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

import exportar

MODELO = next(iter(sorted(glob.glob(os.path.expanduser("~/hf/hub/models--minishlab--potion-multilingual-128M/snapshots/*")))), None)


class RecortarIDs(unittest.TestCase):
    def test_anade_obligatorios_ordena_y_dedup(self):
        r = exportar.recortar_ids([50, 7, 7, 3], 100, {0, 1})
        self.assertEqual(r.tolist(), [0, 1, 3, 7, 50])

    def test_id_fuera_de_rango(self):
        with self.assertRaises(AssertionError):
            exportar.recortar_ids([100], 100, {0, 1})


@unittest.skipUnless(MODELO, "falta potion-multilingual-128M en ~/hf: este test NO se ha ejecutado")
class ExportarRecortado(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.ids = [0, 1, 5, 4, 2, 3934, 17553, 250919, 47956]   # incluye «hola» y «▁Hola»; desordenados y con [PAD]/[UNK]
        (t / "v.json").write_text(json.dumps({"ids_originales": cls.ids}))
        for nombre in ("a", "b"):
            exportar.main(MODELO, str(t / nombre), str(t / "v.json"))
        cls.a = (t / "a").read_bytes()
        cls.b = (t / "b").read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_determinista(self):
        self.assertEqual(self.a, self.b)

    def test_cabecera_y_tamanos(self):
        dim, n = struct.unpack_from("<2I", self.a, 12)
        self.assertEqual(dim, 256)
        self.assertEqual(n, len(set(self.ids)))
        tabla_bits, pref_bits = struct.unpack_from("<2I", self.a, 28)
        sec = [struct.unpack_from("<QQ", self.a, 36 + 16 * i) for i in range(9)]
        self.assertEqual(sec[6][1], n * dim)          # pesos
        self.assertEqual(sec[7][1], 4 * n)            # escalas
        self.assertEqual(sec[5][1], 4 << tabla_bits)  # hash
        self.assertEqual(sec[8][1], 1 << (pref_bits - 3))
        self.assertLess(len(self.a), 5 << 20)

    def test_filas_iguales_a_las_del_completo(self):
        from safetensors import safe_open
        with safe_open(Path(MODELO) / "model.safetensors", "np") as f:
            emb = f.get_tensor("embeddings")
        sec = [struct.unpack_from("<QQ", self.a, 36 + 16 * i) for i in range(9)]
        pesos = np.frombuffer(self.a, np.int8, sec[6][1], sec[6][0]).reshape(-1, 256)
        esc = np.frombuffer(self.a, "<f4", sec[7][1] // 4, sec[7][0])
        orden = sorted(set(self.ids))
        for k, o in enumerate(orden):
            self.assertAlmostEqual(float(np.abs(pesos[k].astype(np.float32) * esc[k] - emb[o]).max()), 0, delta=float(esc[k]))


if __name__ == "__main__":
    unittest.main()
