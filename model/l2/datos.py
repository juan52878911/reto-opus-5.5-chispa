"""Carga de filas (esquema v1, `.jsonl` y `.jsonl.gz`), submuestreo y muestreo por tarea con temperatura."""
import glob
import gzip
import hashlib
import json
import os
from collections import defaultdict

import numpy as np

ALFA = 0.5  # p(tarea) ∝ n^ALFA


def abrir(ruta):
    return gzip.open(ruta, "rt", encoding="utf-8") if str(ruta).endswith(".gz") else open(ruta, encoding="utf-8")


def ficheros(ruta):
    """Un fichero, o todos los *.jsonl/*.jsonl.gz de un directorio (recursivo), en orden estable."""
    if os.path.isdir(ruta):
        fs = [f for f in glob.glob(os.path.join(ruta, "**", "*"), recursive=True) if f.endswith((".jsonl", ".jsonl.gz"))]
        return sorted(f for f in fs if "solo-medir" not in os.path.basename(f))
    return [ruta]


def iterar(rutas):
    """Filas de una o varias rutas. Comparte `opciones`, `descripciones` y `pregunta` entre filas iguales (ahorra RAM:
    clinc150 trae 151 descripciones por fila)."""
    if isinstance(rutas, (str, os.PathLike)):
        rutas = [rutas]
    internos = {}
    for r in rutas:
        for f in ficheros(str(r)):
            with abrir(f) as fh:
                for l in fh:
                    if not l.strip():
                        continue
                    fila = json.loads(l)
                    k = (fila.get("pregunta"), tuple(fila["opciones"]), hashlib.md5(
                        json.dumps(fila["descripciones"], sort_keys=True).encode()).digest())
                    if k not in internos:
                        internos[k] = (fila["pregunta"], fila["opciones"], fila["descripciones"])
                    fila["pregunta"], fila["opciones"], fila["descripciones"] = internos[k]
                    yield fila


def leer(rutas, split=None, solo_comercial=False):
    return [r for r in iterar(rutas) if (split is None or r["split"] == split) and (not solo_comercial or r.get("uso_comercial"))]


def cargar_blandas(rutas):
    """{id: blanda} de las salidas del maestro (`model.maestro.blandas`); ignora los `.solo-medir.jsonl`."""
    out = {}
    for fila in iterar(rutas):
        if fila.get("blanda"):
            out[fila["id"]] = fila["blanda"]
    return out


def aplicar_blandas(filas, blandas, solo_train=True):
    """Pone `blanda` donde la fila no la trae. Devuelve cuántas filas la tienen al final."""
    n = 0
    for r in filas:
        if not r.get("blanda") and (not solo_train or r["split"] == "train") and r["id"] in blandas:
            r["blanda"] = blandas[r["id"]]
        n += bool(r.get("blanda"))
    return n


def _u(clave, semilla):
    """Número estable en [0,1) a partir de (semilla, clave): el submuestreo no depende del orden ni de la ejecución."""
    h = hashlib.blake2b(("%d|%s" % (semilla, clave)).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2 ** 64


def grupo_meta(ruta, raiz):
    rel = os.path.relpath(ruta, raiz).split(os.sep)
    return rel[0] if len(rel) > 1 else "meta"


def submuestrear_meta(raiz, maximo, completos=("tsjev", "tasksource_jev"), semilla=0, split="train"):
    """Filas `split` y comerciales del directorio de metaentrenamiento (`<fuente>/<split>-NNNNN.jsonl.gz`), ≤ `maximo`.
    Las fuentes en `completos` entran enteras (hasta `maximo`); el resto se reparte a partes iguales del presupuesto que
    queda, y una fuente pequeña cede lo que no use. Dos pasadas por los ficheros (cuenta y elige)."""
    fs = ficheros(raiz)
    cuentas = defaultdict(int)
    for f in fs:
        g = grupo_meta(f, raiz)
        for r in _filas_meta(f, split):
            cuentas[g] += 1
    comp = [g for g in cuentas if any(c in g for c in completos)]
    resto = [g for g in cuentas if g not in comp]
    cupo = {g: min(cuentas[g], maximo) for g in comp}
    libre = max(maximo - sum(cupo.values()), 0)
    for i, g in enumerate(sorted(resto, key=lambda g: cuentas[g])):  # reparto con cesión
        cupo[g] = min(cuentas[g], libre // (len(resto) - i))
        libre -= cupo[g]
    if sum(cupo[g] for g in comp) > maximo:  # solo si los completos ya exceden el tope
        f_ = maximo / sum(cupo[g] for g in comp)
        cupo = {g: int(c * f_) for g, c in cupo.items()}
    p = {g: (cupo[g] / cuentas[g] if cuentas[g] else 0.0) for g in cuentas}
    out = []
    for f in fs:
        g = grupo_meta(f, raiz)
        for r in _filas_meta(f, split):
            if p[g] >= 1 or _u(r["id"], semilla) < p[g]:
                out.append(r)
    return out, dict(cuentas), cupo


def _filas_meta(f, split):
    for r in iterar(f):
        if r["split"] == split and r.get("uso_comercial"):
            yield r


class Muestreador:
    """Lotes de `lote` mensajes con la tarea elegida por p ∝ n^ALFA y la fila al azar dentro de ella. Es una función
    pura de (semilla, paso): reanudar desde un checkpoint reproduce el mismo flujo de lotes."""

    def __init__(self, filas, lote=64, alfa=ALFA, semilla=0):
        self.por = defaultdict(list)
        for r in filas:
            self.por[r["tarea"]].append(r)
        self.tareas = sorted(self.por)
        n = np.array([len(self.por[t]) for t in self.tareas], dtype=float)
        self.p = n ** alfa / (n ** alfa).sum()
        self.lote, self.semilla, self.n = lote, semilla, len(filas)

    def pasos_por_epoca(self):
        return max(self.n // self.lote, 1)

    def lote_paso(self, paso):
        rng = np.random.default_rng([self.semilla, paso])
        ts = rng.choice(len(self.tareas), size=self.lote, p=self.p)
        return [self.por[self.tareas[t]][rng.integers(len(self.por[self.tareas[t]]))] for t in ts]
