import os
import re
import subprocess
import unittest

AQUI = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROHIBIDO = re.compile("tet" "ris|tet" "romin", re.I)


class TestHigiene(unittest.TestCase):
    def test_sin_referencias_a_juegos_clasicos(self):
        malos = []
        for base, dirs, ficheros in os.walk(AQUI):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".pytest_cache")]
            for f in ficheros:
                if f.endswith((".pyc", ".mp4")):
                    continue
                with open(os.path.join(base, f), encoding="utf-8", errors="ignore") as fh:
                    lineas = fh.readlines()
                for n, linea in enumerate(lineas, 1):
                    if PROHIBIDO.search(linea):
                        malos.append(f"{f}:{n}")
        # el README puede tener UNA sola frase que diga que no es un clon
        self.assertLessEqual(len(malos), 1, malos)
        self.assertTrue(all(m.startswith("README.md") for m in malos), malos)


if __name__ == "__main__":
    unittest.main()
