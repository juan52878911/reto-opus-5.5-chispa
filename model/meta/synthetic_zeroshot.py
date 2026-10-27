"""MoritzLaurer/synthetic_zeroshot_mixtral_v0.1 (apache-2.0) -> esquema de Chispa.

Cada fila de origen es un par (`text`, `hypothesis`) con `labels` 0 = la hipótesis se cumple (entailment) y
1 = no se cumple. Se lleva a `noul`: la hipótesis es la pregunta y la etiqueta es `true` si labels == 0.
Las descripciones de etiqueta son las que trae la fila: la hipótesis (`true`) y su negación (`false`).
Idioma `en`: la traducción al español va después, aparte.
Las siete configs cuentan como tareas distintas (`synthetic_zeroshot/<config>`). El reparto es por texto
(`plantilla` = hash del texto), para que todas las hipótesis de un mismo texto caigan en el mismo split.
"""
import hashlib
from pathlib import Path

from .comun import Numerador, leer_tabla, licencia_tarjeta, raiz_hf, split_por_clave

REPO = "MoritzLaurer/synthetic_zeroshot_mixtral_v0.1"
CORTO = "synzs"
CONFIGS = (
    "mixtral_refinedweb_categories", "mixtral_refinedweb_characteristics", "mixtral_refinedweb_nli",
    "mixtral_written_texts_for_tasks", "mixtral_written_texts_for_tasks_v2",
    "mixtral_written_texts_for_tasks_v3", "mixtral_written_texts_for_tasks_v4",
)
LICENCIA = "apache-2.0"


def _lotes(ruta):
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(ruta)
    cols = [c for c in ("hypothesis", "text", "labels") if c in pf.schema_arrow.names]
    for lote in pf.iter_batches(batch_size=5000, columns=cols):
        yield from lote.to_pylist()


def filas(raiz=None, info=None, tope=None, configs=CONFIGS):
    raiz = Path(raiz) if raiz else raiz_hf(REPO)
    info = info if info is not None else {}
    leida = licencia_tarjeta(raiz)
    com = leida == LICENCIA
    lic = LICENCIA if com else "sin verificar (tarjeta: %s; se esperaba %s)" % (leida or "sin licencia", LICENCIA)
    info["licencia"] = lic
    num = Numerador(CORTO)
    emitidas = 0
    for cfg in configs:
        for ruta in sorted((raiz / cfg).glob("*.parquet")):
            for r in _lotes(ruta):
                if tope is not None and emitidas >= tope:
                    return
                texto, hip = r.get("text"), r.get("hypothesis")
                try:
                    lab = int(r.get("labels"))
                except (TypeError, ValueError):
                    lab = None
                if not isinstance(texto, str) or not texto.strip() or not isinstance(hip, str) or not hip.strip() \
                        or lab not in (0, 1):
                    info["descartadas_invalidas"] = info.get("descartadas_invalidas", 0) + 1
                    continue
                plantilla = hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]
                split = split_por_clave(plantilla, p_dev=0.01, p_test=0.01, sal=CORTO)
                f = num.numerar(split, dict(
                    tarea="synthetic_zeroshot/" + cfg.replace("mixtral_", "", 1), tipo="noul", pregunta=hip, texto=texto,
                    opciones=["false", "true"],
                    descripciones={"false": "false: not (%s)" % hip, "true": "true: " + hip},
                    etiqueta="true" if lab == 0 else "false", idioma="en", fuente="%s %s" % (REPO, cfg),
                    licencia=lic, plantilla=plantilla), com)
                if f is None:
                    continue
                emitidas += 1
                yield f
    info["descartadas_licencia_nc_fuera_de_test"] = num.descartadas_nc


def convertir(raiz=None, **kw):
    info = {}
    return list(filas(raiz, info, **kw)), info
