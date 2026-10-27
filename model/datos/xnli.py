"""XNLI es (CC-BY-NC): inferencia `entailment`/`neutral`/`contradiction`. Solo `test`, `uso_comercial: false`.

Formato documentado: HF `es/test-*.parquet` con `premise,hypothesis,label` (0 entailment, 1 neutral,
2 contradiction). `train` y `validation` no se emiten: la licencia NC solo permite evaluar.
"""
from .comun import etiqueta_de, leer_split, numerar, raiz_hf

REPO = "facebook/xnli"
CORTO = "xnli"
LICENCIA = "CC-BY-NC-4.0"
PREGUNTA = "¿Qué relación hay entre la premisa y la hipótesis?"
OPCIONES = ["entailment", "neutral", "contradiction"]
DESCRIPCIONES = {
    "entailment": "la hipótesis se deduce de la premisa",
    "neutral": "la premisa no permite afirmar ni negar la hipótesis",
    "contradiction": "la hipótesis contradice la premisa",
}


def convertir(raiz=None):
    raiz = raiz or raiz_hf(REPO)
    items = []
    for r in leer_split(raiz, "test", "es"):
        items.append(("test", dict(
            tarea="nli", tipo="choice", pregunta=PREGUNTA,
            texto="Premisa: %s\nHipótesis: %s" % (r["premise"], r["hypothesis"]), opciones=OPCIONES,
            descripciones=DESCRIPCIONES, etiqueta=etiqueta_de(r, OPCIONES), idioma="es",
            fuente=REPO + " es test", licencia=LICENCIA, uso_comercial=False)))
    filas, desc = numerar(CORTO, items)
    return filas, {"descartadas_nc": desc, "licencia": LICENCIA}
