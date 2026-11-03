"""El texto de torre por defecto es v1 (con id), decisión del 2026-11-03: v2_sin_id solo si se pide explícitamente.
Lee el código con `ast` (sin importar torch) para que corra también donde no está instalado."""
import ast
import unittest
from pathlib import Path

L2 = Path(__file__).resolve().parents[1]


def defectos(fichero: str, funcion: str) -> dict:
    """{parámetro: valor por defecto literal} de `funcion` (o `Clase.metodo`) en `fichero`."""
    arbol = ast.parse((L2 / fichero).read_text(encoding="utf-8"))
    partes = funcion.split(".")
    nodos = arbol.body
    for p in partes:
        nodo = next(n for n in nodos if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == p)
        nodos = nodo.body
    a = nodo.args
    pos = a.args[len(a.args) - len(a.defaults):]
    out = {x.arg: ast.literal_eval(d) for x, d in zip(pos, a.defaults)}
    out.update({x.arg: ast.literal_eval(d) for x, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None})
    return out


class TextoTorreDefecto(unittest.TestCase):
    def test_modelo_nuevo_es_v1(self):
        self.assertEqual(defectos("modelo.py", "ModeloL2.__init__")["texto_torre"], "v1")

    def test_exportador_es_v1(self):
        for f, p in (("texto_torre_consulta", "version"), ("meta_torre", "texto_torre"), ("textos_torre", "version"),
                     ("meta_de", "texto_torre"), ("exportar_l2", "texto_torre")):
            try:
                d = defectos("exportar.py", f)
            except StopIteration:
                continue
            if p in d:
                self.assertEqual(d[p], "v1", f)
        fuente = (L2 / "exportar.py").read_text(encoding="utf-8")
        self.assertIn('if texto_torre != "v1":  # falta = "v1"', fuente)  # META sin campo = v1

    def test_entrenar_sin_flag_resuelve_v1(self):
        fuente = (L2 / "entrenar.py").read_text(encoding="utf-8")
        self.assertIn('texto_torre=a.texto_torre or "v1"', fuente)
        self.assertIn('ck.get("texto_torre", "v1")', fuente)
        self.assertIn('"--texto-torre", choices=TEXTOS_TORRE, default=None', fuente)


if __name__ == "__main__":
    unittest.main()
