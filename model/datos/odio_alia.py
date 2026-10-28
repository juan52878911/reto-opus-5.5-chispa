"""ALIA-es-discriminative-hate-speech (SINAI): `odio`, `noul` (true = discurso de odio).

Etiqueta = `foe_class` (fusión de tres LLM). Las 3000 filas de la muestra humana (3 anotadores de Prolific) van a
`test`, con `anotadores=3`, `blanda` = proporción de votos y la mayoría humana como etiqueta. El resto se reparte
80/10/10 por hash del id. Se lee el JSONL en flujo (419 MB) y solo se guardan los campos útiles.
"""
import json
from pathlib import Path

from .comun import fila, raiz_hf, split_por_clave
from .libres import licencia_estricta, normalizar

REPO = "SINAI/ALIA-es-discriminative-hate-speech"
CORTO = "alia-odio"
PRINCIPAL = "ALIA-es-discriminative-hate-speech.jsonl"
HUMANA = "ALIA-es-discriminative-hate-speech-human-sample.jsonl"
PREGUNTA = "¿El comentario contiene discurso de odio contra una persona o un grupo?"
DESCRIPCIONES = {
    "false": "comentario sin discurso de odio: opinión, broma o insulto que no ataca a un grupo protegido",
    "true": "comentario con discurso de odio: ataca, degrada o excluye a una persona o grupo por su origen, religión, género u otro rasgo",
}


def _lineas(path):
    with open(path, encoding="utf-8") as fh:
        for l in fh:
            if l.strip():
                yield json.loads(l)


def convertir(raiz=None):
    raiz = Path(raiz or raiz_hf(REPO))
    lic, com = licencia_estricta(raiz, ("cc-by-4.0",), "cc-by-4.0")
    humanas = {}
    for r in _lineas(raiz / HUMANA):
        votos = [int(r["annotator_%d" % i]) for i in (1, 2, 3)]
        humanas[r["id"]] = votos
    vistos, filas, cont, dup = set(), [], {}, 0
    # primero las humanas (ganan a un duplicado exacto), luego el resto en el orden del fichero
    registros = []
    for r in _lineas(raiz / PRINCIPAL):
        registros.append((r["id"] in humanas, r["id"], r["text"], r["foe_class"], r.get("source")))
    registros.sort(key=lambda x: not x[0])
    for humana, rid, texto, clase, origen in registros:
        k = normalizar(texto)
        if not k or k in vistos:
            dup += 1
            continue
        vistos.add(k)
        if humana:
            v = humanas[rid]
            split, etq = "test", "true" if sum(v) * 2 > len(v) else "false"
            extra = {"anotadores": 3, "blanda": {"false": (3 - sum(v)) / 3.0, "true": sum(v) / 3.0}}
        else:
            split, etq = split_por_clave(rid, 0.1, 0.1, "alia-odio"), "true" if int(clase) == 1 else "false"
            extra = {}
        n = cont.get(split, 0)
        cont[split] = n + 1
        f = fila(CORTO, split, n, tarea="odio", tipo="noul", pregunta=PREGUNTA, texto=texto, opciones=["false", "true"],
                 descripciones=DESCRIPCIONES, etiqueta=etq, idioma="es", fuente=REPO + (" human-sample" if humana else " train"),
                 licencia=lic, uso_comercial=com)
        f.update(extra)
        filas.append(f)
    return filas, {"licencia": lic, "duplicados_descartados": dup, "filas_humanas_en_test": sum(1 for x in filas if "anotadores" in x),
                   "etiquetas": "foe_class (LLM) salvo la muestra humana"}
