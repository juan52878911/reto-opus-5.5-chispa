"""Genera score_orden.json con model/l2/modelo.py (solo lectura): el nivel que Python usa como consulta de score en cada orden.

Uso: python3 -I testdata/gen_score_orden.py > testdata/score_orden.json   (desde server/decide, con la raíz del repo en ../..)
torch no hace falta: texto_consulta es puro; se sustituye torch por un módulo vacío solo para poder importar el fichero.
"""
import json, os, sys, types
from unittest import mock

for m in ("torch", "torch.nn", "torch.nn.functional"):
    sys.modules[m] = mock.MagicMock()
sys.modules["torch.nn"].Module = object
raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(raiz, "model", "l2"))
import modelo  # noqa: E402

casos = {
    "1..3 en orden": ["1", "2", "3"],
    "1..3 permutado": ["3", "1", "2"],
    "1..12 en orden": [str(i) for i in range(1, 13)],
    "1..12 permutado": ["10", "2", "12", "1", "7", "3", "11", "5", "9", "4", "8", "6"],
    "1..10 invertido": [str(i) for i in range(10, 0, -1)],
    "no numéricos": ["bajo", "medio", "alto"],
    "mezcla": ["1", "dos", "3"],
}
out = []
for nombre, ops in casos.items():
    fila = {"pregunta": "Gravedad", "tipo": "score", "opciones": ops, "descripciones": {}}
    try:
        texto = modelo.texto_consulta(fila)
        nivel = texto.split(modelo.SEP)[1]
        out.append({"caso": nombre, "opciones": ops, "consulta": nivel, "error": False})
    except ValueError:
        out.append({"caso": nombre, "opciones": ops, "consulta": "", "error": True})
print(json.dumps(out, ensure_ascii=False, indent=1))
