"""tasksource/tasksource-instruct-v0 -> esquema de Chispa, solo las tareas comerciales (G.8).

Columnas de origen (tarjeta del dataset): `inputs` (el texto ya plantillado), `targets` (la respuesta) y `task` (la tarea, p. ej.
`glue/mnli`). El dataset no trae opciones ni licencia por fila, así que:
  - Comercial = la tarea figura con `license_use == "commercial"` en el `sources.yaml` de tasksource-jev-typed-decisions (mismo
    catálogo de tasksource) o en el fichero `CHISPA_INSTRUCT_TAREAS` (una tarea por línea; manda si existe). Sin lista, no se
    convierte nada (falla cerrado): una tarea que no consta como comercial no entra.
  - Solo clasificación: una tarea entra si sus `targets` (en train) son un vocabulario cerrado de 2 a `MAX_CLASES` valores cortos,
    cada uno visto al menos `MIN_POR_CLASE` veces. Generación libre y tareas de respuesta abierta se descartan y se cuentan.
  - tipo = choice; opciones = los targets de la tarea (orden alfabético); descripción = el propio texto; etiqueta = el target;
    pregunta = frase fija con el nombre de la tarea (sin él, el nombre no se lee en ninguna parte).
  - La tarea sale como `instruct/<tarea>` (no choca con la de tsjev, que puede cubrir el mismo origen); `tarea_base` quita ese
    prefijo para que la lista de tareas que se dejan fuera (`muestreo.py`) valga para las dos fuentes.
Dos pasadas por los parquet: vocabulario de cada tarea y emisión. Las tareas que tocan GLiClass, XNLI o ANLI se descartan.
"""
import os
from collections import Counter, defaultdict
from pathlib import Path

from model.datos.comun import ficheros_split

from .comun import Numerador, prohibida, raiz_hf
from .muestreo import PREFIJO_INSTRUCT as PREFIJO, tarea_base  # noqa: F401
from .tasksource_jev import cargar_fuentes

REPO = "tasksource/tasksource-instruct-v0"
REPO_CATALOGO = "tasksource/tasksource-jev-typed-decisions"
CORTO = "tsinst"
SPLIT_FICHERO = {"train": "train", "dev": "validation", "test": "test"}
COLUMNAS = ("inputs", "targets", "task")
MAX_CLASES = 20
MIN_POR_CLASE = 3
MAX_TARGET = 64     # caracteres de un target para que cuente como etiqueta
MAX_INPUT = 4000    # caracteres: más largo que esto no cabe en 256 tokens de ningún modo
TOPE_TAREA = 5000   # filas por tarea y split en la conversión (el tope fino lo pone el muestreo)


def tareas_comerciales(raiz_catalogo=None, ruta=None):
    """Conjunto de tareas comerciales: del fichero `ruta` / `$CHISPA_INSTRUCT_TAREAS` si existe, si no del `sources.yaml`."""
    ruta = ruta or os.environ.get("CHISPA_INSTRUCT_TAREAS")
    if ruta:
        return {l.strip() for l in Path(ruta).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}
    raiz = raiz_catalogo or raiz_hf(REPO_CATALOGO)
    return {t for t, ficha in cargar_fuentes(Path(raiz)).items() if ficha.get("license_use") == "commercial"}


def pregunta_de(tarea):
    return "Which label fits the input for the task «%s»?" % tarea_base(tarea).replace("_", " ")


def _lotes(ruta):
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(ruta)
    cols = [c for c in COLUMNAS if c in pf.schema_arrow.names]
    for lote in pf.iter_batches(batch_size=5000, columns=cols):
        yield from lote.to_pylist()


def _ficheros(raiz, split, subdir):
    return [p for p in ficheros_split(raiz, split, subdir) if p.name.endswith(".parquet")]


def vocabularios(raiz, subdir, comerciales, info):
    """{tarea: [clases]} de las tareas comerciales con vocabulario cerrado, a partir de train."""
    cuentas = defaultdict(Counter)
    abiertas = set()
    for ruta in _ficheros(raiz, "train", subdir):
        for r in _lotes(ruta):
            t = r.get("task")
            if t not in comerciales or t in abiertas:
                continue
            y = r.get("targets")
            if not isinstance(y, str) or not y.strip() or len(y) > MAX_TARGET:
                abiertas.add(t)
                continue
            cuentas[t][y.strip()] += 1
            if len(cuentas[t]) > MAX_CLASES * 4:  # corta antes de acumular miles de respuestas libres
                abiertas.add(t)
    vocab = {}
    for t, c in cuentas.items():
        if t in abiertas:
            continue
        clases = sorted(k for k, n in c.items() if n >= MIN_POR_CLASE)
        if 2 <= len(clases) <= MAX_CLASES and len(clases) == len(c):
            vocab[t] = clases
        else:
            abiertas.add(t)
    info["tareas_abiertas"] = len(abiertas)
    info["tareas_con_vocabulario"] = len(vocab)
    return vocab


def convertir_fila(r, clases, tarea):
    """Fila de origen -> campos del esquema (sin id ni split), o None."""
    x, y = r.get("inputs"), r.get("targets")
    if not isinstance(x, str) or not x.strip() or len(x) > MAX_INPUT or not isinstance(y, str) or y.strip() not in clases:
        return None
    y = y.strip()
    return {
        "tarea": PREFIJO + tarea, "tipo": "choice", "pregunta": pregunta_de(tarea), "texto": x.strip(), "opciones": list(clases),
        "descripciones": {c: c for c in clases}, "etiqueta": y, "blanda": {c: 1.0 if c == y else 0.0 for c in clases},
    }


def filas(raiz=None, info=None, subdir=None, tope=None, comerciales=None, tope_tarea=TOPE_TAREA):
    """Genera filas del esquema y rellena `info`. Solo tareas comerciales con vocabulario cerrado."""
    raiz = raiz or raiz_hf(REPO)
    subdir = subdir if subdir is not None else os.environ.get("CHISPA_TS_INSTRUCT_SUBDIR", "")
    info = info if info is not None else {}
    cont = lambda k, n=1: info.__setitem__(k, info.get(k, 0) + n)  # noqa: E731
    if comerciales is None:
        comerciales = tareas_comerciales()
    comerciales = {t for t in comerciales if not prohibida(t)}
    info["tareas_comerciales_declaradas"] = len(comerciales)
    if not comerciales:
        info["sin_datos"] = True
        return
    vocab = vocabularios(raiz, subdir, comerciales, info)
    num = Numerador(CORTO)
    info.setdefault("filas_leidas", 0)
    emitidas = 0
    for split, _ in SPLIT_FICHERO.items():
        por_tarea = Counter()
        for ruta in _ficheros(raiz, split, subdir):
            for r in _lotes(ruta):
                if tope is not None and emitidas >= tope:
                    break
                cont("filas_leidas")
                t = r.get("task")
                if t not in comerciales:
                    cont("descartadas_tarea_no_comercial")
                    continue
                if t not in vocab:
                    cont("descartadas_tarea_abierta")
                    continue
                if por_tarea[t] >= tope_tarea:
                    cont("descartadas_tope_tarea")
                    continue
                kw = convertir_fila(r, vocab[t], t)
                if kw is None:
                    cont("descartadas_invalidas")
                    continue
                kw.update(idioma="en", fuente="%s:%s %s" % (REPO, t, split), licencia="commercial (tasksource license_use)")
                por_tarea[t] += 1
                emitidas += 1
                yield num.numerar(split, kw, True)
    info["sin_datos"] = info["filas_leidas"] == 0


def convertir(raiz=None, **kw):
    info = {}
    return list(filas(raiz, info, **kw)), info
