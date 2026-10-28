"""GoEmotions traducido al español (mrm8488/go_emotions-es-mt): `emocion`, `choice` de 28 clases.

Texto = `text_es` (traducción automática con EasyNMT). Es multietiqueta: con una sola etiqueta se usa esa; con
varias se usa la PRIMERA de la lista (no «neutral»). Se respetan los splits originales (ya son 80/10/10).
"""
import collections
from pathlib import Path

from .comun import fila, leer_split, raiz_hf, SPLITS
from .libres import licencia_estricta

REPO = "mrm8488/go_emotions-es-mt"
CORTO = "goemociones"
NOMBRES = ["admiration", "amusement", "anger", "annoyance", "approval", "caring", "confusion", "curiosity", "desire",
           "disappointment", "disapproval", "disgust", "embarrassment", "excitement", "fear", "gratitude", "grief", "joy",
           "love", "nervousness", "optimism", "pride", "realization", "relief", "remorse", "sadness", "surprise", "neutral"]
DESCRIPCIONES = {
    "admiration": "admiración: respeto o aprecio por alguien o algo", "amusement": "diversión: algo le hace gracia",
    "anger": "enojo: rabia o ira", "annoyance": "molestia: fastidio leve", "approval": "aprobación: está de acuerdo o lo ve bien",
    "caring": "cariño: preocupación afectuosa por otra persona", "confusion": "confusión: no entiende algo",
    "curiosity": "curiosidad: quiere saber más", "desire": "deseo: quiere algo con fuerza",
    "disappointment": "decepción: esperaba algo mejor", "disapproval": "desaprobación: no está de acuerdo o lo ve mal",
    "disgust": "asco: repulsión", "embarrassment": "vergüenza: se siente incómodo o expuesto",
    "excitement": "emoción: entusiasmo por algo que viene", "fear": "miedo: temor ante un peligro",
    "gratitude": "gratitud: agradece algo", "grief": "duelo: pena profunda por una pérdida", "joy": "alegría: felicidad",
    "love": "amor: afecto profundo", "nervousness": "nerviosismo: inquietud o ansiedad", "optimism": "optimismo: confía en que saldrá bien",
    "pride": "orgullo: satisfacción por un logro propio o ajeno", "realization": "comprensión: se da cuenta de algo",
    "relief": "alivio: se libera de una preocupación", "remorse": "remordimiento: lamenta algo que hizo",
    "sadness": "tristeza: pena o desánimo", "surprise": "sorpresa: algo inesperado",
    "neutral": "neutral: sin emoción clara",
}
PREGUNTA = "¿Qué emoción expresa el mensaje?"


def convertir(raiz=None):
    raiz = Path(raiz or raiz_hf(REPO))
    lic, com = licencia_estricta(raiz, ("apache-2.0",), "apache-2.0")
    filas, multi, sin_texto = [], 0, 0
    for split in SPLITS:
        n = 0
        for r in leer_split(raiz, split, "data"):
            ls = list(r["labels"])
            texto = (r.get("text_es") or "").strip()
            if not ls or not texto:
                sin_texto += 1
                continue
            multi += len(ls) > 1
            filas.append(fila(CORTO, split, n, tarea="emocion", tipo="choice", pregunta=PREGUNTA, texto=texto,
                              opciones=NOMBRES, descripciones=DESCRIPCIONES, etiqueta=NOMBRES[int(ls[0])], idioma="es",
                              fuente=REPO + " " + split, licencia=lic, uso_comercial=com))
            n += 1
    return filas, {"licencia": lic, "multietiqueta": multi, "descartadas": sin_texto,
                   "regla_multietiqueta": "primera etiqueta de la lista", "traduccion": "automática (EasyNMT)"}
