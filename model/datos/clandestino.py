"""Clandestino (`microsoft/Clandestino`): mensajes anotados -> filas de Chispa, solo los escritos por personas (W9, ajuste v3).

Licencia: MIT, con la condición de uso de Microsoft («no dañar», sin vigilancia). Juan la aceptó el 2026-11-02 (ver `LICENCIAS.md`).
Como el resto de conversores, solo se da por buena si la tarjeta del snapshot dice `license: mit`; si no, «sin verificar», `uso_comercial: false`
y solo se emite `test`.

COLUMNAS: HIPÓTESIS, SIN VERIFICAR. El dataset no está en `~/hf` y la máquina no tiene red, así que no se ha podido leer ni la tarjeta ni una fila
real. Lo único dado por el encargo es la columna `Is AI Generated` (se conservan las filas con `false`) y que hay anotaciones de las cuatro clases:
puntuación 1..5, sí/no, tipo y grupos. Los nombres de abajo son lo que se espera (sin distinguir mayúsculas, espacios, guiones ni guiones bajos):

    Text              el mensaje                                   (alias: message, utterance, content)
    Is AI Generated   true/false: solo se conservan las false      (obligatoria)
    Template ID       plantilla/semilla que generó el mensaje      (alias: template, seed, scenario id, prompt id); obligatoria: reparte
                      train/dev/test por plantilla, sin fugas
    Language          idioma del mensaje                           (alias: locale, lang); si falta, «en»
    Score             entero 1..5 -> `score`, ids «1»..«5»         (alias: rating, severity)
    Label             sí/no -> `noul`                              (alias: is harmful, harmful, is toxic, toxic)
    Type              una categoría -> `choice`                    (alias: category, content type, harm type)
    Groups            varias etiquetas -> `multi`                  (alias: target groups, targets, groups targeted)

Cada anotación presente da una familia de filas; las ausentes se omiten (pero tiene que haber al menos una). Si falta `Text`, `Is AI Generated`
o la plantilla, o no hay ninguna anotación, `convertir` lanza `ValueError` con las columnas que sí trae el fichero: así `ajuste.sh` falla antes de
gastar GPU y se corrige este módulo con las columnas reales. Las preguntas y descripciones en español son una hipótesis de qué mide cada columna
(gravedad 1..5, ¿dañino?, tipo y grupos aludidos) y hay que revisarlas con la tarjeta real.

multi: el esquema (`esquema.md`) no tiene `multi`; cada grupo (con al menos `MIN_GRUPO` mensajes) da una fila `noul` «¿el mensaje se refiere al
grupo X?» por mensaje, con `plantilla` igual que el resto de sus filas.
Filas inválidas (puntuación fuera de 1..5, valor sí/no ilegible, tipo vacío) se descartan y se cuentan en `info`; nada se corrige.
Splits: `split_por_clave(plantilla, 0.1, 0.1)`: todas las filas de una plantilla, de todas las anotaciones, caen en el mismo split.
"""
import re
from collections import Counter
from pathlib import Path

from .comun import EXT, fila, leer_tabla, licencia_fuente, raiz_hf, split_por_clave

REPO = "microsoft/Clandestino"
CORTO = "clandestino"
MIN_GRUPO = 20   # grupos con menos mensajes no dan pregunta (sin soporte para aprender nada)

ALIAS = {
    "texto": ("text", "message", "utterance", "content"),
    "ia": ("isaigenerated",),
    "plantilla": ("templateid", "template", "seed", "scenarioid", "promptid"),
    "idioma": ("language", "locale", "lang"),
    "score": ("score", "rating", "severity"),
    "sino": ("label", "isharmful", "harmful", "istoxic", "toxic"),
    "tipo": ("type", "category", "contenttype", "harmtype"),
    "grupos": ("groups", "targetgroups", "targets", "groupstargeted"),
}
VERDADERO = {"true", "1", "yes", "si", "sí", "y", "t"}
FALSO = {"false", "0", "no", "n", "f"}

PREGUNTA_SCORE = "¿Qué tan grave es el contenido del mensaje, de 1 (nada grave) a 5 (muy grave)?"
DESC_SCORE = {"1": "nada grave: no hay nada dañino ni ofensivo", "2": "poco grave: un tono incómodo o un comentario leve",
              "3": "gravedad media: ofensivo o dañino, pero sin ensañamiento", "4": "grave: ofensa o daño claros contra alguien",
              "5": "muy grave: ataque, amenaza o daño severo"}
PREGUNTA_SINO = "¿El mensaje es dañino para alguien?"
DESC_SINO = {"false": "false: no (el mensaje no daña a nadie)", "true": "true: sí (el mensaje ofende, humilla, amenaza o perjudica a alguien)"}
PREGUNTA_TIPO = "¿De qué tipo es el contenido del mensaje?"
PREGUNTA_GRUPO = "¿El mensaje se refiere al grupo «%s»?"
DESC_GRUPO = {"false": "false: no (el mensaje no menciona ni apunta a ese grupo)", "true": "true: sí (el mensaje menciona o apunta a ese grupo)"}


def _norm(c):
    return re.sub(r"[^a-z0-9]", "", str(c).lower())


def columnas(muestra):
    """{clave: nombre real de la columna} según ALIAS, para el conjunto de columnas de una fila."""
    por_norm = {_norm(c): c for c in muestra}
    return {k: next((por_norm[a] for a in al if a in por_norm), None) for k, al in ALIAS.items()}


def _bool(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return True if s in VERDADERO else False if s in FALSO else None


def _lista(v):
    """Valor multi: lista, JSON de lista o texto separado por `;` `|` `,`."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    if s.startswith("["):
        import json
        try:
            return [str(x).strip() for x in json.loads(s) if str(x).strip()]
        except ValueError:
            pass
        s = s.strip("[]").replace("'", "").replace('"', "")
    return [x.strip() for x in re.split(r"[;|,]", s) if x.strip()]


def leer_filas(raiz):
    """Todas las filas de todos los ficheros de datos del snapshot (parquet/csv/tsv/json/jsonl, con o sin .gz)."""
    ficheros = sorted(p for p in Path(raiz).rglob("*") if p.is_file() and p.name != "README.md" and not p.name.startswith(".")
                      and p.name.endswith(EXT) and "/.git" not in str(p))
    if not ficheros:
        raise ValueError("clandestino: el snapshot %s no trae ficheros de datos (%s)" % (raiz, ", ".join(EXT)))
    filas = []
    for p in ficheros:
        filas.extend(leer_tabla(p))
    return filas


def convertir(raiz=None, min_grupo=MIN_GRUPO):
    raiz = Path(raiz or raiz_hf(REPO))
    lic, com = licencia_fuente(raiz, ("mit",), "MIT", True)
    crudas = leer_filas(raiz)
    if not crudas:
        raise ValueError("clandestino: los ficheros de %s no traen filas" % raiz)
    col = columnas(crudas[0])
    vistas = sorted(crudas[0])
    for k, nombre in (("texto", "Text"), ("ia", "Is AI Generated"), ("plantilla", "Template ID")):
        if col[k] is None:
            raise ValueError("clandestino: falta la columna %s (alias %s); el fichero trae %s. Las columnas de este conversor son una hipótesis "
                             "(ver el docstring de model/datos/clandestino.py): hay que ajustarlas a la tarjeta real" % (nombre, ", ".join(ALIAS[k]), vistas))
    if not any(col[k] for k in ("score", "sino", "tipo", "grupos")):
        raise ValueError("clandestino: no hay ninguna columna de anotación (score/rating, label, type, groups); el fichero trae %s. "
                         "Hipótesis sin verificar: ver model/datos/clandestino.py" % (vistas,))
    info = {"licencia": lic, "columnas": {k: v for k, v in col.items() if v}, "descartadas_ia": 0, "descartadas_invalidas": Counter(),
            "condicion_de_uso": "Microsoft: no dañar, sin vigilancia (aceptada por Juan, 2026-11-02)"}
    humanas = []
    for r in crudas:
        ia = _bool(r.get(col["ia"]))
        if ia is None:
            raise ValueError("clandestino: valor ilegible en Is AI Generated: %r (se esperaba true/false)" % (r.get(col["ia"]),))
        texto = str(r.get(col["texto"]) or "").strip()
        if ia:
            info["descartadas_ia"] += 1
        elif not texto or r.get(col["plantilla"]) in (None, ""):
            info["descartadas_invalidas"]["sin_texto_o_plantilla"] += 1
        else:
            humanas.append((r, texto, str(r[col["plantilla"]]).strip()))
    tipos = sorted({str(r[col["tipo"]]).strip() for r, _, _ in humanas if col["tipo"] and str(r.get(col["tipo"]) or "").strip()})
    grupos_n = Counter(g for r, _, _ in humanas if col["grupos"] for g in set(_lista(r.get(col["grupos"]))))
    grupos = sorted(g for g, n in grupos_n.items() if n >= min_grupo)
    info["tipos"], info["grupos"] = tipos, grupos
    cont, descartadas_nc, out = Counter(), 0, []
    for r, texto, plantilla in humanas:
        split = split_por_clave(plantilla, 0.1, 0.1, CORTO)
        idioma = str(r.get(col["idioma"]) or "en").strip() if col["idioma"] else "en"
        base = dict(texto=texto, idioma=idioma, fuente="%s (Is AI Generated = false)" % REPO)

        def emite(tarea, tipo, pregunta, ops, desc, et):
            nonlocal descartadas_nc
            if not com and split != "test":   # esquema.md: una fila no comercial solo puede ir a test
                descartadas_nc += 1
                return
            out.append(fila(CORTO, split, cont[split], tarea, tipo, pregunta, base["texto"], ops, desc, et, base["idioma"], base["fuente"],
                            lic, com, plantilla))
            cont[split] += 1
        if col["score"]:
            try:
                v = int(float(str(r.get(col["score"])).strip()))
            except ValueError:
                v = None
            if v is None or not 1 <= v <= 5:
                info["descartadas_invalidas"]["score_fuera_de_1_5"] += 1
            else:
                emite("clandestino_gravedad", "score", PREGUNTA_SCORE, [str(i) for i in range(1, 6)], DESC_SCORE, str(v))
        if col["sino"]:
            b = _bool(r.get(col["sino"]))
            if b is None:
                info["descartadas_invalidas"]["sino_ilegible"] += 1
            else:
                emite("clandestino_danino", "noul", PREGUNTA_SINO, ["false", "true"], DESC_SINO, "true" if b else "false")
        if col["tipo"]:
            t = str(r.get(col["tipo"]) or "").strip()
            if not t:
                info["descartadas_invalidas"]["tipo_vacio"] += 1
            else:
                emite("clandestino_tipo", "choice", PREGUNTA_TIPO, tipos, {x: "contenido de tipo «%s»" % x for x in tipos}, t)
        if col["grupos"]:
            propios = set(_lista(r.get(col["grupos"])))
            for g in grupos:
                emite("clandestino_grupo_" + _norm(g), "noul", PREGUNTA_GRUPO % g, ["false", "true"], DESC_GRUPO, "true" if g in propios else "false")
    info["descartadas_invalidas"] = dict(info["descartadas_invalidas"])
    info["descartadas_licencia_nc_fuera_de_test"] = descartadas_nc
    return out, info
