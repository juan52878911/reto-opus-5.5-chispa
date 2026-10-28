"""Seguimiento de PQRSD del Concejo de Pereira (datos.gov.co xtj2-ipwy): `pqrs`, tipo desde las columnas SI/NO."""
from .pqrs_comun import DESCRIPCIONES_TIPO, PREGUNTA_TIPO, TIPOS, construir, leer_fuente, licencia_meta

ID = "xtj2-ipwy"
CORTO = "pqrs-xtj2"
# Una columna por tipo con SI/NO; «Solicitud» se cuenta como petición. Sin ninguna marca, o con tipos distintos
# marcados a la vez, la fila se descarta. El nombre del peticionario se usa para enmascarar el texto y no se guarda.
COLUMNAS = {"Peticion": "peticion", "Solicitud": "peticion", "Queja": "queja", "Reclamo": "reclamo",
            "Sugerencia": "sugerencia", "Denuncia": "denuncia", "Felicitación": "felicitacion"}


def _si(v):
    return (v or "").strip().upper() in ("SI", "SÍ", "TRUE")


def convertir(raiz=None):
    filas, meta = leer_fuente(raiz, ID)
    lic, com = licencia_meta(meta)
    regs, sin_tipo, ambiguas = [], 0, 0
    for r in filas:
        tipos = {t for c, t in COLUMNAS.items() if _si(r.get(c))}
        if not tipos:
            sin_tipo += 1
            continue
        if len(tipos) > 1:
            ambiguas += 1
            continue
        regs.append((r["RESUMEN INFORMACIÓN SOLICITADA"], tipos.pop(), [r.get("NOMBRE DEL PETICIONARIO", "")]))
    out, info = construir(CORTO, "datos.gov.co " + ID, lic, com, "pqrs", PREGUNTA_TIPO, TIPOS, DESCRIPCIONES_TIPO, regs)
    info["sin_tipo_descartadas"] = sin_tipo
    info["varios_tipos_descartadas"] = ambiguas
    return out, info
