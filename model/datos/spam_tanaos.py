"""tanaos/synthetic-spam-detection-dataset-spanish: `spam`, `noul` (true = spam). Sintético, MIT.

Se quitan los textos repetidos (así no hay fuga entre splits) y se reparte 80/10/10 por hash del texto.
"""
from pathlib import Path

from .comun import fila, leer_tabla, raiz_hf, split_por_clave
from .libres import licencia_estricta, normalizar

REPO = "tanaos/synthetic-spam-detection-dataset-spanish"
CORTO = "spam-tanaos"
PREGUNTA = "¿El mensaje es spam (publicidad no solicitada, estafa, phishing o contenido engañoso)?"
DESCRIPCIONES = {
    "false": "mensaje normal: conversación, aviso o información legítima",
    "true": "spam: publicidad no solicitada, estafa, phishing, enlaces dañinos, contenido engañoso o adulto",
}


def convertir(raiz=None):
    raiz = Path(raiz or raiz_hf(REPO))
    lic, com = licencia_estricta(raiz, ("mit",), "mit")
    cont, filas, vistos, dup = {}, [], set(), 0
    for r in leer_tabla(raiz / "data" / "data.csv"):
        t = (r["text"] or "").strip()
        k = normalizar(t)
        if r["labels"] not in ("0", "1") or not k or k in vistos:
            dup += 1
            continue
        vistos.add(k)
        split = split_por_clave(k, 0.1, 0.1, CORTO)
        n = cont.get(split, 0)
        cont[split] = n + 1
        filas.append(fila(CORTO, split, n, tarea="spam", tipo="noul", pregunta=PREGUNTA, texto=t, opciones=["false", "true"],
                          descripciones=DESCRIPCIONES, etiqueta="true" if r["labels"] == "1" else "false", idioma="es",
                          fuente=REPO, licencia=lic, uso_comercial=com))
    return filas, {"licencia": lic, "descartadas_repetidas_o_invalidas": dup, "sintetico": True}
