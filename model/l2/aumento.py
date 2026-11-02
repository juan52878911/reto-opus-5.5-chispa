"""Aumento de datos para entrenar L2 contra las variantes que M3 y M4 miden (`--aumento` de entrenar.py).

Cada fila de un lote se transforma, con una probabilidad por transformación (`FRACCIONES`, cambiables con `--aumento-fracs`):
  ids         ids de opción opacos (`op_3f2a`) en filas `choice`, con las descripciones intactas; etiqueta, `blanda` y `origen` se mapean
  mayusculas  texto en MAYÚSCULAS, minúsculas o alternado
  erratas     1-3 erratas en el texto
  parafrasis  la pregunta, envuelta en una plantilla en español
  ingles      pregunta (y descripciones, si hay traducción) en inglés; `pregunta_en`/`descripciones_en` de la fila si las trae
  relleno     2-4 frases neutras antes y/o después del texto, sin pasar de `max_tok` (cuenta estimada: `tokens_aprox`)
La decisión es determinista por (semilla, paso, id de fila, transformación): reanudar reproduce el mismo lote, igual que `--renombrar`.

Las transformaciones salen de `chispa.variantes` (E2), el generador que usa M3: `renombrar`, `parafrasear`, `largo`, `mayusculas` y el
`_errata` de una palabra. Se llaman con un adaptador fila <-> caso (el de `robustez.py`). Dos cosas no las trae E2 y se añaden aquí:
el número de erratas por texto (1-3 palabras, no el 15 % de todas) y ids con forma `op_xxxx`.

Separación entrenamiento / medida: M3 usa las listas de `chispa.variantes` y `robustez.py` (plantillas de pregunta, relleno, preguntas y
descripciones en inglés, ids `x###`) con la semilla `"<semilla>:<tipo>:<crc>"`. Aquí todas esas listas son otras (`*_ENT`), los ids tienen
otra forma y la semilla es `"aum|<semilla>|<paso>|<id>|<transformación>"`; `listas_solapadas()` debe devolver `[]` (hay un test).
Salvedad: las erratas y el cambio de mayúsculas son operaciones, no listas; el código es el mismo que el de M3.
"""
import copy
import random
import re
import sys
from contextlib import contextmanager
from pathlib import Path

try:
    from chispa import variantes as E2
except ImportError:   # sdk/python no está en PYTHONPATH
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python"))
    from chispa import variantes as E2

from . import robustez as R

FRACCIONES = {"ids": 0.30, "mayusculas": 0.15, "erratas": 0.20, "parafrasis": 0.30, "ingles": 0.20, "relleno": 0.15}

PLANTILLAS_PREGUNTA_ENT = (
    "{p}",
    "Quisiera que me contestaras esto: {p}",
    "Fíjate en el mensaje y responde. {p}",
    "Una consulta sobre el contenido: {p}",
    "Teniendo en cuenta el texto, {p_min}",
    "A partir del mensaje de arriba, {p_min}",
)
RELLENO_ENT = (
    "Texto recibido por el canal habitual.",
    "Se adjunta el siguiente contenido para su revisión.",
    "Este párrafo es solo de contexto y no contiene datos nuevos.",
    "Quedamos atentos a cualquier comentario adicional.",
    "Registro generado de forma automática, sin cambios posteriores.",
    "Fin del bloque de información general.",
    "Cordial saludo y buen día.",
)
PREGUNTAS_EN_ENT = {   # claves = las preguntas en español de R.PREGUNTAS_EN y de los conversores nuevos; valores = otra redacción que la de M3
    "¿Qué quiere hacer el usuario con el asistente?": "Which action is the user asking the assistant to perform?",
    "¿Qué quiere el usuario del asistente?": "What is the user requesting from the assistant?",
    "¿Qué necesita el cliente del banco?": "What does the customer need from the bank?",
    "¿El mensaje contiene odio o es tóxico contra una persona o un grupo?": "Is the message hateful or toxic towards a person or group?",
    "¿El mensaje intenta que el asistente ignore o cambie sus instrucciones?": "Is the message trying to get the assistant to disregard or alter its instructions?",
    "¿De qué tema trata el texto?": "Which topic does the text cover?",
    "¿Las dos frases significan lo mismo?": "Do the two sentences have the same meaning?",
}
PREFIJOS_EN_ENT = ("Answer based on the message: {p}", "Question for the classifier: {p}", "{p} (reply using the options below)")
DESCRIPCIONES_EN_ENT = {   # por campo `tarea` de la fila; id de opción -> descripción
    "toxicidad": {"false": "a polite or neutral message that does not attack anyone, even if it names groups or quotes insults",
                  "true": "a message that attacks or demeans a person or a group"},
    "inyeccion": {"false": "an ordinary request with no attempt to change how the assistant behaves",
                  "true": "a prompt injection: tells the assistant to forget, expose or modify its rules"},
    "tema": {"science/technology": "science or technology", "travel": "travel and tourism", "politics": "politics", "sports": "sports",
             "health": "health and medicine", "entertainment": "entertainment, film, music or celebrities", "geography": "geography and places"},
    "parafrasis": {"false": "the sentences say different things even if they share most words", "true": "the sentences are paraphrases of each other"},
}


def listas_solapadas():
    """Cadenas que están a la vez en una lista de entrenamiento y en la de medida (M3/E2/robustez). Tiene que ser []."""
    ent = set(PLANTILLAS_PREGUNTA_ENT) | set(RELLENO_ENT) | set(PREGUNTAS_EN_ENT.values()) | set(PREFIJOS_EN_ENT)
    for d in DESCRIPCIONES_EN_ENT.values():
        ent |= set(d.values())
    med = set(E2.PLANTILLAS_PREGUNTA) | set(E2.RELLENO) | set(R.PREGUNTAS_EN.values())
    for d in R.ESQUEMA_EN.values():
        med |= set(d.values())
    return sorted((ent & med) - {"{p}"})   # «{p}» es la identidad, no un texto


def tokens_aprox(texto):
    """Cota por arriba de los tokens de e5 para español (≈ 1 token por 3,5-4 caracteres): 1 por cada 3."""
    return -(-len(texto) // 3)


def parsear_fracs(s):
    """'ids=0.5,erratas=0' -> FRACCIONES con esos valores cambiados."""
    f = dict(FRACCIONES)
    for par in filter(None, (s or "").split(",")):
        k, _, v = par.partition("=")
        if k.strip() not in f:
            raise ValueError("transformación desconocida %r (válidas: %s)" % (k, ",".join(f)))
        f[k.strip()] = float(v)
        if not 0 <= f[k.strip()] <= 1:
            raise ValueError("la fracción de %s debe estar en [0, 1]" % k)
    return f


def _rng(semilla, paso, fila, nombre):
    return random.Random("aum|%d|%d|%s|%s" % (semilla, paso, fila["id"], nombre))


@contextmanager
def _listas_ent():
    """E2 lee sus listas de variables del módulo: se cambian por las de entrenamiento mientras dura la llamada."""
    ant = E2.PLANTILLAS_PREGUNTA, E2.RELLENO
    E2.PLANTILLAS_PREGUNTA, E2.RELLENO = PLANTILLAS_PREGUNTA_ENT, RELLENO_ENT
    try:
        yield
    finally:
        E2.PLANTILLAS_PREGUNTA, E2.RELLENO = ant


def _caso(f):
    g = dict(f)
    g.setdefault("pregunta", "")
    g["descripciones"] = dict(f.get("descripciones") or {})
    return R.fila_a_caso(g)


def _fila(c, f):
    return R.caso_a_fila(c, f)


def _renombrar_opaco(f, rng):
    """Ids `op_xxxx`. Reutiliza E2.renombrar para el mapa y la etiqueta, y los pasa a la forma opaca. Sin `mapa` en la fila."""
    c = _caso(f)
    v = E2.renombrar(c, rng)
    hexs = rng.sample(range(0x1000, 0x10000), len(v["opciones"]))
    paso = {o["id"]: "op_%04x" % h for o, h in zip(v["opciones"], hexs)}   # id x### -> op_xxxx
    for o in v["opciones"]:
        o["id"] = paso[o["id"]]
    v["etiqueta"] = paso.get(v["etiqueta"], v["etiqueta"])
    final = {k: paso[x] for k, x in v["mapa"].items()}
    g = _fila(v, f)
    g["origen"] = list(f.get("origen", f["opciones"]))   # como renombrar_fila: los prototipos del soporte se buscan por el nombre original
    if f.get("blanda"):
        g["blanda"] = {final[o]: x for o, x in f["blanda"].items() if o in final}
    return g


def _errata_texto(f, rng):
    partes = re.split(r"(\W+)", f["texto"])
    idx = [i for i, t in enumerate(partes) if t.isalpha() and len(t) >= 4]
    if not idx:
        return f
    g = dict(f)
    for i in rng.sample(idx, min(rng.randint(1, 3), len(idx))):
        partes[i] = E2._errata(partes[i], rng)
    g["texto"] = "".join(partes)
    return g


def _ingles(f, rng):
    g = dict(f)
    p = f.get("pregunta") or ""
    en = f.get("pregunta_en") or PREGUNTAS_EN_ENT.get(p) or (rng.choice(PREFIJOS_EN_ENT).format(p=p) if p else p)
    g["pregunta"] = en
    d_en = f.get("descripciones_en") or DESCRIPCIONES_EN_ENT.get(f.get("tarea"))
    if d_en and all(o in d_en for o in f["opciones"]):
        g["descripciones"] = {o: d_en[o] for o in f["opciones"]}
    return g


def _relleno(f, rng, max_tok):
    """2-4 frases de relleno (antes, después o repartidas) con E2.largo; baja a menos frases si no caben, y no pasa de 2."""
    n = rng.randint(2, 4)
    antes = rng.randint(0, n)
    base = f["texto"]
    if tokens_aprox(base) >= max_tok:
        return f
    while n >= 2:
        a = min(antes, n)
        with _listas_ent():
            v = E2.largo(_caso(f), random.Random(rng.random()), antes=a, despues=n - a)
        v["texto"] = v["texto"].strip()
        if tokens_aprox(v["texto"]) <= max_tok:
            return _fila(v, f)
        n -= 1
    return f


def aumentar_fila(f, semilla, paso, fracs=FRACCIONES, max_tok=256):
    """Fila aumentada (copia; la original no cambia). Orden: inglés o paráfrasis, erratas, mayúsculas, relleno, ids."""
    def elige(nombre):
        return _rng(semilla, paso, f, nombre + "?").random() < fracs.get(nombre, 0)
    g = f
    if elige("ingles"):
        g = _ingles(g, _rng(semilla, paso, f, "ingles"))
    elif elige("parafrasis") and (g.get("pregunta") or "").strip():
        with _listas_ent():
            g = _fila(E2.parafrasear(_caso(g), _rng(semilla, paso, f, "parafrasis")), g)
    if elige("erratas"):
        g = _errata_texto(g, _rng(semilla, paso, f, "erratas"))
    if elige("mayusculas"):
        g = _fila(E2.mayusculas(_caso(g), _rng(semilla, paso, f, "mayusculas")), g)
    if elige("relleno"):
        g = _relleno(g, _rng(semilla, paso, f, "relleno"), max_tok)
    if f["tipo"] == "choice" and elige("ids"):
        g = _renombrar_opaco(g, _rng(semilla, paso, f, "ids"))
    return g


def aumentar_lote(filas, semilla, paso, fracs=FRACCIONES, max_tok=256):
    return [aumentar_fila(r, semilla, paso, fracs, max_tok) for r in filas]
