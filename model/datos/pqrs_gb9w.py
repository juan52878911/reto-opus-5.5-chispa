"""PQRSD de la Alcaldía de Flandes, Tolima (datos.gov.co gb9w-jt96): `pqrs`, tipo desde «Tipo de solicitud»."""
from .pqrs_comun import DESCRIPCIONES_TIPO, PREGUNTA_TIPO, TIPOS, construir, leer_fuente, licencia_meta

ID = "gb9w-jt96"
CORTO = "pqrs-gb9w"
# Mapeo del campo «Tipo de solicitud». Lo que no es un tipo de PQRS (agendar cita) se descarta.
MAPEO = {"sugerencia": "sugerencia", "peticion": "peticion", "solicitud de informacion": "peticion",
         "reclamo": "reclamo", "queja": "queja", "denuncia": "denuncia", "solicitud de datos personales": "peticion"}


def convertir(raiz=None):
    from .libres import normalizar
    filas, meta = leer_fuente(raiz, ID)
    lic, com = licencia_meta(meta)
    regs, sin_mapeo = [], {}
    for r in filas:
        k = normalizar(r["Tipo de solicitud"])
        if k not in MAPEO:
            sin_mapeo[k] = sin_mapeo.get(k, 0) + 1
            continue
        regs.append((r["Descripción de la solicitud"], MAPEO[k], ()))
    out, info = construir(CORTO, "datos.gov.co " + ID, lic, com, "pqrs", PREGUNTA_TIPO, TIPOS, DESCRIPCIONES_TIPO, regs)
    info["sin_mapeo_descartadas"] = sin_mapeo
    return out, info
