"""SIB-200 es (Davlan/sib200, `data/spa_Latn`): tema de un texto de noticias, 7 clases, `tema` `choice`.

La tarjeta declara `cc-by-sa-4.0` y en el cuerpo «CC 4.0 Commercial»: uso comercial permitido, con la condición SA (compartir igual)
que Juan tiene aún por decidir (ver LICENCIAS.md). Mientras no decida, **solo test**: `COMERCIAL = False` (2026-11-03; antes entraba en
train y por eso G.8, el ajuste 1, v2 y v3 no son publicables bajo Apache, ver `model/datos/pesos-licencias.md`).
Splits de origen: train, dev, test. El `test` es el de M4 (`model.l2.espanol`): sale como `test` y nunca entra en train.
La pregunta, las opciones y las descripciones son las mismas que usa M4 (un test lo comprueba).
"""
from pathlib import Path

from .comun import etiqueta_de, leer_tabla, licencia_fuente, numerar, raiz_hf

REPO = "Davlan/sib200"
CORTO = "sib200"
LICENCIAS_OK = ("cc-by-sa-4.0",)
COMERCIAL = False  # SA sin decidir: solo test (las filas no comerciales fuera de test se descartan en `numerar`)
PREGUNTA = "¿De qué tema trata el texto?"
DESCRIPCIONES = {"science/technology": "ciencia o tecnología", "travel": "viajes y turismo", "politics": "política",
                 "sports": "deportes", "health": "salud y medicina", "entertainment": "entretenimiento, cine, música o famosos",
                 "geography": "geografía y lugares"}
OPCIONES = sorted(DESCRIPCIONES)
SPLIT_ORIGEN = {"train": "train", "dev": "dev", "test": "test"}


def convertir(raiz=None):
    raiz = Path(raiz or raiz_hf(REPO))
    lic, com = licencia_fuente(raiz, LICENCIAS_OK, "CC-BY-SA-4.0", COMERCIAL)
    items = []
    for split, fichero in SPLIT_ORIGEN.items():
        p = raiz / "data" / "spa_Latn" / (fichero + ".tsv")
        if not p.is_file():
            continue
        for r in leer_tabla(p):
            if r["category"] not in DESCRIPCIONES:
                continue
            items.append((split, dict(
                tarea="tema", tipo="choice", pregunta=PREGUNTA, texto=r["text"], opciones=OPCIONES, descripciones=DESCRIPCIONES,
                etiqueta=etiqueta_de(r), idioma="es", fuente=REPO + " spa_Latn " + fichero, licencia=lic, uso_comercial=com)))
    filas, desc = numerar(CORTO, items)
    return filas, {"licencia": lic, "descartadas_nc": desc}
