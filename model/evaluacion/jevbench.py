"""Adaptador de JevBench detrás de una interfaz. La API de Jev no es alcanzable desde la VM: aquí solo se lee un
volcado local. Forma documentada del volcado (JSONL, una caso por línea; la inventamos hasta ver el real):

    {"caso": "jev-0001", "dimension": "intencion", "pregunta": "...", "mensaje": "...",
     "opciones": ["a", "b"], "descripciones": {"a": "...", "b": "..."}, "oro": "a", "idioma": "es-CO"}

Se convierte a filas de model/esquema.md con split `test`, `uso_comercial` false (hasta conocer la licencia).
Cuando exista el formato real, se cambia solo `_a_fila`, o se registra otra fuente con `FUENTES`.
"""
import json


def _a_fila(c):
    for k in ("caso", "dimension", "mensaje", "opciones", "oro"):
        if k not in c:
            raise ValueError(f"caso JevBench {c.get('caso', '?')}: falta '{k}'")
    return {
        "id": f"jev:test:{c['caso']}", "tarea": c["dimension"], "tipo": "choice",
        "pregunta": c.get("pregunta", ""), "texto": c["mensaje"], "opciones": list(c["opciones"]),
        "descripciones": c.get("descripciones", {}), "etiqueta": c["oro"], "idioma": c.get("idioma", "es"),
        "split": "test", "fuente": "JevBench", "licencia": "desconocida", "uso_comercial": False,
    }


def cargar_jevbench(ruta):
    """ruta de un volcado local -> lista de filas del esquema."""
    with open(ruta, encoding="utf-8") as f:
        return [_a_fila(json.loads(l)) for l in f if l.strip()]
