"""Lo común de los conversores de PQRS de datos.gov.co (T1.1c): lectura, licencia del `*.meta.json`, anonimizado y reparto.

Cada fuente real vive en `~/datos/datosgov/<id>.csv` + `<id>.meta.json`. Ninguna fila sin anonimizar sale de aquí:
el texto pasa por `anonimizar.anonimizar` antes de construir la fila.
"""
import collections
import csv
import hashlib
import json
import re
from pathlib import Path

from . import anonimizar
from .comun import FuenteAusente, fila
from .libres import normalizar

DATOSGOV = Path.home() / "datos" / "datosgov"
TIPOS = ["peticion", "queja", "reclamo", "sugerencia", "denuncia", "felicitacion"]
PREGUNTA_TIPO = "¿Qué tipo de solicitud ciudadana es el mensaje?"
DESCRIPCIONES_TIPO = {
    "peticion": "petición: la persona pide información, un documento, una gestión o una acción de la entidad",
    "queja": "queja: la persona se molesta por la conducta o la atención de un funcionario o del servicio",
    "reclamo": "reclamo: la persona exige que se corrija o se compense una falla, un cobro o un derecho incumplido",
    "sugerencia": "sugerencia: la persona propone una mejora o una idea para la entidad o el servicio",
    "denuncia": "denuncia: la persona informa de una irregularidad, un delito o un acto de corrupción",
    "felicitacion": "felicitación: la persona agradece o reconoce el buen servicio o a un funcionario",
}
LICENCIAS_META = {"CC_40_BY_SA": ("cc-by-sa-4.0", "by-sa/4.0"), "CC_40_BY": ("cc-by-4.0", "by/4.0")}


def leer_fuente(raiz, id_fuente):
    """(filas del CSV, meta.json) de una fuente de datos.gov.co; FuenteAusente si no están."""
    raiz = Path(raiz or DATOSGOV)
    csv_p, meta_p = raiz / (id_fuente + ".csv"), raiz / (id_fuente + ".meta.json")
    if not csv_p.is_file() or not meta_p.is_file():
        raise FuenteAusente("datos.gov.co " + id_fuente)
    with open(csv_p, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.DictReader(fh))
    with open(meta_p, encoding="utf-8") as fh:
        return filas, json.load(fh)


def licencia_meta(meta):
    """(licencia, uso_comercial) desde `licenseId` y confirmada con el enlace de términos; si no, «sin verificar»."""
    lid = meta.get("licenseId")
    enlace = (meta.get("license") or {}).get("termsLink", "")
    if lid in LICENCIAS_META and LICENCIAS_META[lid][1] in enlace:
        return LICENCIAS_META[lid][0], True
    return "sin verificar (meta.json: %s %s)" % (lid, enlace), False


def construir(corto, fuente, lic, com, tarea, pregunta, opciones, descripciones, registros, idioma="es-CO",
              sal="pqrs", vocabulario=True):
    """registros = [(texto original, etiqueta, nombres_extra)] -> (filas, info).

    Anonimiza, descarta textos vacíos o muy cortos, agrupa los textos idénticos (misma `plantilla`, todos en el
    mismo split). Por decisión de Juan, todas las PQRS de datos.gov.co van solo a `test` con `uso_comercial=False`
    (conservan ~1 nombre visible por cada 300 filas): `com` del `meta.json` se ignora.
    """
    com = False
    cuentas = collections.Counter()
    descartes = collections.Counter()
    filas_ok = []
    limpios = [re.sub(r"\s+", " ", r[0] or "").strip() for r in registros]
    voc = anonimizar.vocabulario_de(limpios) if vocabulario else None
    estricto = anonimizar.vocabulario_de(limpios, min_df=5) if vocabulario else None
    for limpio, (_, etiqueta, extra) in zip(limpios, registros):
        t, c = anonimizar.anonimizar(limpio, extra, voc, estricto)
        if len(re.sub(r"\[[A-Z]+\]|\W", "", t)) < 3:
            descartes["texto_vacio_o_solo_datos"] += 1
            continue
        cuentas.update(c)
        filas_ok.append((t, etiqueta))
    grupos = collections.defaultdict(list)
    for t, e in filas_ok:
        grupos[normalizar(t)].append(e)
    plantilla = {k: "%s-%s" % (corto, hashlib.sha1(k.encode("utf-8")).hexdigest()[:10]) for k in grupos}
    cont = collections.Counter()
    filas = []
    for t, e in filas_ok:
        k = normalizar(t)
        sp = "test"
        n = cont[sp]
        cont[sp] += 1
        filas.append(fila(corto, sp, n, tarea=tarea, tipo="choice", pregunta=pregunta, texto=t,
                          opciones=opciones, descripciones=descripciones, etiqueta=e, idioma=idioma,
                          fuente=fuente, licencia=lic, uso_comercial=com, plantilla=plantilla[k]))
    info = {"licencia": lic, "reemplazos": dict(cuentas), "descartadas": dict(descartes),
            "textos_distintos": len(grupos),
            "uso_comercial": "false por decisión de Juan (todo a test)"}
    return filas, info
