"""Utilidades comunes del conversor: lectura de tablas, tarjetas de licencia, reparto y filas."""
import csv
import gzip
import hashlib
import json
import re
from pathlib import Path

import yaml

HF_HUB = Path.home() / "hf" / "hub"
SPLITS = ("train", "dev", "test")
ALIAS_SPLIT = {"train": ("train",), "dev": ("validation", "val", "dev"), "test": ("test",)}
EXT = (".parquet", ".csv", ".tsv", ".jsonl", ".json", ".json.gz", ".jsonl.gz")
COL_ETIQUETA = ("label", "category", "intent", "label_text", "labels")


class FuenteAusente(Exception):
    """La fuente no está en ~/hf (ni se dio otra raíz)."""


def raiz_hf(repo):
    """Snapshot más reciente de `owner/nombre` en la caché de ~/hf."""
    d = HF_HUB / ("datasets--" + repo.replace("/", "--")) / "snapshots"
    snaps = sorted(p for p in d.glob("*") if p.is_dir()) if d.is_dir() else []
    if not snaps:
        raise FuenteAusente(repo)
    return snaps[-1]


def bucket(clave, sal=""):
    """Número estable en [0,1) a partir de una clave (reparto sin depender del orden)."""
    h = hashlib.sha1((sal + "|" + str(clave)).encode("utf-8")).hexdigest()
    return int(h[:12], 16) / float(16 ** 12)


def split_por_clave(clave, p_dev=0.1, p_test=0.1, sal=""):
    b = bucket(clave, sal)
    if b < p_test:
        return "test"
    if b < p_test + p_dev:
        return "dev"
    return "train"


def _abrir(path):
    if str(path).endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8", newline="")


def leer_tabla(path):
    """Lee un fichero (parquet/csv/tsv/jsonl/json, con o sin .gz) a lista de dicts."""
    path = Path(path)
    n = path.name
    if n.endswith(".parquet"):
        import pyarrow.parquet as pq
        return pq.read_table(path).to_pylist()
    if n.endswith((".csv", ".csv.gz")):
        with _abrir(path) as f:
            return list(csv.DictReader(f))
    if n.endswith((".tsv", ".tsv.gz")):
        with _abrir(path) as f:
            return list(csv.DictReader(f, delimiter="\t"))
    if n.endswith((".jsonl", ".jsonl.gz", ".json.gz")):
        with _abrir(path) as f:
            return [json.loads(l) for l in f if l.strip()]
    if n.endswith(".json"):
        with _abrir(path) as f:
            return json.load(f)
    raise ValueError("formato no soportado: " + n)


def ficheros_split(raiz, split, subdir=""):
    """Ficheros de un split bajo raiz/subdir: `train.csv`, `train-0000-of-0001.parquet`, `validation/...`."""
    base = Path(raiz) / subdir
    out = []
    for alias in ALIAS_SPLIT[split]:
        for p in sorted(base.rglob("*")):
            if not p.is_file() or not p.name.endswith(EXT):
                continue
            if p.name.startswith(alias) or alias in p.relative_to(base).parts[:-1]:
                out.append(p)
        if out:
            break
    return out


def leer_split(raiz, split, subdir=""):
    fs = ficheros_split(raiz, split, subdir)
    if not fs:
        raise FileNotFoundError("sin ficheros de %s en %s/%s" % (split, raiz, subdir))
    filas = []
    for f in fs:
        filas.extend(leer_tabla(f))
    return filas


def tarjeta(raiz):
    """Cabecera YAML del README.md de la tarjeta del dataset ({} si no hay)."""
    p = Path(raiz) / "README.md"
    if not p.is_file():
        return {}
    m = re.match(r"^---\n(.*?)\n---", p.read_text(encoding="utf-8"), re.S)
    return (yaml.safe_load(m.group(1)) or {}) if m else {}


def licencia_tarjeta(raiz):
    """Licencia declarada en la tarjeta, normalizada a minúsculas; None si no declara."""
    lic = tarjeta(raiz).get("license")
    if isinstance(lic, list):
        lic = lic[0] if lic else None
    return str(lic).strip().lower() if lic else None


def nombres_de_clase(raiz, columna=None):
    """Nombres de un ClassLabel desde `dataset_info` de la tarjeta (id -> nombre), o None."""
    info = tarjeta(raiz).get("dataset_info") or []
    if isinstance(info, dict):
        info = [info]
    for cfg in info:
        for ft in cfg.get("features") or []:
            cl = (ft.get("dtype") or {}) if isinstance(ft.get("dtype"), dict) else {}
            if "class_label" in cl and (columna is None or ft.get("name") == columna):
                nombres = cl["class_label"].get("names") or {}
                return {int(k): v for k, v in nombres.items()}
    return None


def etiqueta_de(fila, nombres=None, columnas=COL_ETIQUETA):
    """Etiqueta de texto de una fila; resuelve enteros con `nombres` (dict id->nombre o lista)."""
    for c in columnas:
        if c in fila and fila[c] not in (None, ""):
            v = fila[c]
            break
    else:
        raise KeyError("la fila no trae columna de etiqueta: %s" % sorted(fila))
    if isinstance(v, str) and not v.lstrip("-").isdigit():
        return v
    if nombres is None:
        raise ValueError("etiqueta entera %r sin tabla de nombres" % (v,))
    return nombres[int(v)]


def licencia_fuente(raiz, esperadas, canonica, comercial=True):
    """(licencia, uso_comercial) de una fuente: solo vale la esperada si la tarjeta la confirma.

    Si la tarjeta no declara licencia o declara otra, queda «sin verificar» y `uso_comercial=False`.
    """
    leida = licencia_tarjeta(raiz)
    if leida in esperadas:
        return canonica, comercial
    return "sin verificar (tarjeta: %s; se esperaba %s)" % (leida or "sin licencia", canonica), False


def fila(corto, split, n, tarea, tipo, pregunta, texto, opciones, descripciones, etiqueta, idioma,
         fuente, licencia, uso_comercial, plantilla=None):
    f = {
        "id": "%s:%s:%d" % (corto, split, n), "tarea": tarea, "tipo": tipo, "pregunta": pregunta,
        "texto": texto, "opciones": list(opciones), "descripciones": dict(descripciones),
        "etiqueta": etiqueta, "idioma": idioma, "split": split, "fuente": fuente,
        "licencia": licencia, "uso_comercial": bool(uso_comercial),
    }
    if plantilla is not None:
        f["plantilla"] = str(plantilla)
    return f


def numerar(corto, items):
    """items = [(split, kwargs-de-fila)] -> (filas, descartadas).

    Red de seguridad común: una fila no comercial fuera de `test` se descarta (y se cuenta) antes de
    numerar, para que los ids `<corto>:<split>:<n>` (n desde 0 por split) no tengan huecos.
    """
    cont = {}
    out = []
    descartadas = 0
    for split, kw in items:
        if not kw["uso_comercial"] and split != "test":
            descartadas += 1
            continue
        n = cont.get(split, 0)
        cont[split] = n + 1
        out.append(fila(corto, split, n, **kw))
    return out, descartadas
