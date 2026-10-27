"""PAWS-X `es` (google-research-datasets/paws-x) -> noul «¿son paráfrasis las dos frases?».

`texto` lleva las dos frases unidas con `SEPARADOR` (" [SEP] "), la marca que los codificadores BERT ya conocen y
que no aparece en el texto de PAWS-X. `label` 1 = paráfrasis (`true`), 0 = no.
Licencia: la tarjeta declara `other` y dice «may be freely used for any purpose»; solo se da por buena si la
tarjeta sigue diciéndolo (si no, `uso_comercial: false`, solo test).
"""
from .comun import Numerador, leer_tabla, licencia_tarjeta, raiz_hf

REPO = "google-research-datasets/paws-x"
CORTO = "pawsx"
SEPARADOR = " [SEP] "
PREGUNTA = "¿Son paráfrasis las dos frases?"
DESCRIPCIONES = {
    "false": "las dos frases dicen cosas distintas, aunque usen casi las mismas palabras",
    "true": "las dos frases dicen lo mismo con otras palabras (son paráfrasis)",
}
SPLIT_ORIGEN = {"train": "train", "dev": "validation", "test": "test"}
LICENCIA = "libre uso (Google PAWS-X: «freely used for any purpose»)"


def licencia(raiz):
    """(licencia, uso_comercial) según el texto de la tarjeta."""
    p = raiz / "README.md"
    txt = p.read_text(encoding="utf-8") if p.is_file() else ""
    if licencia_tarjeta(raiz) == "other" and "freely used for any purpose" in txt:
        return LICENCIA, True
    return "sin verificar (la tarjeta no confirma el libre uso)", False


def filas(raiz=None, info=None, tope=None):
    raiz = raiz or raiz_hf(REPO)
    info = info if info is not None else {}
    lic, com = licencia(raiz)
    info["licencia"] = lic
    num = Numerador(CORTO)
    emitidas = 0
    for split, nombre in SPLIT_ORIGEN.items():
        for ruta in sorted((raiz / "es").glob(nombre + "-*.parquet")):
            for r in leer_tabla(ruta):
                if tope is not None and emitidas >= tope:
                    return
                a, b = r.get("sentence1"), r.get("sentence2")
                if not isinstance(a, str) or not isinstance(b, str) or not a.strip() or not b.strip() \
                        or r.get("label") not in (0, 1):
                    info["descartadas_invalidas"] = info.get("descartadas_invalidas", 0) + 1
                    continue
                f = num.numerar(split, dict(
                    tarea="pawsx_parafrasis", tipo="noul", pregunta=PREGUNTA, texto=a.strip() + SEPARADOR + b.strip(),
                    opciones=["false", "true"], descripciones=DESCRIPCIONES,
                    etiqueta="true" if r["label"] == 1 else "false", idioma="es",
                    fuente="%s es %s" % (REPO, nombre), licencia=lic), com)
                if f is None:
                    continue
                emitidas += 1
                yield f
    info["descartadas_licencia_nc_fuera_de_test"] = num.descartadas_nc


def convertir(raiz=None, **kw):
    info = {}
    return list(filas(raiz, info, **kw)), info
