"""tasksource/tasksource-jev-typed-decisions -> esquema de Chispa, solo filas con `license_use == "commercial"`.

Columnas de origen (README del dataset): `state`, `question`, `kind` (choice | score | noul), `options`,
`target`, `source` (tarea), `license`, `license_use`; el split sale del fichero (`train`, `validation`, `test`).
  texto = state, pregunta = question, tipo = kind, opciones = options, etiqueta = argmax(target),
  blanda = target normalizado. En `noul`, `target = [p_true]`: opciones ["false","true"], etiqueta "true" si p >= 0.5.
  En `score`, las opciones de origen son los anclajes de la escala: ids "1".."K", cada uno con su texto como descripción.
Sin `descripciones` de origen, el texto de la opción hace de descripción.

Filtro duro: `license_use` de la fila distinto de «commercial» (non-commercial, unspecified, vacío…) se descarta y
se cuenta; no se escribe. Se descarta además la fila si `sources.yaml` clasifica su tarea como no comercial, si el
texto de su licencia es NC/ND o si la tarea toca GLiClass, XNLI o ANLI (o derivados).
"""
import math
import os

from model.datos.comun import ficheros_split
from model.datos.validar import RE_NO_COMERCIAL

from .comun import Numerador, prohibida, raiz_hf

REPO = "tasksource/tasksource-jev-typed-decisions"
CORTO = "tsjev"
SUBDIR = "data"  # config `default`; para `full`, "full" (`CHISPA_TS_SUBDIR`)
SPLIT_FICHERO = {"train": "train", "dev": "validation", "test": "test"}
COLUMNAS = ("state", "question", "kind", "options", "target", "source", "license", "license_use")
TIPOS = ("choice", "score", "noul")


def cargar_fuentes(raiz):
    """`sources.yaml` del dataset: tarea -> ficha (licencia, dataset de origen…). {} si no está."""
    import yaml
    p = raiz / "sources.yaml"
    if not p.is_file():
        return {}
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("sources") or {}


def censo_yaml(fuentes):
    """Lo que declara `sources.yaml`: tareas y filas por `license_use` (no son filas del fragmento, solo el catálogo)."""
    out = {}
    for ficha in fuentes.values():
        uso = ficha.get("license_use") or "vacio"
        c = out.setdefault(uso, {"tareas": 0, "filas": 0})
        c["tareas"] += 1
        c["filas"] += sum((ficha.get("rows") or {}).values())
    return out


def _distribucion(target):
    if not isinstance(target, (list, tuple)) or not target:
        return None
    try:
        v = [float(x) for x in target]
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(x) or x < 0 for x in v) or sum(v) <= 0:
        return None
    return v


def convertir_fila(r):
    """Fila de origen -> campos del esquema (sin id ni split), o None si no es válida."""
    kind, texto, pregunta = r.get("kind"), r.get("state"), r.get("question")
    if kind not in TIPOS or not isinstance(texto, str) or not texto.strip() or not isinstance(pregunta, str) \
            or not pregunta.strip():
        return None
    v = _distribucion(r.get("target"))
    if v is None:
        return None
    if kind == "noul":
        if len(v) != 1 or v[0] > 1:
            return None
        p = v[0]
        ids = ["false", "true"]
        desc = {"false": "false: not (%s)" % pregunta, "true": "true: " + pregunta}
        probs = [1 - p, p]
        etiqueta = "true" if p >= 0.5 else "false"
    else:
        ops = r.get("options")
        if not isinstance(ops, (list, tuple)) or len(ops) < 2 or len(ops) != len(v) \
                or not all(isinstance(o, str) and o.strip() for o in ops) or len(set(ops)) != len(ops):
            return None
        tot = sum(v)
        probs = [x / tot for x in v]
        ids = list(ops) if kind == "choice" else [str(i + 1) for i in range(len(ops))]
        desc = dict(zip(ids, ops))
        etiqueta = ids[max(range(len(ids)), key=lambda i: v[i])]
    return {
        "tarea": r.get("source") or "", "tipo": kind, "pregunta": pregunta, "texto": texto, "opciones": ids,
        "descripciones": desc, "etiqueta": etiqueta, "blanda": dict(zip(ids, probs)),
    }


def _lotes(ruta):
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(ruta)
    cols = [c for c in COLUMNAS if c in pf.schema_arrow.names]
    for lote in pf.iter_batches(batch_size=5000, columns=cols):
        yield from lote.to_pylist()


def filas(raiz=None, info=None, subdir=None, tope=None):
    """Genera filas del esquema y rellena `info` (contadores). Solo `commercial`."""
    raiz = raiz or raiz_hf(REPO)
    subdir = subdir or os.environ.get("CHISPA_TS_SUBDIR") or SUBDIR
    info = info if info is not None else {}
    cont = lambda k: info.__setitem__(k, info.get(k, 0) + 1)  # noqa: E731
    fuentes = cargar_fuentes(raiz)
    info["censo_sources_yaml"] = censo_yaml(fuentes)
    num = Numerador(CORTO)
    veto = {}  # tarea -> motivo de descarte de toda la tarea, o None
    info.setdefault("filas_leidas", 0)
    emitidas = 0
    for split, nombre in SPLIT_FICHERO.items():
        for ruta in ficheros_split(raiz, split, subdir):
            if not ruta.name.endswith(".parquet"):
                continue
            for r in _lotes(ruta):
                if tope is not None and emitidas >= tope:
                    break
                cont("filas_leidas")
                uso = r.get("license_use")
                if uso != "commercial":
                    cont("descartadas_licencia_%s" % (uso or "vacia"))
                    continue
                tarea = r.get("source") or ""
                if tarea not in veto:
                    ficha = fuentes.get(tarea) or {}
                    if prohibida(tarea, ficha.get("dataset"), ficha.get("originals"), list(ficha.get("revisions") or ()),
                                 ficha.get("data_files_from"), ficha.get("source_urls")):
                        veto[tarea] = "prohibida"
                    elif ficha and ficha.get("license_use") != "commercial":
                        veto[tarea] = "licencia_fuente_no_comercial"
                    else:
                        veto[tarea] = None
                if veto[tarea]:
                    cont("descartadas_" + veto[tarea])
                    continue
                lic = r.get("license") or (fuentes.get(tarea) or {}).get("license") or "commercial (tasksource license_use)"
                if RE_NO_COMERCIAL.search(str(lic)):
                    cont("descartadas_licencia_texto_nc")
                    continue
                kw = convertir_fila(r)
                if kw is None:
                    cont("descartadas_invalidas")
                    continue
                kw.update(idioma="mul" if tarea.startswith("multilingual/") else "en",
                          fuente="%s:%s %s" % (REPO, tarea, nombre), licencia=str(lic))
                f = num.numerar(split, kw, True)
                emitidas += 1
                yield f
    info["sin_datos"] = info["filas_leidas"] == 0
    info["tareas_vetadas"] = {t: m for t, m in veto.items() if m}


def convertir(raiz=None, **kw):
    """(lista de filas, info) para tests y fragmentos pequeños."""
    info = {}
    return list(filas(raiz, info, **kw)), info
