"""Pieza común de los conversores de metaentrenamiento (T1.8): fuentes prohibidas, ids, salida en trozos y resumen.

Reutiliza lo ya hecho en `model.datos.comun` (lectura de tablas, tarjetas de licencia, reparto por clave).
"""
import gzip
import json
import os
import re
from pathlib import Path

from model.datos.comun import (  # noqa: F401  (se reexportan para los conversores)
    FuenteAusente, leer_tabla, licencia_tarjeta, split_por_clave, tarjeta,
)

# Nada de GLiClass, XNLI ni ANLI, ni derivados. Derivados conocidos: multilingual-NLI-26lang-2mil7 y
# dataset_train_nli (de MoritzLaurer, mezclan XNLI y ANLI) y AmericasNLI (XNLI traducido). `wanli` no casa:
# antes de `anli` tiene que haber un separador.
PROHIBIDOS = re.compile(
    r"gliclass|(?<![a-z0-9])(?:xnli|anli)(?![a-z])|multilingual-nli-26lang|dataset_train_nli|americas_nli", re.I)

CHUNK_BYTES = 100 * 1024 * 1024  # texto JSONL sin comprimir por trozo; el trozo se escribe en gzip
SPLITS = ("train", "dev", "test")


class FuenteProhibida(Exception):
    """Una fila o una fuente toca GLiClass, XNLI o ANLI (o un derivado)."""


def prohibida(*textos):
    """El primer fragmento prohibido que aparezca en los textos dados, o None."""
    m = PROHIBIDOS.search(" ".join(str(t) for t in textos if t is not None))
    return m.group(0) if m else None


def hf_hub():
    """Caché de Hugging Face: `$HF_HOME/hub` (en kindling ~/hf; en AWS $BASE/hf)."""
    return Path(os.environ.get("HF_HOME") or Path.home() / "hf") / "hub"


def raiz_hf(repo):
    """Snapshot más reciente de `owner/nombre` en la caché."""
    if prohibida(repo):
        raise FuenteProhibida(repo)
    d = hf_hub() / ("datasets--" + repo.replace("/", "--")) / "snapshots"
    snaps = sorted(p for p in d.glob("*") if p.is_dir()) if d.is_dir() else []
    if not snaps:
        raise FuenteAusente(repo)
    return snaps[-1]


def limite():
    """Tope de filas por fuente para pruebas en seco (`CHISPA_LIMITE`); None = sin tope."""
    v = os.environ.get("CHISPA_LIMITE", "").strip()
    return int(v) if v else None


class Numerador:
    """Ids `<corto>:<split>:<n>` (n desde 0 por split, sin huecos) y la red de seguridad de licencia.

    Una fila no comercial fuera de `test` se descarta y se cuenta (esquema.md), igual que `datos.comun.numerar`.
    """

    def __init__(self, corto):
        self.corto = corto
        self.cont = {}
        self.descartadas_nc = 0

    def numerar(self, split, kw, uso_comercial):
        if not uso_comercial and split != "test":
            self.descartadas_nc += 1
            return None
        n = self.cont.get(split, 0)
        self.cont[split] = n + 1
        f = {"id": "%s:%s:%d" % (self.corto, split, n), "split": split, "uso_comercial": bool(uso_comercial)}
        f.update(kw)
        return f


class Salida:
    """Escribe filas en `<raiz>/<corto>/<split>-NNNNN.jsonl.gz` (trozos de ~100 MB sin comprimir) y lleva el resumen.

    Es la última barrera: rechaza una fila prohibida o no comercial fuera de `test`.
    """

    def __init__(self, raiz, chunk_bytes=CHUNK_BYTES):
        self.raiz = Path(raiz)
        self.chunk_bytes = chunk_bytes
        self.abiertos = {}  # (corto, split) -> [manejador, bytes, n_trozo]
        self.ficheros = []
        self.filas = {}  # fuente -> tipo -> split -> n
        self.tareas = {}  # fuente -> {tarea}
        self.descartes = {}  # fuente -> {motivo: n}

    def descartar(self, corto, motivo, n=1):
        d = self.descartes.setdefault(corto, {})
        d[motivo] = d.get(motivo, 0) + n

    def anadir(self, corto, f):
        malo = prohibida(f.get("fuente"), f.get("tarea"), f.get("id"))
        if malo:
            raise FuenteProhibida("fila %s toca %r" % (f.get("id"), malo))
        if not f["uso_comercial"] and f["split"] != "test":
            raise ValueError("fila no comercial fuera de test: " + f["id"])
        linea = json.dumps(f, ensure_ascii=False, separators=(",", ":")) + "\n"
        clave = (corto, f["split"])
        est = self.abiertos.get(clave)
        if est is None or est[1] >= self.chunk_bytes:
            if est is not None:
                est[0].close()
            n = 0 if est is None else est[2] + 1
            d = self.raiz / corto
            d.mkdir(parents=True, exist_ok=True)
            ruta = d / ("%s-%05d.jsonl.gz" % (f["split"], n))
            est = self.abiertos[clave] = [gzip.open(ruta, "wt", encoding="utf-8", compresslevel=6), 0, n]
            self.ficheros.append(str(ruta.relative_to(self.raiz)))
        est[0].write(linea)
        est[1] += len(linea.encode("utf-8"))
        por_tipo = self.filas.setdefault(corto, {}).setdefault(f["tipo"], {})
        por_tipo[f["split"]] = por_tipo.get(f["split"], 0) + 1
        self.tareas.setdefault(corto, set()).add(f["tarea"])

    def cerrar(self):
        for est in self.abiertos.values():
            est[0].close()
        self.abiertos = {}

    def resumen(self):
        por_fuente = {c: sum(n for t in tipos.values() for n in t.values()) for c, tipos in self.filas.items()}
        por_tipo, por_split = {}, {}
        for tipos in self.filas.values():
            for t, splits in tipos.items():
                for s, n in splits.items():
                    por_tipo[t] = por_tipo.get(t, 0) + n
                    por_split[s] = por_split.get(s, 0) + n
        todas = set().union(*self.tareas.values()) if self.tareas else set()
        return {
            "filas_total": sum(por_fuente.values()),
            "filas_por_fuente": por_fuente,
            "filas_por_tipo": por_tipo,
            "filas_por_split": por_split,
            "filas_por_fuente_tipo_split": self.filas,
            "descartadas": self.descartes,
            "descartadas_por_licencia": {c: {m: n for m, n in d.items() if m.startswith("licencia")}
                                         for c, d in self.descartes.items()},
            "tareas_distintas": len(todas),
            "tareas_distintas_por_fuente": {c: len(t) for c, t in self.tareas.items()},
            "ficheros": sorted(self.ficheros),
        }
