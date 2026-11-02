"""Variantes deterministas de un caso para medir si Chispa decide de forma estable.

Un caso es un dict ``{texto, pregunta, kind, opciones: [{id, description}], etiqueta}``.
Cada transformación recibe el caso y un ``random.Random`` y devuelve una variante: copia
del caso con la etiqueta ya traducida, más ``variante`` (nombre de la transformación) y
``mapa`` (id original -> id de la variante, identidad si los ids no cambian). Para
comparar una respuesta de la variante con la del original, tradúcela con ``mapa``.

Transformaciones (``TIPOS``): permutar, renombrar, parafrasear, erratas, mayusculas,
mezcla, largo. Seguras (``SEGURAS``, no cambian la respuesta correcta): permutar (también
en noul y score: solo cambia el orden, los ids se conservan; en score, con ids 1..K, mide justo el
invariante de que el runtime lee los niveles por el valor del id, así que una inestabilidad bajo
``permutar`` en score es un fallo del runtime, no de la transformación; con ids que no son 1..K el runtime
no opina y ``permutar`` es la identidad), renombrar (solo en choice y
multi; en noul/score es la identidad porque sus ids no son opacos), parafrasear (plantilla
en el idioma de la pregunta) y mayusculas. Con riesgo (``RIESGOS``; la variante lleva la
nota en ``riesgo``): erratas (rompe preguntas por palabras clave), mezcla (traducir
palabras puede cambiar el sentido) y largo (rompe preguntas sobre la extensión o sobre si
algo se menciona). Úsalas para medir fragilidad, no como verdad de etiqueta. mezcla y
erratas solo tocan ``texto``, nunca el nombre de las opciones. ``generar(caso, tipos, semilla)`` devuelve una variante por tipo, siempre
igual para la misma semilla. ``estabilidad`` resume % de decisiones que no cambian y
Δ de confianza (media y p95). Sin dependencias fuera de la biblioteca estándar.
"""
import copy
import math
import random
import re
import zlib

_ENTERO_CANONICO = re.compile(r"[1-9][0-9]*")  # entero canónico positivo, como strconv.Itoa en tok.NivelesScore del runtime


def _ids_uno_a_k(opciones):
    """True si los ids son exactamente 1..K (enteros canónicos, sin huecos ni repetidos, en cualquier orden)."""
    ids = [str(o["id"]) for o in opciones]
    return bool(ids) and all(_ENTERO_CANONICO.fullmatch(i) for i in ids) and sorted(int(i) for i in ids) == list(range(1, len(ids) + 1))

TIPOS = ("permutar", "renombrar", "parafrasear", "erratas", "mayusculas", "mezcla", "largo")

SEGURAS = ("permutar", "renombrar", "parafrasear", "mayusculas")
RIESGOS = {
    "erratas": "puede cambiar la etiqueta si la pregunta depende de palabras clave concretas",
    "mezcla": "traducir palabras del texto puede cambiar el sentido o la persona",
    "largo": "puede cambiar la etiqueta si la pregunta trata de la extensión o de lo que se menciona",
}

PLANTILLAS_PREGUNTA_EN = (
    "{p}",
    "Tell me this: {p}",
    "I need to know the following. {p}",
    "Please answer: {p}",
    "About the text above, {p_min}",
    "Based on what is said, {p_min}",
)

_EN = {"the", "is", "are", "what", "which", "who", "does", "do", "did", "this", "that", "of",
       "to", "and", "in", "for", "with", "user", "has", "was", "how", "why", "can", "it", "a", "an"}

PLANTILLAS_PREGUNTA = (
    "{p}",
    "Dime esto: {p}",
    "Necesito saber lo siguiente. {p}",
    "Por favor responde: {p}",
    "Sobre el texto anterior, {p_min}",
    "Con base en lo que se dice, {p_min}",
)

GLOSARIO = {  # español -> inglés; palabras enteras, en minúscula, sin ambiguas (su, tiempo, cuenta, pago...)
    "el": "the", "un": "a", "una": "a",
    "y": "and", "o": "or", "pero": "but", "con": "with", "sin": "without",
    "para": "for", "de": "of", "en": "in", "es": "is", "no": "not",
    "mi": "my",
    "tarjeta": "card", "banco": "bank", "dinero": "money", "saldo": "balance",
    "quiero": "want", "necesito": "need", "problema": "problem",
    "cliente": "customer", "mensaje": "message", "gracias": "thanks",
    "hola": "hello", "urgente": "urgent",
    "musica": "music", "música": "music", "alarma": "alarm", "correo": "email",
}

RELLENO = (
    "Este es un mensaje de contexto general.",
    "A continuación se incluye el contenido principal.",
    "Nota: el siguiente párrafo continúa el contexto.",
    "Gracias por su atención y por su tiempo.",
    "Los datos de este registro se conservan según el procedimiento habitual.",
    "Fin de la sección de contexto.",
)


def _copia(caso, nombre, mapa=None):
    v = copy.deepcopy(caso)
    v["variante"] = nombre
    v["mapa"] = mapa if mapa is not None else {o["id"]: o["id"] for o in caso.get("opciones", [])}
    v["riesgo"] = RIESGOS.get(nombre)
    return v


def _traducir_etiqueta(caso, mapa):
    """La etiqueta es un id (choice) o una lista de ids (multi)."""
    et = caso.get("etiqueta")
    if isinstance(et, (list, tuple)):
        return [mapa.get(e, e) if isinstance(e, str) else e for e in et]
    return mapa.get(et, et) if isinstance(et, str) else et


def permutar(caso, rng):
    """Reordena las opciones (en todos los kinds, también noul y score). Los ids no cambian, así que la etiqueta tampoco.

    En score siempre es segura con ids 1..K: el runtime lee los niveles por el valor del id, así que si la decisión
    depende del orden de entrada, el runtime está mal. Si los ids de un score no son exactamente 1..K («alto», «0..K-1», «01», huecos),
    el runtime no opina con ninguna capa (es lo esperado) y la variante no aplica: es la identidad.
    """
    v = _copia(caso, "permutar")
    if caso.get("kind") == "score" and not _ids_uno_a_k(v["opciones"]):
        return v
    rng.shuffle(v["opciones"])
    return v


def renombrar(caso, rng):
    """Cambia los ids por otros opacos (distintos entre sí y de los originales).

    Solo en choice y multi. En noul y score los ids significan (``true``/``false``, 1..K):
    devuelve la identidad.
    """
    if caso.get("kind") in ("noul", "score"):
        return _copia(caso, "renombrar")
    ids = [o["id"] for o in caso.get("opciones", [])]
    nuevos = [f"x{n}" for n in rng.sample(range(100, 1000), len(ids))]
    mapa = dict(zip(ids, nuevos))
    v = _copia(caso, "renombrar", mapa)
    for o in v["opciones"]:
        o["id"] = mapa[o["id"]]
    v["etiqueta"] = _traducir_etiqueta(caso, mapa)
    return v


def parafrasear(caso, rng):
    """Reescribe la pregunta con una plantilla en su idioma (español o inglés; la original va intacta dentro)."""
    p = (caso.get("pregunta") or "").strip()
    v = _copia(caso, "parafrasear")
    if p:
        p_min = p[0].lower() + p[1:]
        ingles = sum(w in _EN for w in re.findall(r"[a-z]+", p.lower())) >= 2
        plantillas = PLANTILLAS_PREGUNTA_EN if ingles else PLANTILLAS_PREGUNTA
        v["pregunta"] = rng.choice(plantillas[1:]).format(p=p, p_min=p_min)
    return v


def _errata(palabra, rng):
    if len(palabra) < 4:
        return palabra
    i = rng.randrange(1, len(palabra) - 1)
    if rng.random() < 0.5 and palabra[i] != palabra[i + 1]:  # intercambia dos letras contiguas
        return palabra[:i] + palabra[i + 1] + palabra[i] + palabra[i + 2:]
    return palabra[:i] + palabra[i + 1:]  # omite una letra


def erratas(caso, rng, prob=0.15):
    """Erratas (letra omitida o dos letras intercambiadas) en ~15% de las palabras del texto."""
    v = _copia(caso, "erratas")
    partes = re.split(r"(\W+)", caso.get("texto") or "")
    v["texto"] = "".join(_errata(t, rng) if t.isalpha() and rng.random() < prob else t for t in partes)
    return v


def mayusculas(caso, rng):
    """Cambia las mayúsculas del texto: TODO MAYÚSCULAS, todo minúsculas o alternado."""
    v = _copia(caso, "mayusculas")
    t = caso.get("texto") or ""
    modo = rng.choice(("alto", "bajo", "alterno"))
    if modo == "alto":
        v["texto"] = t.upper()
    elif modo == "bajo":
        v["texto"] = t.lower()
    else:
        v["texto"] = "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(t))
    return v


def mezcla(caso, rng, prob=0.5):
    """Mezcla español/inglés: traduce al inglés las palabras del texto que están en el glosario."""
    v = _copia(caso, "mezcla")
    partes = re.split(r"(\W+)", caso.get("texto") or "")
    out = []
    for t in partes:
        en = GLOSARIO.get(t.lower()) if t.isalpha() else None
        if en and rng.random() < prob:
            en = en.capitalize() if t[0].isupper() else en
            t = en
        out.append(t)
    v["texto"] = "".join(out)
    return v


def largo(caso, rng, antes=3, despues=3):
    """Texto largo: relleno neutro antes y después del texto original."""
    v = _copia(caso, "largo")
    pre = " ".join(rng.choice(RELLENO) for _ in range(antes))
    pos = " ".join(rng.choice(RELLENO) for _ in range(despues))
    v["texto"] = f"{pre}\n\n{caso.get('texto') or ''}\n\n{pos}"
    return v


_FUNCIONES = {f.__name__: f for f in (permutar, renombrar, parafrasear, erratas, mayusculas, mezcla, largo)}


def generar(caso, tipos=TIPOS, semilla=0):
    """Una variante por tipo, determinista: misma ``semilla`` y caso, mismas variantes.

    Cada tipo usa su propia secuencia aleatoria (semilla + nombre), así que añadir o quitar
    tipos de la lista no cambia las demás variantes. No modifica ``caso``.
    """
    out = []
    for t in tipos:
        if t not in _FUNCIONES:
            raise ValueError(f"tipo desconocido: {t!r} (válidos: {', '.join(TIPOS)})")
        rng = random.Random(f"{semilla}:{t}:{zlib.crc32(repr(caso).encode())}")
        out.append(_FUNCIONES[t](caso, rng))
    return out


def _p95(xs):
    xs = sorted(xs)
    return xs[max(0, math.ceil(0.95 * len(xs)) - 1)]


def estabilidad(original, variantes, respuestas):
    """Estabilidad de la decisión frente a las variantes.

    ``original``: respuesta al caso original, ``{"id": decisión, "confianza": float}``.
    ``variantes``: lista de variantes (de ``generar``), de las que se usa ``mapa``.
    ``respuestas``: respuestas a cada variante, en el mismo orden y con la misma forma.

    La decisión de una variante se compara con ``mapa[original["id"]]`` (si el id no está
    en el mapa, tal cual: sirve para score/noul). Devuelve ``{n, estables, pct_estable,
    delta_media, delta_p95}``; Δ es |confianza_variante − confianza_original|.
    """
    if len(variantes) != len(respuestas):
        raise ValueError("variantes y respuestas deben tener la misma longitud")
    if not variantes:
        return {"n": 0, "estables": 0, "pct_estable": 0.0, "delta_media": 0.0, "delta_p95": 0.0}
    estables, deltas = 0, []
    for var, r in zip(variantes, respuestas):
        esperado = var["mapa"].get(original["id"], original["id"])
        estables += r["id"] == esperado
        deltas.append(abs(r["confianza"] - original["confianza"]))
    n = len(variantes)
    return {"n": n, "estables": estables, "pct_estable": 100.0 * estables / n,
            "delta_media": sum(deltas) / n, "delta_p95": _p95(deltas)}
