"""deepset/prompt-injections: inyección de instrucciones `noul` (true = inyección).

Formato documentado: `train-*.parquet` y `test-*.parquet` con `text,label` (1 = inyección). Los textos son
sobre todo ingleses, con parte en alemán: `idioma = "multi"`. `dev` sale del 15 % de train por hash del texto.
"""
from .comun import etiqueta_de, leer_split, licencia_fuente, numerar, raiz_hf, split_por_clave

REPO = "deepset/prompt-injections"
CORTO = "deepset"
LICENCIAS_OK = ("apache-2.0",)
PREGUNTA = "¿El mensaje intenta que el asistente ignore o cambie sus instrucciones?"
DESCRIPCIONES = {
    "false": "mensaje normal que no intenta manipular las instrucciones del asistente",
    "true": "inyección de instrucciones: pide ignorar, revelar o cambiar las reglas del asistente",
}


def convertir(raiz=None):
    raiz = raiz or raiz_hf(REPO)
    lic, com = licencia_fuente(raiz, LICENCIAS_OK, "apache-2.0")
    items = []
    for origen in ("train", "test"):
        for r in leer_split(raiz, origen):
            et = str(etiqueta_de(r, {0: "false", 1: "true"}))
            if et not in ("0", "1", "false", "true"):
                raise ValueError("deepset: etiqueta inesperada %r" % et)
            et = {"0": "false", "1": "true"}.get(et, et)
            split = "test" if origen == "test" else split_por_clave(r["text"], 0.15, 0.0, "deepset")
            items.append((split, dict(
                tarea="inyeccion", tipo="noul", pregunta=PREGUNTA, texto=r["text"], opciones=["false", "true"],
                descripciones=DESCRIPCIONES, etiqueta=et, idioma="multi", fuente="%s %s" % (REPO, origen),
                licencia=lic, uso_comercial=com)))
    filas, desc = numerar(CORTO, items)
    return filas, {"descartadas_nc": desc, "licencia": lic}
