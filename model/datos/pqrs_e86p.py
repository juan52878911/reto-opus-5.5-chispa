"""PQRSD del Instituto Social de Vivienda de Medellín (datos.gov.co e86p-frfd): `pqrs`, tipo desde «CLASIFICACIÓN»."""
from .libres import normalizar
from .pqrs_comun import DESCRIPCIONES_TIPO, PREGUNTA_TIPO, TIPOS, construir, leer_fuente, licencia_meta

ID = "e86p-frfd"
CORTO = "pqrs-e86p"
# Mapeo de «CLASIFICACIÓN». Se descarta lo ambiguo (derecho a secas, queja-reclamo juntos), lo que no es un tipo
# (entes de control, recursos) y lo vacío.
MAPEO = {"derecho de peticion": "peticion", "solicitud de informacion": "peticion", "queja": "queja",
         "sugerencia": "sugerencia"}


def convertir(raiz=None):
    filas, meta = leer_fuente(raiz, ID)
    lic, com = licencia_meta(meta)
    regs, sin_mapeo = [], {}
    for r in filas:
        k = normalizar(r["CLASIFICACIÓN"])
        if k not in MAPEO:
            sin_mapeo[k or "(vacio)"] = sin_mapeo.get(k or "(vacio)", 0) + 1
            continue
        regs.append((r["ASUNTO"], MAPEO[k], ()))
    out, info = construir(CORTO, "datos.gov.co " + ID, lic, com, "pqrs", PREGUNTA_TIPO, TIPOS, DESCRIPCIONES_TIPO, regs)
    info["sin_mapeo_descartadas"] = sin_mapeo
    return out, info
