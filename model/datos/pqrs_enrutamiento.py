"""PQRSR de la Dirección General de Sanidad Militar (datos.gov.co m3mt-c275): `pqrs_enrutamiento`.

Texto = «Asunto»; etiqueta = «Dependencia» (las 30 más frecuentes y «otra»).
"""
import collections
import re
import unicodedata

from .libres import normalizar
from .pqrs_comun import construir, leer_fuente, licencia_meta

ID = "m3mt-c275"
CORTO = "pqrs-ruta"
MAX_CLASES = 30
PREGUNTA = "¿A qué dependencia se debe enrutar la solicitud?"


def _id(nombre):
    t = unicodedata.normalize("NFD", nombre.casefold())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")[:60] or "sin_nombre"


def convertir(raiz=None):
    filas, meta = leer_fuente(raiz, ID)
    lic, com = licencia_meta(meta)
    vistas = collections.defaultdict(collections.Counter)  # clave normalizada -> formas escritas
    for r in filas:
        d = re.sub(r"\s+", " ", r["Dependencia"]).strip()
        if d:
            vistas[normalizar(d)][d] += 1
    total = {k: sum(c.values()) for k, c in vistas.items()}
    top = [k for k, _ in sorted(total.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_CLASES]]
    ids = {k: _id(vistas[k].most_common(1)[0][0]) for k in top}
    if len(set(ids.values())) != len(ids):
        raise ValueError("ids de dependencia repetidos tras normalizar")
    opciones = [ids[k] for k in top] + ["otra"]
    desc = {ids[k]: "dependencia: " + vistas[k].most_common(1)[0][0] for k in top}
    desc["otra"] = "cualquier otra dependencia que no está entre las más frecuentes"
    regs, sin_dep = [], 0
    for r in filas:
        d = normalizar(re.sub(r"\s+", " ", r["Dependencia"]))
        if not d:
            sin_dep += 1
            continue
        regs.append((r["Asunto"], ids.get(d, "otra"), ()))
    out, info = construir(CORTO, "datos.gov.co " + ID, lic, com, "pqrs_enrutamiento", PREGUNTA, opciones, desc, regs,
                          sal="ruta", vocabulario=False)
    info["sin_dependencia_descartadas"] = sin_dep
    info["clases"] = len(opciones)
    return out, info
