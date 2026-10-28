import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

from model.l2 import datos as D
from model.l2 import entrenar
from model.l2.tests.falso import CodificadorFalso, fila


def escribir(ruta, filas):
    with open(ruta, "w", encoding="utf-8") as f:
        for r in filas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class Reanudar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        filas = [fila(i, "choice", 4, "a") for i in range(30)] + [fila(100 + i, "noul", tarea="b") for i in range(20)] \
            + [fila(200 + i, "score", tarea="c", k=4) for i in range(10)]
        escribir(self.dir / "d.jsonl", filas)

    def tearDown(self):
        self.tmp.cleanup()

    def correr(self, salida, caer_en=None, extra=()):
        enc = CodificadorFalso(caer_en)
        with mock.patch.object(entrenar, "Codificador", lambda **kw: enc):
            return entrenar.main(["--salida", str(self.dir / salida), "--datos", str(self.dir / "d.jsonl"), "--pasos", "8", "--lote", "8",
                                  "--device", "cpu", "--ckpt-cada", "0", *extra])

    def test_reanudar_da_lo_mismo_que_no_parar(self):
        self.assertEqual(self.correr("entero"), 0)
        with self.assertRaises(RuntimeError):
            self.correr("cortado", caer_en=5)  # cae a mitad de camino; hay checkpoint de cada paso
        ck = torch.load(self.dir / "cortado" / "ultimo.pt", weights_only=False)
        self.assertTrue(0 < ck["paso"] < 8)
        self.assertEqual(self.correr("cortado"), 0)
        a = torch.load(self.dir / "entero" / "ultimo.pt", weights_only=False)
        b = torch.load(self.dir / "cortado" / "ultimo.pt", weights_only=False)
        self.assertEqual((a["paso"], b["paso"]), (8, 8))
        for k, v in a["modelo"].items():
            self.assertTrue(torch.allclose(v, b["modelo"][k], atol=1e-6), k)

    def test_s3_local(self):
        self.assertEqual(self.correr("a", extra=["--s3", str(self.dir / "nube")]), 0)
        self.assertTrue((self.dir / "nube" / "ultimo.pt").exists())
        # un directorio nuevo reanuda desde «s3»: ya está en el paso 8, no entrena más
        self.assertEqual(self.correr("b", extra=["--s3", str(self.dir / "nube")]), 0)
        self.assertEqual(torch.load(self.dir / "b" / "ultimo.pt", weights_only=False)["paso"], 8)


class DatosTest(unittest.TestCase):
    def test_gz_y_submuestreo_y_muestreo_por_tarea(self):
        import gzip
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            (t / "tsjev").mkdir()
            (t / "otra").mkdir()
            with gzip.open(t / "tsjev" / "train-00000.jsonl.gz", "wt") as f:
                for i in range(100):
                    f.write(json.dumps(fila(i, tarea="grande")) + "\n")
            with gzip.open(t / "otra" / "train-00000.jsonl.gz", "wt") as f:
                for i in range(1000):
                    f.write(json.dumps(fila(i, tarea="resto")) + "\n")
            filas, cuentas, cupo = D.submuestrear_meta(str(t), 300)
            self.assertEqual(cuentas, {"tsjev": 100, "otra": 1000})
            self.assertEqual(cupo["tsjev"], 100)
            self.assertAlmostEqual(len(filas), 300, delta=40)
            self.assertEqual(sum(r["tarea"] == "grande" for r in filas), 100)
            self.assertEqual(filas, D.submuestrear_meta(str(t), 300)[0])  # estable
        n_g, n_c = 10000, 100
        mu = D.Muestreador([fila(i, tarea="g") for i in range(n_g)] + [fila(i + n_g, tarea="c") for i in range(n_c)], lote=64)
        fr = sum(r["tarea"] == "c" for p in range(200) for r in mu.lote_paso(p)) / (200 * 64)
        self.assertAlmostEqual(fr, 10 / 110, delta=0.02)  # n^0,5: 10 de 110, no 100 de 10100
        self.assertEqual([r["id"] for r in mu.lote_paso(7)], [r["id"] for r in mu.lote_paso(7)])


if __name__ == "__main__":
    unittest.main()
