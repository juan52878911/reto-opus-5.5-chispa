"""Ejecuta los ejemplos de `ejemplos/` como procesos: zero-shot y few-shot con un L1 falso (bytes), y el cliente contra un servidor falso."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from chispa import formato
from tests.test_cliente import Falso

SDK = Path(__file__).resolve().parents[1]
EJ = SDK / "ejemplos"


def correr(script, *args):
    env = dict(os.environ, PYTHONPATH=str(SDK) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    return subprocess.run([sys.executable, str(EJ / script), *map(str, args)], capture_output=True, text=True, env=env, timeout=120)


class TestEjemplos(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "l1.bin").write_bytes(b"l1-falso")

    def test_zero_shot(self):
        r = correr("zero_shot.py", "--l1", self.d / "l1.bin", "--salida", self.d / "z.chispa")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("modo zero-shot", r.stdout)
        sec = formato.leer((self.d / "z.chispa").read_bytes())
        self.assertEqual(sec[formato.L1], b"l1-falso")
        self.assertNotIn(formato.L0, sec)

    def test_few_shot(self):
        r = correr("few_shot.py", "--l1", self.d / "l1.bin", "--salida", self.d / "f.chispa", "--sin-go")  # el L1 falso no lo calibra el entrenador
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("modo few-shot", r.stdout)
        self.assertIn("sin L0", r.stdout)
        self.assertTrue((self.d / "f.chispa").is_file())

    def test_cliente(self):
        f = Falso()
        self.addCleanup(f.cerrar)
        r = correr("cliente.py", "--url", f.url)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cotizacion (capa L0", r.stdout)
        q = f.peticiones[0]["questions"][0]
        self.assertEqual([o["id"] for o in q["options"]], ["cotizacion", "pedido", "garantia", "asesoria", "factura"])

    def test_cliente_sin_servidor(self):
        r = correr("cliente.py", "--url", "http://127.0.0.1:1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("chispa-server", r.stderr)


if __name__ == "__main__":
    unittest.main()


class TestDescripcionNull(unittest.TestCase):
    def test_descripcion_null_es_vacia(self):
        from chispa.datos import cargar_esquema
        import json, tempfile, os
        p = os.path.join(tempfile.mkdtemp(), "e.json")
        open(p, "w").write(json.dumps({"id": "t", "pregunta": "q", "tipo": "choice", "opciones": [{"id": "a", "descripcion": None}, {"id": "b"}]}))
        q, _ = cargar_esquema(p)
        self.assertEqual([(o.id, o.description) for o in q.options], [("a", ""), ("b", "")])
