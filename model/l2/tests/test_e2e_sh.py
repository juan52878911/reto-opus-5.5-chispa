"""e2e.sh: sintaxis y número de argumentos de las llamadas a `pasada` y `diagnosticar` (un `$3` sin pasar aborta bajo `set -u`)."""
import shlex
import subprocess
import unittest
from pathlib import Path

E2E = Path(__file__).resolve().parents[2] / "bench" / "torre" / "e2e.sh"
ESPERADOS = {"pasada": 3, "diagnosticar": 3}   # nombre .chispa restantes · nombre .chispa capas
CORTES = {"&&", "||", ";", "|", "then", "fi", "else"}


def llamadas(texto):
    for i, linea in enumerate(texto.splitlines(), 1):
        if linea.lstrip().startswith("#"):
            continue
        try:
            toks = shlex.split(linea, comments=True)
        except ValueError:
            continue
        for j, t in enumerate(toks):
            if t in ESPERADOS and (j == 0 or toks[j - 1] in CORTES or toks[j - 1] == "]"):
                fin = next((k for k in range(j + 1, len(toks)) if toks[k] in CORTES), len(toks))
                yield i, t, toks[j + 1:fin]


class TestE2eSh(unittest.TestCase):
    def test_sintaxis(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(E2E)]).returncode, 0)

    def test_aridad_de_llamadas(self):
        ll = list(llamadas(E2E.read_text(encoding="utf-8")))
        self.assertGreaterEqual(len(ll), 5)   # 2 pasadas+... base, calib, calib-l2fp32 (diagnosticar) y dos pasadas
        for i, nombre, args in ll:
            self.assertEqual(len(args), ESPERADOS[nombre], "línea %d: %s con %d argumentos: %s" % (i, nombre, len(args), args))

    def test_detecta_la_llamada_mala(self):
        self.assertEqual([len(a) for _, _, a in llamadas('  pasada calib-l2fp32 1\n  x && pasada a "$B" 1\n')], [2, 3])


if __name__ == "__main__":
    unittest.main()
