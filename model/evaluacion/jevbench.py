"""Adaptador de JevBench (https://github.com/fstandhartinger/jevbench, harness MIT) al esquema de filas de model/esquema.md.

Formato real: `datasets/public/{easy,hard,original}.jsonl` del repo (231 casos, JSONL, un caso por línea):

    {"id": "easy-intent-00", "family": "intent", "group": null | "<id de grupo de paráfrasis>", "split": "public",
     "state": str | dict,                       # el contenido que se decide (un dict se serializa a JSON)
     "question": {"type": "choice" | "noul" | "score", "instructions": "...", "criteria": {opción: descripción} | [niveles] | null},
     "labels": ["a", "b", ...],                 # choice: ids; noul: ["no", "yes"]; score: ["0", "1", ...] (índice de nivel)
     "expected": "a" | "yes" | 2,               # oro (int para score)
     "provenance": {"license": "MIT", "source": "...", ...}}

Conversión: choice → opciones = labels, descripciones = criteria; noul → opciones ["false", "true"] (no→false, yes→true; las
descripciones salen de criteria["false"|"true"]); score → opciones "1".."K" (nivel + 1, como pide model/esquema.md; criteria es una lista).
La etiqueta predicha de un score es la mediana CORAL (número de umbrales con P(y>j) > 0,5; `metricas.top1`), no el argmax.
Campos añadidos a la fila: `esquema` (hash de tipo + instrucciones + labels + criteria: casos con el mismo esquema comparten
pregunta y opciones), `grupo` (paráfrasis del mismo caso: nunca se usan como soporte uno del otro) y `oro_jev` (el `expected` original).

`ruta`: el clon del repo, su `datasets/public/`, o un `.jsonl` suelto.
"""
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

SPLITS = ("easy", "hard", "original")
LICENCIAS_COMERCIALES = {"MIT"}


def _texto(state):
    return state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)


def esquema_id(c):
    q = c["question"]
    clave = json.dumps([q["type"], q.get("instructions", ""), c["labels"], q.get("criteria")], ensure_ascii=False, sort_keys=True)
    return "jev:" + hashlib.sha1(clave.encode("utf-8")).hexdigest()[:10]


def _a_fila(c, origen="jevbench"):
    for k in ("id", "family", "state", "question", "labels", "expected"):
        if k not in c:
            raise ValueError(f"caso JevBench {c.get('id', '?')}: falta '{k}'")
    q, labels, crit, oro = c["question"], [str(x) for x in c["labels"]], c["question"].get("criteria"), c["expected"]
    tipo = q.get("type")
    if tipo == "choice":
        crit = crit or {}
        ops, desc, etq = labels, {o: crit.get(o, "") for o in labels}, str(oro)
    elif tipo == "noul":
        if sorted(labels) != ["no", "yes"]:
            raise ValueError(f"caso JevBench {c['id']}: noul con labels {labels}")
        crit = crit or {}
        ops, desc, etq = ["false", "true"], {"false": crit.get("false", ""), "true": crit.get("true", "")}, {"no": "false", "yes": "true"}[str(oro)]
    elif tipo == "score":
        if not isinstance(oro, int) or str(oro) not in labels:
            raise ValueError(f"caso JevBench {c['id']}: nivel {oro!r} fuera de labels {labels}")
        niv = list(crit or [])
        ops, desc, etq = [str(i + 1) for i in range(len(labels))], {str(i + 1): (niv[i] if i < len(niv) else "") for i in range(len(labels))}, str(oro + 1)
    else:
        raise ValueError(f"caso JevBench {c['id']}: tipo de pregunta desconocido {tipo!r}")
    if etq not in ops:
        raise ValueError(f"caso JevBench {c['id']}: oro '{etq}' fuera de las opciones {ops}")
    lic = (c.get("provenance") or {}).get("license", "desconocida")
    return {
        "id": f"jev:public:{c['id']}", "tarea": c["family"], "tipo": tipo, "pregunta": q.get("instructions", ""), "texto": _texto(c["state"]),
        "opciones": ops, "descripciones": desc, "etiqueta": etq, "idioma": "en", "split": "test",
        "fuente": f"JevBench {origen}", "licencia": lic, "uso_comercial": lic in LICENCIAS_COMERCIALES,
        "esquema": esquema_id(c), "grupo": c.get("group"), "oro_jev": oro,
    }


def _ficheros(ruta):
    p = Path(ruta)
    if p.is_file():
        return [p]
    d = p / "datasets" / "public" if (p / "datasets" / "public").is_dir() else p
    fs = [d / f"{s}.jsonl" for s in SPLITS if (d / f"{s}.jsonl").is_file()]
    if not fs:
        raise ValueError(f"{ruta}: no hay datasets/public/{{easy,hard,original}}.jsonl")
    return fs


def cargar_jevbench(ruta):
    """ruta (clon, datasets/public o un .jsonl) -> lista de filas del esquema, en orden easy, hard, original."""
    filas, vistos = [], set()
    for f in _ficheros(ruta):
        with open(f, encoding="utf-8") as fh:
            for n, linea in enumerate(fh, 1):
                if not linea.strip():
                    continue
                try:
                    c = json.loads(linea)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{f.name}:{n}: JSON inválido ({e})") from None
                r = _a_fila(c, f.stem)
                if r["id"] in vistos:
                    raise ValueError(f"id repetido: {r['id']}")
                vistos.add(r["id"])
                filas.append(r)
    return filas


def soporte(fila, filas, k, semilla=0):
    """Soporte de `fila` dentro de `filas`: casos con su mismo esquema, SIN el propio caso ni sus paráfrasis (mismo `grupo`), con
    como mucho `k` por opción (orden por id, barajado con semilla fija: como model.l2.datos.soporte_t17a). Puede salir vacío."""
    por = defaultdict(list)
    for r in filas:
        if r["esquema"] != fila["esquema"] or r["id"] == fila["id"] or (fila.get("grupo") and r.get("grupo") == fila["grupo"]):
            continue
        por[r["etiqueta"]].append(r)
    rng, out = random.Random(semilla), []
    for c in sorted(por):
        g = sorted(por[c], key=lambda r: r["id"])
        rng.shuffle(g)
        out += g[:k]
    return out


def pliegues(filas, k, semilla=0):
    """[(clave, casos, soporte)]: casos que comparten esquema y grupo comparten soporte (el que deja fuera a todos ellos), así que
    se entrena/calcula una vez por pliegue. Un caso sin grupo es su propio pliegue (dejar uno fuera)."""
    por = defaultdict(list)
    for r in filas:
        por[(r["esquema"], r.get("grupo") or r["id"])].append(r)
    return [(c, rs, soporte(rs[0], filas, k, semilla)) for c, rs in por.items()]


def cubre_opciones(fila, sop):
    """True si el soporte tiene al menos un ejemplo de cada opción (lo que exige `chispa train`)."""
    return set(fila["opciones"]) <= {r["etiqueta"] for r in sop}
