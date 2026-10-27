"""HateCheck-ES (Paul/hatecheck-spanish): toxicidad `noul` (true = odio), partido por plantilla."""
from .comun import leer_tabla, licencia_fuente, numerar, raiz_hf, split_por_clave
from pathlib import Path

REPO = "Paul/hatecheck-spanish"
CORTO = "hatecheck"
LICENCIAS_OK = ("cc-by-4.0",)
PREGUNTA = "¿El mensaje contiene odio o es tóxico contra una persona o un grupo?"
DESCRIPCIONES = {
    "false": "mensaje respetuoso o no ofensivo, aunque mencione grupos o insultos sin atacar",
    "true": "mensaje de odio o tóxico contra una persona o un grupo",
}
ETIQUETA = {"hateful": "true", "non-hateful": "false"}


def convertir(raiz=None):
    """Excluye los casos con desacuerdo entre anotadores y reparte 80/10/10 por `templ_id`."""
    raiz = Path(raiz or raiz_hf(REPO))
    lic, com = licencia_fuente(raiz, LICENCIAS_OK, "cc-by-4.0")
    items, sin_acuerdo = [], 0
    for r in leer_tabla(raiz / "test.csv"):
        if str(r.get("disagreement_in_case", "")).lower() == "true":
            sin_acuerdo += 1
            continue
        plantilla = "hc-" + (r["templ_id"] or r["mhc_case_id"])
        items.append((split_por_clave(plantilla, 0.1, 0.1, "hatecheck"), dict(
            tarea="toxicidad", tipo="noul", pregunta=PREGUNTA, texto=r["test_case"],
            opciones=["false", "true"], descripciones=DESCRIPCIONES, etiqueta=ETIQUETA[r["label_gold"]],
            idioma="es", fuente=REPO + " test", licencia=lic, uso_comercial=com, plantilla=plantilla)))
    filas, desc = numerar(CORTO, items)
    return filas, {"descartadas_nc": desc, "sin_acuerdo_anotadores": sin_acuerdo, "licencia": lic}
