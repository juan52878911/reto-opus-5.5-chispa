"""Conversores del listón humano: datasets con una etiqueta por anotador -> filas del esquema (`split: test`).

Cada fuente tiene dos pasos: `registros_*` lee ~/hf y devuelve unidades `{clave, texto, votos, ...}`,
y `filas_*` las pasa al esquema. `votos` es la lista de etiquetas (str) de los anotadores de la unidad.

Reglas comunes: `etiqueta` = mayoría de `votos`; con empate, la clase de menor índice en `opciones`;
`blanda` = proporción de anotadores por clase (suma 1); `anotadores` = nº de votos. Campos extra
opcionales (aprobación pendiente del orquestador): `anotadores`, `variedad`, `paises_anotadores`.
"""
import collections
from pathlib import Path

from model.datos.comun import leer_tabla, licencia_fuente, numerar, raiz_hf

BINARIAS = ["false", "true"]


def mayoria(votos, opciones):
    """(etiqueta, blanda). Empate -> la clase de menor índice en `opciones`."""
    if not votos:
        raise ValueError("unidad sin votos")
    c = collections.Counter(votos)
    ajenas = set(c) - set(opciones)
    if ajenas:
        raise ValueError("votos fuera de opciones: %s" % sorted(ajenas))
    n = len(votos)
    etiqueta = max(opciones, key=lambda o: (c[o], -opciones.index(o)))
    return etiqueta, {o: c[o] / n for o in opciones}


def _filas(corto, unidades, opciones, tarea, tipo, pregunta, descripciones, idioma, fuente, lic, com):
    """Unidades -> filas con extras. `idioma`, `fuente` y los extras pueden venir en la unidad."""
    items, extras = [], []
    for u in sorted(unidades, key=lambda u: str(u["clave"])):
        etiqueta, blanda = mayoria(u["votos"], opciones)
        items.append(("test", dict(
            tarea=tarea, tipo=tipo, pregunta=pregunta, texto=u["texto"], opciones=opciones,
            descripciones=descripciones, etiqueta=etiqueta, idioma=u.get("idioma", idioma),
            fuente=fuente, licencia=lic, uso_comercial=com)))
        extras.append((blanda, {"anotadores": len(u["votos"]), **u.get("extra", {})}))
    filas, descartadas = numerar(corto, items)
    assert not descartadas and len(filas) == len(extras)
    for f, (blanda, extra) in zip(filas, extras):
        f["blanda"] = blanda
        f.update(extra)
    return filas


def _raiz(repo, raiz):
    return Path(raiz) if raiz else raiz_hf(repo)


# ---------------------------------------------------------------- MultiPICo (ironía)
MP_REPO = "Multilingual-Perspectivist-NLU/MultiPICo"
MP_IDIOMA = {"co": "es-CO", "mx": "es-MX", "ar": "es-AR", "es": "es-ES", "us": "es-US"}
MP_DESC = {"false": "la respuesta es literal, sin ironía", "true": "la respuesta es irónica respecto al mensaje al que contesta"}


def registros_multipico(raiz=None):
    """Español de MultiPICo: una unidad por `reply_id`. La variedad (`language_variety`) es la del texto;
    del anotador solo viene el país de residencia, que se guarda aparte."""
    r = _raiz(MP_REPO, raiz)
    unidades = {}
    for x in leer_tabla(r / "multipico_anonimized.csv"):
        if x["language"] != "es":
            continue
        u = unidades.setdefault(x["reply_id"], dict(
            clave=x["reply_id"], idioma=MP_IDIOMA.get(x["language_variety"], "es"),
            texto="Mensaje: %s\nRespuesta: %s" % (str(x["post"]).strip(), str(x["reply"]).strip()),
            votos=[], paises=[], variedad=x["language_variety"]))
        u["votos"].append("true" if str(x["label"]).strip() in ("1", "1.0") else "false")
        u["paises"].append(str(x.get("Country of residence") or "?"))
    return [dict(u, extra={"variedad": u["variedad"], "paises_anotadores": u.pop("paises")}) for u in unidades.values()]


def filas_multipico(unidades, lic="cc-by-4.0", com=True):
    return _filas("multipico", unidades, BINARIAS, "ironia", "noul", "¿La respuesta es irónica?", MP_DESC,
                  "es", MP_REPO + " (es)", lic, com)


def convertir_multipico(raiz=None):
    r = _raiz(MP_REPO, raiz)
    lic, com = licencia_fuente(r, ("cc-by-4.0",), "cc-by-4.0")
    return filas_multipico(registros_multipico(r), lic, com)


# ---------------------------------------------------------------- ALIA (odio, 3 anotadores)
ALIA_REPO = "SINAI/ALIA-es-discriminative-hate-speech"
ODIO_DESC = {"false": "comentario sin discurso de odio", "true": "comentario con discurso de odio o discriminación"}


def registros_alia(raiz=None):
    """Solo las filas de la muestra humana con los 3 anotadores (`annotator_1..3` en 0/1)."""
    r = _raiz(ALIA_REPO, raiz)
    fich = next(iter(sorted(r.glob("*human-sample.jsonl"))), None)
    if fich is None:
        raise FileNotFoundError("falta la muestra humana de ALIA en %s" % r)
    out = []
    for x in leer_tabla(fich):
        v = [str(x.get("annotator_%d" % i, "")).strip() for i in (1, 2, 3)]
        if all(a in ("0", "1") for a in v):
            out.append(dict(clave=x["id"], texto=x["text"], votos=["true" if a == "1" else "false" for a in v]))
    return out


def filas_alia(unidades, lic="cc-by-4.0", com=True):
    return _filas("alia", unidades, BINARIAS, "odio", "noul", "¿El comentario contiene discurso de odio?",
                  ODIO_DESC, "es", ALIA_REPO + " human_sample", lic, com)


def convertir_alia(raiz=None):
    r = _raiz(ALIA_REPO, raiz)
    lic, com = licencia_fuente(r, ("cc-by-4.0",), "cc-by-4.0")
    return filas_alia(registros_alia(r), lic, com)


# ---------------------------------------------------------------- toxicity-protests-ES / Constitution-ES
TOX_DESC = {"false": "mensaje no tóxico", "true": "mensaje tóxico (insulto, agresión o desprecio)"}
TOX = {
    "protests": dict(repo="bgonzalezbustamante/toxicity-protests-ES", csv="goldstd_protests.csv", corto="toxprotestas"),
    "constitution": dict(repo="bgonzalezbustamante/toxicity-Constitution-ES", csv="goldstd_Convention.csv", corto="toxconstitucion"),
}
TOX_IDIOMA = {"Argentina": "es-AR", "Chile": "es-CL"}


def registros_toxicidad(clave, raiz=None):
    cfg = TOX[clave]
    r = _raiz(cfg["repo"], raiz)
    out = []
    for x in leer_tabla(r / cfg["csv"]):
        v = [str(x.get("coder_%d" % i, "")).strip() for i in (1, 2)]
        v = [("true" if a in ("1", "1.0") else "false") for a in v if a in ("0", "1", "0.0", "1.0")]
        if len(v) == 2:
            out.append(dict(clave=x["id_obs"], texto=str(x["text"]).strip(), votos=v,
                            idioma=TOX_IDIOMA.get(x.get("country") or "Chile", "es")))
    return out


def filas_toxicidad(clave, unidades, lic="cc-by-4.0", com=True):
    cfg = TOX[clave]
    return _filas(cfg["corto"], unidades, BINARIAS, "toxicidad", "noul", "¿El mensaje es tóxico?", TOX_DESC,
                  "es", cfg["repo"], lic, com)


def convertir_toxicidad(clave, raiz=None):
    r = _raiz(TOX[clave]["repo"], raiz)
    lic, com = licencia_fuente(r, ("cc-by-4.0",), "cc-by-4.0")
    return filas_toxicidad(clave, registros_toxicidad(clave, r), lic, com)


# ---------------------------------------------------------------- GoEmotions raw (+ texto en español por id)
GE_REPO = "google-research-datasets/go_emotions"
GE_ES_REPO = "mrm8488/go_emotions-es-mt"
EMOCIONES = ["admiration", "amusement", "anger", "annoyance", "approval", "caring", "confusion", "curiosity",
             "desire", "disappointment", "disapproval", "disgust", "embarrassment", "excitement", "fear",
             "gratitude", "grief", "joy", "love", "nervousness", "optimism", "pride", "realization", "relief",
             "remorse", "sadness", "surprise", "neutral"]
EMO_DESC = dict(zip(EMOCIONES, [
    "admiración", "diversión", "enojo", "molestia", "aprobación", "cariño o cuidado", "confusión", "curiosidad",
    "deseo", "decepción", "desaprobación", "asco", "vergüenza", "entusiasmo", "miedo", "gratitud", "duelo",
    "alegría", "amor", "nerviosismo", "optimismo", "orgullo", "darse cuenta", "alivio", "remordimiento",
    "tristeza", "sorpresa", "neutral, sin emoción clara"]))
GE_MIN = 3


def voto_emocion(x):
    """Un anotador puede marcar varias emociones: se queda la de menor índice en `EMOCIONES`. None si no marcó ninguna."""
    for e in EMOCIONES:
        if int(x.get(e) or 0):
            return e
    return None


def registros_goemotions(raiz=None, raiz_es=None, minimo=GE_MIN):
    """Une `raw` con `text_es` de go_emotions-es-mt por id. Devuelve (unidades, info). Sin traducción, la unidad se descarta."""
    r, re_ = _raiz(GE_REPO, raiz), _raiz(GE_ES_REPO, raiz_es)
    trad = {}
    for p in sorted((re_ / "data").glob("*.parquet")) or sorted(re_.glob("*.parquet")):
        for x in leer_tabla(p):
            trad[x["id"]] = x["text_es"]
    votos, textos = {}, {}
    for p in sorted(r.glob("raw/*.parquet")) or sorted(r.glob("*.parquet")):
        for x in leer_tabla(p):
            e = voto_emocion(x)
            if e is not None:
                votos.setdefault(x["id"], []).append(e)
                textos[x["id"]] = x["text"]
    unidades, sin_trad, pocos = [], 0, 0
    for i, v in votos.items():
        if len(v) < minimo:
            pocos += 1
        elif i not in trad:
            sin_trad += 1
        else:
            unidades.append(dict(clave=i, texto=str(trad[i]).strip(), votos=v))
    return unidades, {"ids_raw": len(votos), "sin_traduccion": sin_trad, "con_menos_de_%d_anotadores" % minimo: pocos}


def filas_goemotions(unidades, lic="apache-2.0", com=True):
    # El texto es la traducción automática, pero los anotadores vieron el original inglés: idioma "en".
    return _filas("goemotions", unidades, EMOCIONES, "emocion", "choice", "¿Qué emoción expresa el mensaje?",
                  EMO_DESC, "en", GE_REPO + " raw + " + GE_ES_REPO, lic, com)


def convertir_goemotions(raiz=None, raiz_es=None):
    r, re_ = _raiz(GE_REPO, raiz), _raiz(GE_ES_REPO, raiz_es)
    lic, com = licencia_fuente(r, ("apache-2.0",), "apache-2.0")
    lic2, com2 = licencia_fuente(re_, ("apache-2.0",), "apache-2.0")
    if not (com and com2):
        lic, com = "%s / %s" % (lic, lic2), False
    unidades, info = registros_goemotions(r, re_)
    return filas_goemotions(unidades, lic, com), info
