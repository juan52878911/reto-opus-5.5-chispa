"""Clandestino (`microsoft/Clandestino`, GitHub, MIT): mensajes anotados -> filas de Chispa, solo los escritos por personas (W11, ajuste v3).

Datos: `data/clandestino_no_ontology_42023.json`, una fila JSON por línea (también se acepta una lista JSON). Licencia MIT, con la condición de uso de
Microsoft («no dañar», sin vigilancia; aceptada por Juan el 2026-11-02, ver `LICENCIAS.md`).

Fila: `Key`, `Sentence`, `IsAIGenerated` ("True"/"False"), `Index`, `Switch` y `Annotators` (5 a 12 dicts con `Annotator` y una clave por pregunta). Las
preguntas se identifican por prefijo («Question 1:», «Question 7:»…), no por el texto entero. Si falta una clave esperada, `ValueError` con lo que trae la fila.

Conversión (decidida por el orquestador):
  filtro   IsAIGenerated == "False" y ningún anotador con Q7 (PII) = Yes (esas filas se descartan y se cuentan).
  score    Q1 (dañino, 1..5): mediana de los anotadores, redondeada (la mitad hacia arriba) -> ids «1»..«5».
  noul     dañino: mediana de Q1 >= 3 (sin redondear) -> `true`/`false`.
  noul     Q3 (sexual) y Q8 (información falsa): `true` si más de la mitad de los anotadores dice Yes, `false` si más de la mitad dice No; Maybe no
           cuenta y sin mayoría estricta la fila se omite.
  multi    el esquema no tiene `multi`: cada grupo de Q4 que marca más de la mitad de los anotadores (sin «21. No aplicable») y con al menos `MIN_GRUPO`
           mensajes da una fila `noul` «¿el mensaje se refiere al grupo X?» por mensaje.
Splits: `split_por_clave(Key, 0.1, 0.1)`; `plantilla` = Key, así que todas las filas de un mensaje caen en el mismo split.

    python -m model.datos.clandestino contar FICHERO     # recuento en JSON (lo corre ajuste.sh antes de entrenar)
"""
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from .comun import FuenteAusente, fila, raiz_hf, split_por_clave

REPO = "microsoft/Clandestino"
URL = "https://raw.githubusercontent.com/microsoft/Clandestino/main/data/clandestino_no_ontology_42023.json"
CORTO = "clandestino"
LICENCIA = "MIT"
MIN_GRUPO = 20   # grupos con menos mensajes no dan pregunta (sin soporte para aprender nada)
NO_APLICABLE = 21
ENV_FICHERO = "CHISPA_CLANDESTINO"

CLAVES_FILA = ("Key", "Sentence", "IsAIGenerated", "Annotators")
PREGUNTAS = {1: "Question 1:", 3: "Question 3:", 4: "Question 4:", 7: "Question 7:", 8: "Question 8:"}

PREGUNTA_SCORE = "¿Qué tan dañino es el mensaje para alguien, de 1 (nada dañino) a 5 (muy dañino)?"
DESC_SCORE = {"1": "nada dañino: no perjudica ni ofende a nadie", "2": "poco dañino: un tono incómodo o un comentario leve",
              "3": "dañino a medias: puede ofender o perjudicar a alguien", "4": "dañino: ofensa o perjuicio claros contra alguien",
              "5": "muy dañino: ataque, humillación o daño severo"}
PREGUNTA_SINO = "¿El mensaje es dañino para alguien?"
DESC_SINO = {"false": "false: no (el mensaje no daña a nadie)", "true": "true: sí (el mensaje ofende, humilla, amenaza o perjudica a alguien)"}
PREGUNTA_SEXUAL = "¿El mensaje contiene o alude a contenido o actos sexuales?"
DESC_SEXUAL = {"false": "false: no (no hay contenido sexual ni alusión a él)", "true": "true: sí (contiene o alude a contenido o actos sexuales)"}
PREGUNTA_FALSA = "¿El mensaje contiene información falsa?"
DESC_FALSA = {"false": "false: no (no contiene información falsa)", "true": "true: sí (afirma o da por cierto algo falso)"}
PREGUNTA_GRUPO = "¿El mensaje se refiere al grupo «%s»?"
DESC_GRUPO = {"false": "false: no (el mensaje no menciona ni apunta a ese grupo)", "true": "true: sí (el mensaje menciona o apunta a ese grupo)"}


def _pregunta(anot, n):
    """Valor de la pregunta `n` de un anotador, buscada por prefijo («Question 7:»), o None si no está."""
    pref = PREGUNTAS[n]
    for k, v in anot.items():
        if k.strip().startswith(pref):
            return v
    return None


def _falta(r, donde, claves):
    raise ValueError("clandestino: falta %s en %s; la fila %r trae %s" % (", ".join(claves), donde, r.get("Key"), sorted(r)))


def _validar_fila(r):
    if not isinstance(r, dict):
        raise ValueError("clandestino: se esperaba un objeto JSON por fila y llegó %r" % (type(r).__name__,))
    faltan = [k for k in CLAVES_FILA if k not in r]
    if faltan:
        _falta(r, "la fila", faltan)
    if not isinstance(r["Annotators"], list) or not r["Annotators"]:
        raise ValueError("clandestino: Annotators de %r no es una lista con anotadores; la fila trae %s" % (r.get("Key"), sorted(r)))
    for a in r["Annotators"]:
        faltan = [PREGUNTAS[n] for n in PREGUNTAS if _pregunta(a, n) is None]
        if faltan:
            raise ValueError("clandestino: falta %s en un anotador de la fila %r; el anotador trae %s" % (", ".join(faltan), r["Key"], sorted(a)))


def _bool_ia(v):
    s = str(v).strip().lower()
    if s in ("true", "1"):
        return True
    if s in ("false", "0"):
        return False
    raise ValueError("clandestino: IsAIGenerated ilegible: %r (se esperaba \"True\"/\"False\")" % (v,))


def _yn(v):
    return str(v).strip().lower()


def _dañino(anots):
    """Votos válidos de Q1 (enteros 1..5)."""
    out = []
    for a in anots:
        try:
            x = int(float(str(_pregunta(a, 1)).strip()))
        except ValueError:
            continue
        if 1 <= x <= 5:
            out.append(x)
    return out


def _mayoria_yn(anots, n):
    c = Counter(_yn(_pregunta(a, n)) for a in anots)
    if c["yes"] * 2 > len(anots):
        return "true"
    if c["no"] * 2 > len(anots):
        return "false"
    return None


def _grupos(anots):
    """Grupos de Q4 que marca más de la mitad de los anotadores, sin «21. No aplicable»: {nombre sin número}."""
    c = Counter()
    for a in anots:
        propios = {g.strip() for g in str(_pregunta(a, 4) or "").split(";") if g.strip()}
        c.update(propios)
    out = set()
    for g, n in c.items():
        m = re.match(r"(\d+)\.\s*(.*)$", g)
        if m and int(m.group(1)) == NO_APLICABLE:
            continue
        if n * 2 > len(anots):
            out.add(m.group(2).strip() if m else g)
    return out


def _slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def leer_filas(ruta):
    """Filas de un fichero (una por línea o lista JSON) o de los ficheros `*.json`/`*.jsonl` de un directorio (sin README ni ocultos)."""
    ruta = Path(ruta)
    if ruta.is_dir():
        ficheros = sorted(p for p in ruta.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl") and not p.name.startswith("."))
        if not ficheros:
            raise ValueError("clandestino: %s no trae ficheros .json/.jsonl" % ruta)
    else:
        ficheros = [ruta]
    for p in ficheros:
        with open(p, encoding="utf-8") as fh:
            primero = fh.read(1)
            fh.seek(0)
            if primero == "[":
                yield from json.load(fh)
                continue
            for i, linea in enumerate(fh, 1):
                if linea.strip():
                    try:
                        yield json.loads(linea)
                    except ValueError as e:
                        raise ValueError("clandestino: %s línea %d no es JSON: %s" % (p.name, i, e))


def _origen(raiz):
    if raiz:
        return Path(raiz)
    if os.environ.get(ENV_FICHERO):
        return Path(os.environ[ENV_FICHERO])
    return Path(raiz_hf(REPO))   # FuenteAusente si no está


def convertir(raiz=None, min_grupo=MIN_GRUPO):
    """-> (filas, info). `raiz`: fichero o directorio; por defecto $CHISPA_CLANDESTINO o ~/hf."""
    info = {"licencia": LICENCIA, "leidas": 0, "descartadas_ia": 0, "descartadas_pii": 0, "descartadas_invalidas": Counter(),
            "omitidas": Counter(), "condicion_de_uso": "Microsoft: no dañar, sin vigilancia (aceptada por Juan, 2026-11-02)"}
    humanas = []
    for r in leer_filas(_origen(raiz)):
        info["leidas"] += 1
        _validar_fila(r)
        if _bool_ia(r["IsAIGenerated"]):
            info["descartadas_ia"] += 1
        elif any(_yn(_pregunta(a, 7)) == "yes" for a in r["Annotators"]):
            info["descartadas_pii"] += 1
        elif not str(r["Sentence"] or "").strip() or not str(r["Key"] or "").strip():
            info["descartadas_invalidas"]["sin_texto_o_key"] += 1
        else:
            humanas.append(r)
    propios = [_grupos(r["Annotators"]) for r in humanas]
    n_grupo = Counter(g for s in propios for g in s)
    grupos = sorted(g for g, n in n_grupo.items() if n >= min_grupo)
    info["grupos"] = grupos
    cont, out = Counter(), []
    for r, gs in zip(humanas, propios):
        key, texto, anots = str(r["Key"]).strip(), str(r["Sentence"]).strip(), r["Annotators"]
        split = split_por_clave(key, 0.1, 0.1, CORTO)
        fuente = "%s (IsAIGenerated = False, sin PII)" % REPO

        def emite(tarea, tipo, pregunta, ops, desc, et):
            out.append(fila(CORTO, split, cont[split], tarea, tipo, pregunta, texto, ops, desc, et, "es", fuente, LICENCIA, True, key))
            cont[split] += 1
        votos = _dañino(anots)
        if votos:
            med = statistics.median(votos)
            emite("clandestino_gravedad", "score", PREGUNTA_SCORE, [str(i) for i in range(1, 6)], DESC_SCORE, str(int(med + 0.5)))
            emite("clandestino_danino", "noul", PREGUNTA_SINO, ["false", "true"], DESC_SINO, "true" if med >= 3 else "false")
        else:
            info["descartadas_invalidas"]["sin_votos_validos_q1"] += 1
        for n, tarea, preg, desc in ((3, "clandestino_sexual", PREGUNTA_SEXUAL, DESC_SEXUAL), (8, "clandestino_falsa", PREGUNTA_FALSA, DESC_FALSA)):
            m = _mayoria_yn(anots, n)
            if m is None:
                info["omitidas"][tarea] += 1
            else:
                emite(tarea, "noul", preg, ["false", "true"], desc, m)
        for g in grupos:
            emite("clandestino_grupo_" + _slug(g), "noul", PREGUNTA_GRUPO % g, ["false", "true"], DESC_GRUPO, "true" if g in gs else "false")
    info["descartadas_invalidas"], info["omitidas"] = dict(info["descartadas_invalidas"]), dict(info["omitidas"])
    info["columnas"] = {"texto": "Sentence", "clave": "Key", "ia": "IsAIGenerated", "anotadores": "Annotators"}   # lo muestra ajuste.sh
    return out, info


def contar(ruta, min_grupo=MIN_GRUPO):
    filas, info = convertir(ruta, min_grupo)
    por = {}
    for f in filas:
        por.setdefault(f["tipo"], Counter())[f["split"]] += 1
    return {"filas_leidas": info["leidas"], "descartadas_ia": info["descartadas_ia"], "descartadas_pii": info["descartadas_pii"],
            "descartadas_invalidas": info["descartadas_invalidas"], "omitidas_sin_mayoria": info["omitidas"], "filas_validas": len(filas),
            "filas_por_tipo_y_split": {t: dict(sorted(c.items())) for t, c in sorted(por.items())},
            "distribucion_score": dict(sorted(Counter(f["etiqueta"] for f in filas if f["tipo"] == "score").items())), "grupos": info["grupos"]}


def main(argv):
    if len(argv) != 3 or argv[1] != "contar":
        print("uso: python -m model.datos.clandestino contar FICHERO", file=sys.stderr)
        return 2
    try:
        print(json.dumps(contar(argv[2]), ensure_ascii=False, indent=2, sort_keys=True))
    except (ValueError, OSError) as e:
        print("clandestino: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
