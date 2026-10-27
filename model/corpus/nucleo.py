"""Piezas puras del generador (T1.3): parseo de JSON roto, esquema, dedup, reparto sin fugas y contador de USD."""
import hashlib
import json
import os
import random
import re
import threading
import unicodedata

import numpy as np

CAMPOS = {"id": str, "tarea": str, "tipo": str, "pregunta": str, "texto": str, "opciones": list, "descripciones": dict,
          "etiqueta": str, "idioma": str, "split": str, "fuente": str, "licencia": str, "uso_comercial": bool}


class ErrorFormato(ValueError):
    """La respuesta del modelo no trae lo pedido."""


class TopeAlcanzado(Exception):
    """El gasto llegó al tope de USD: se para en seco."""


# --- parseo ------------------------------------------------------------------------------------------------
_CERCA = re.compile(r"^```[a-zA-Z]*\s*|\s*```\s*$")
_CADENA = re.compile(r'"((?:[^"\\\n]|\\.)*)"')


def _json_en(texto):
    """Primer objeto o lista JSON completo que empieza en texto (ignora lo que haya antes o después)."""
    dec = json.JSONDecoder()
    for i, c in enumerate(texto):
        if c in "{[":
            try:
                return dec.raw_decode(texto, i)[0]
            except ValueError:
                continue
    return None


def parsear_lista(respuesta, clave):
    """Saca una lista de cadenas de la respuesta del modelo. Acepta {clave: [...]}, [...], cercas ``` y texto alrededor;
    si el JSON está cortado o roto, rescata las cadenas completas que haya tras «clave»: [.
    Devuelve (lista, reparado). Lanza ErrorFormato si no queda nada."""
    t = _CERCA.sub("", respuesta.strip())
    v = _json_en(t)
    era_dict = isinstance(v, dict)
    if era_dict:
        v = v.get(clave)
    if isinstance(v, list) and all(isinstance(x, str) for x in v) and v:
        return v, False
    m = re.search(r'"%s"\s*:\s*\[' % re.escape(clave), t)
    if m is None and era_dict:
        raise ErrorFormato("el objeto no trae «%s»: %r" % (clave, respuesta[:80]))
    resto = t[m.end():] if m else t[t.find("[") + 1:] if "[" in t else ""
    sal = []
    for c in _CADENA.finditer(resto):
        try:
            sal.append(json.loads('"%s"' % c.group(1)))
        except ValueError:
            continue
    if resto.lstrip().startswith("]"):  # lista vacía bien formada
        sal = []
    if not sal:
        raise ErrorFormato("sin lista «%s» en la respuesta: %r" % (clave, respuesta[:80]))
    return sal, True


# --- normalización y dedup -------------------------------------------------------------------------------
def norm(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\W+", " ", s).strip()


def gramas(s, n=5):
    """Conjunto de n-gramas de caracteres del texto normalizado (el texto entero si es más corto que n)."""
    s = norm(s)
    if len(s) <= n:
        return frozenset([s])
    return frozenset(s[i:i + n] for i in range(len(s) - n + 1))


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def deduplicar(filas, referencias=(), embeber=None, umbral_jaccard=0.8, umbral_coseno=0.95):
    """Quita duplicados de `filas` (dicts con texto y etiqueta), en orden. Compara con las filas ya aceptadas y con
    `referencias` (textos del test, que no se emiten). Criterios: exacto, 5-gramas (Jaccard ≥ umbral) y coseno ≥ umbral
    si `embeber(lista_de_textos) -> matriz normalizada` está disponible. Si el duplicado de una fila aceptada tiene otra
    etiqueta, se descartan las dos (etiqueta dudosa). Devuelve (aceptadas, descartes: dict de contadores)."""
    desc = {"exacto": 0, "jaccard": 0, "coseno": 0, "conflicto_etiqueta": 0, "fuga_test": 0}
    todas = [(f["texto"], None) for f in referencias] + [(f["texto"], f["etiqueta"]) for f in filas]
    nref = len(referencias)
    vec = embeber([t for t, _ in todas]) if embeber and todas else None
    exactos, vistos = {}, []  # vistos: índices aceptados
    gr = [gramas(t) for t, _ in todas]
    tam = [len(g) for g in gr]
    vivo = [True] * len(todas)
    acc = np.zeros(len(todas), dtype=bool) if vec is not None else None

    def aceptar(i):
        exactos[norm(todas[i][0])] = i
        vistos.append(i)
        if acc is not None:
            acc[i] = True

    def comparar(i):
        n = norm(todas[i][0])
        if n in exactos:
            return exactos[n], "exacto"
        for j in vistos:
            if min(tam[i], tam[j]) >= umbral_jaccard * max(tam[i], tam[j]) and jaccard(gr[i], gr[j]) >= umbral_jaccard:
                return j, "jaccard"
        if vec is not None and i:
            golpes = np.flatnonzero((vec[:i] @ vec[i] >= umbral_coseno) & acc[:i])
            if golpes.size:
                return int(golpes[0]), "coseno"
        return None, None

    for i in range(len(todas)):
        if i < nref:
            aceptar(i)
            continue
        j, tipo = comparar(i)
        if j is None:
            aceptar(i)
            continue
        vivo[i] = False
        if j < nref:
            desc["fuga_test"] += 1
            continue
        if todas[j][1] != todas[i][1]:
            desc["conflicto_etiqueta"] += 2
            vivo[j] = False
            vistos.remove(j)
            if acc is not None:
                acc[j] = False
            for k in [k for k, v in exactos.items() if v == j]:
                del exactos[k]
            continue
        desc[tipo] += 1
    return [f for f, v in zip(filas, vivo[nref:]) if v], desc


# --- reparto sin fugas ------------------------------------------------------------------------------------
def repartir(plantillas, frac_dev=0.10, semilla=1):
    """plantillas: {plantilla: n_filas}. Devuelve {plantilla: 'train'|'dev'}. Todas las filas de una plantilla van a un
    mismo split; ~frac_dev de las filas va a dev (error máximo: una plantilla). Determinista por semilla."""
    orden = sorted(plantillas)
    random.Random(semilla).shuffle(orden)
    total, dev = sum(plantillas.values()), 0
    sal = {}
    for p in orden:
        n = plantillas[p]
        if dev + n / 2 <= frac_dev * total:
            sal[p] = "dev"
            dev += n
        else:
            sal[p] = "train"
    if len(plantillas) > 1 and "dev" not in sal.values():
        sal[orden[0]] = "dev"
    return sal


# --- esquema --------------------------------------------------------------------------------------------------
def validar_fila(f):
    """Lanza ValueError si la fila no cumple model/esquema.md."""
    for k, t in CAMPOS.items():
        if k not in f:
            raise ValueError("falta %s" % k)
        if not isinstance(f[k], t) or (t is str and not f[k].strip()):
            raise ValueError("%s con tipo o valor inválido: %r" % (k, f[k]))
    extra = set(f) - set(CAMPOS) - {"plantilla", "blanda"}
    if extra:
        raise ValueError("campos fuera del esquema: %s" % sorted(extra))
    if f["tipo"] != "choice":
        raise ValueError("tipo %r (aquí solo choice)" % f["tipo"])
    if f["etiqueta"] not in f["opciones"]:
        raise ValueError("etiqueta %r fuera de opciones" % f["etiqueta"])
    if set(f["descripciones"]) != set(f["opciones"]) or len(set(f["opciones"])) != len(f["opciones"]):
        raise ValueError("descripciones y opciones no coinciden")
    if f["split"] not in ("train", "dev", "test"):
        raise ValueError("split %r" % f["split"])
    if not f["uso_comercial"] and f["split"] != "test":
        raise ValueError("uso_comercial false fuera de test")
    if "plantilla" in f and not isinstance(f["plantilla"], str):
        raise ValueError("plantilla debe ser str")
    return f


def validar_conjunto(filas):
    ids = set()
    for f in filas:
        validar_fila(f)
        if f["id"] in ids:
            raise ValueError("id repetido " + f["id"])
        ids.add(f["id"])
    split_de = {}
    for f in filas:
        if split_de.setdefault(f.get("plantilla"), f["split"]) != f["split"]:
            raise ValueError("plantilla %r repartida en dos splits" % f.get("plantilla"))


# --- contador de gasto ----------------------------------------------------------------------------------------
class Gasto:
    """USD gastados, persistidos en un libro (una línea por llamada) para que reanudar no pierda la cuenta."""

    def __init__(self, ruta, tope, precio_in, precio_out):
        self.ruta, self.tope, self.pin, self.pout = ruta, tope, precio_in, precio_out
        self.lock = threading.Lock()
        self.usd = self.llamadas = self.tin = self.tout = 0
        self.por_tarea = {}
        self.max_llamada = 0.0
        self.parado = False
        if ruta and os.path.exists(ruta):
            with open(ruta, encoding="utf-8") as f:
                for linea in f:
                    if linea.strip():
                        r = json.loads(linea)
                        self._sumar(r["tarea"], r["tin"], r["tout"], r["usd"])

    def costo(self, tin, tout):
        return (tin * self.pin + tout * self.pout) / 1e6

    def _sumar(self, tarea, tin, tout, usd):
        self.usd += usd
        self.llamadas += 1
        self.tin += tin
        self.tout += tout
        self.max_llamada = max(self.max_llamada, usd)
        d = self.por_tarea.setdefault(tarea, {"usd": 0.0, "llamadas": 0, "tokens_in": 0, "tokens_out": 0})
        d["usd"] += usd
        d["llamadas"] += 1
        d["tokens_in"] += tin
        d["tokens_out"] += tout

    def permitir(self, margen=0.0):
        """Antes de cada llamada: lanza TopeAlcanzado si el gasto, más el margen, ya llega al tope."""
        with self.lock:
            if self.usd + max(margen, 1.5 * self.max_llamada) >= self.tope:  # la siguiente puede costar más que la mayor vista
                self.parado = True
                raise TopeAlcanzado("gasto %.4f USD de tope %.2f" % (self.usd, self.tope))

    def registrar(self, tarea, tipo, tin, tout):
        usd = self.costo(tin, tout)
        with self.lock:
            self._sumar(tarea, tin, tout, usd)
            if self.ruta:
                with open(self.ruta, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"tarea": tarea, "tipo": tipo, "tin": tin, "tout": tout, "usd": usd}) + "\n")
        return usd


def semilla_de(*partes):
    return int(hashlib.sha256("|".join(map(str, partes)).encode()).hexdigest()[:12], 16)
