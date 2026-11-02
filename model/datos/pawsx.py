"""PAWS-X es (google-research-datasets/paws-x, `es/`): ¿son paráfrasis las dos frases?, `parafrasis` `noul` (false/true).

La tarjeta declara `license: other` y el cuerpo dice «may be freely used for any purpose»: se acepta como uso comercial solo si el
cuerpo de la tarjeta trae esa frase; si no, queda «sin verificar» y solo test. Splits de origen: train, validation (dev), test.
El `test` es el de M4 (`model.l2.espanol`): sale como `test` y nunca entra en train.
"""
from pathlib import Path

from .comun import leer_split, numerar, raiz_hf, tarjeta

REPO = "google-research-datasets/paws-x"
CORTO = "pawsx"
LICENCIA = "libre para cualquier uso (Google LLC, tarjeta: license other)"
FRASE_TARJETA = "may be freely used for any purpose"
PREGUNTA = "¿Las dos frases significan lo mismo?"
DESCRIPCIONES = {"false": "las frases dicen cosas distintas, aunque usen casi las mismas palabras",
                 "true": "las frases son paráfrasis una de otra"}
OPCIONES = ["false", "true"]
SPLIT_ORIGEN = {"train": "train", "dev": "validation", "test": "test"}


def _licencia(raiz):
    cuerpo = (raiz / "README.md").read_text(encoding="utf-8") if (raiz / "README.md").is_file() else ""
    if tarjeta(raiz).get("license") in (["other"], "other") and FRASE_TARJETA in " ".join(cuerpo.split()):
        return LICENCIA, True
    return "sin verificar (la tarjeta no confirma el uso libre)", False


def convertir(raiz=None):
    raiz = Path(raiz or raiz_hf(REPO))
    lic, com = _licencia(raiz)
    items = []
    for split in SPLIT_ORIGEN:
        for r in leer_split(raiz, split, "es"):
            items.append((split, dict(
                tarea="parafrasis", tipo="noul", pregunta=PREGUNTA,
                texto="Frase 1: %s\nFrase 2: %s" % (r["sentence1"], r["sentence2"]), opciones=OPCIONES, descripciones=DESCRIPCIONES,
                etiqueta="true" if int(r["label"]) == 1 else "false", idioma="es", fuente=REPO + " es " + SPLIT_ORIGEN[split],
                licencia=lic, uso_comercial=com)))
    filas, desc = numerar(CORTO, items)
    return filas, {"licencia": lic, "descartadas_nc": desc}
