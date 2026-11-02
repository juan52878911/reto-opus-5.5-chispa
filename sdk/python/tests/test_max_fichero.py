"""ZH: `chispa train` no escribe un .chispa que el servidor rechazaría por tamaño (topes pequeños de test, nada de 1 GiB)."""
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from chispa import formato
from chispa.cli import main
from chispa.cliente import ChispaError
from chispa.train import encontrar_go, entrenar

try:
    from .test_train import ESQ, ejemplos
except ImportError:  # `python -m unittest discover -s tests`: tests es el nivel superior
    from test_train import ESQ, ejemplos


class TestMaxFichero(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        (self.d / "l1.bin").write_bytes(b"l1" * 2000)  # 4000 bytes de «L1»
        with open(self.d / "ej.jsonl", "w") as f:
            for t, e in ejemplos():
                f.write(json.dumps({"texto": t, "etiqueta": e}) + "\n")
        self.salida = self.d / "s.chispa"

    def test_defecto_es_1_gib(self):
        self.assertEqual(formato.MAX_FICHERO, 1 << 30)
        self.assertEqual(formato.MAX_FICHERO_DEFECTO, 1 << 30)

    def test_escribir_rechaza_y_da_secciones(self):
        secs = {formato.L1: b"x" * 5000, formato.CALIB: b"{}"}
        self.assertTrue(formato.escribir(secs, max_fichero=1 << 20))
        with self.assertRaises(formato.ErrTamano) as cm:
            formato.escribir(secs, max_fichero=1000)
        m = str(cm.exception)
        self.assertIn("L1 5000", m)
        self.assertIn("CALIB 2", m)
        self.assertIn("--l1", m)
        self.assertIn('"max_fichero"', m)

    def _rechaza(self, **kw):
        with self.assertRaises(ChispaError) as cm:
            entrenar(self.d / "ej.jsonl", self.d / "e.json", self.salida, log=lambda m: None, **kw)
        self.assertFalse(self.salida.exists(), "no debe quedar un .chispa en la salida")
        self.assertFalse(list(self.d.glob("*.tmp")))
        return str(cm.exception)

    def test_train_sin_go_rechaza_con_tope_pequeno(self):
        m = self._rechaza(usar_go=False, max_fichero=200)
        for q in ("200 bytes", "META", "CALIB", "--l1", "--max-fichero", '"max_fichero"'):
            self.assertIn(q, m)

    def test_train_con_go_rechaza_con_tope_pequeno(self):
        if not encontrar_go():
            self.skipTest("sin Go")
        m = self._rechaza(max_fichero=1000)
        self.assertIn("1000 bytes", m)
        self.assertIn("max_fichero", m)

    def test_cota_de_l1_falla_antes_de_entrenar(self):
        m = self._rechaza(usar_go=False, l1=str(self.d / "l1.bin"), max_fichero=1000)
        self.assertIn("al menos", m)
        self.assertIn("L1 4000", m)

    def test_con_tope_suficiente_escribe_y_carga(self):
        entrenar(self.d / "ej.jsonl", self.d / "e.json", self.salida, usar_go=False, max_fichero=1 << 20, log=lambda m: None)
        self.assertIn(formato.CALIB, formato.leer(self.salida.read_bytes()))
        self.assertEqual(formato.MAX_FICHERO, 1 << 30, "el tope se restaura al terminar")

    def test_tope_no_positivo(self):
        for v in (0, -1):
            with self.assertRaises(ChispaError):
                entrenar(self.d / "ej.jsonl", self.d / "e.json", self.salida, usar_go=False, max_fichero=v)

    def test_cli_max_fichero(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = main(["train", "--esquema", str(self.d / "e.json"), "--ejemplos", str(self.d / "ej.jsonl"), "--salida", str(self.salida), "--max-fichero", "10"])
        self.assertNotEqual(rc, 0)
        self.assertIn("10 bytes", err.getvalue())
        self.assertFalse(self.salida.exists())


if __name__ == "__main__":
    unittest.main()
