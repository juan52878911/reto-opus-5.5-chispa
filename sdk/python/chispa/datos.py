"""Lectura de ejemplos (CSV/JSONL) y esquemas (YAML/JSON) de `chispa train`."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

from .cliente import ChispaError
from .tipos import KINDS, Opcion, Pregunta

_TEXTO = ("texto", "text", "estado", "state", "mensaje")
_ETIQ = ("etiqueta", "label", "clase")


def _pick(fila: dict, nombres, donde: str):
    for n in nombres:
        if n in fila and fila[n] not in (None, ""):
            return str(fila[n])
    raise ChispaError(f"{donde}: falta la columna {' | '.join(nombres)}")


SEP_MULTI = "|"
SEPARADORES = "\x1d\x1e\x1f"  # el servidor los rechaza (invalid_characters): HashEsquema2 los usa de separadores


def etiquetas_multi(v) -> Tuple[str, ...]:
    """Las etiquetas de un ejemplo multietiqueta: «a|b» (o una lista JSON) → ("a", "b"); vacío = ninguna. Sin repetidas, en orden."""
    if isinstance(v, (list, tuple)):
        partes = [str(x).strip() for x in v]
    else:
        partes = [x.strip() for x in str(v or "").split(SEP_MULTI)]
    return tuple(dict.fromkeys(p for p in partes if p))


def cargar_ejemplos(ruta, pregunta_id: Optional[str] = None, multi: bool = False) -> List[Tuple[str, str]]:
    """[(texto, etiqueta)]. CSV (con cabecera) o JSONL; columnas `texto|text` y `etiqueta|label`. Con una columna
    `pregunta`, se queda con las filas de `pregunta_id`. Con `multi=True` la etiqueta es una tupla: las etiquetas separadas por
    `|` en el CSV (o una lista en el JSONL); la celda vacía es «ninguna etiqueta»."""
    p = Path(ruta)
    filas = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        if p.suffix.lower() in (".jsonl", ".json", ".ndjson"):
            for n, linea in enumerate(f, 1):
                if linea.strip():
                    try:
                        filas.append((f"{p.name}:{n}", json.loads(linea)))
                    except ValueError as e:
                        raise ChispaError(f"{p.name}:{n}: JSON inválido: {e}") from None
        else:
            filas = [(f"{p.name}:{n}", r) for n, r in enumerate(csv.DictReader(f), 2)]
    out = []
    for donde, r in filas:
        if not isinstance(r, dict):
            raise ChispaError(f"{donde}: se esperaba un objeto")
        if pregunta_id and r.get("pregunta") not in (None, "", pregunta_id) and "pregunta" in r:
            continue
        if multi:
            col = next((n for n in _ETIQ if n in r), None)
            if col is None:
                raise ChispaError(f"{donde}: falta la columna {' | '.join(_ETIQ)}")
            out.append((_pick(r, _TEXTO, donde), etiquetas_multi(r[col])))
        else:
            out.append((_pick(r, _TEXTO, donde), _pick(r, _ETIQ, donde)))
    if not out:
        raise ChispaError(f"{p}: sin ejemplos")
    return out


def _leer_mapa(ruta) -> dict:
    p = Path(ruta)
    txt = p.read_text(encoding="utf-8")
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            raise ChispaError("esquema YAML: falta PyYAML (`pip install chispa[yaml]`) o usa un esquema .json") from None
        d = yaml.safe_load(txt)
    else:
        d = json.loads(txt)
    if not isinstance(d, dict):
        raise ChispaError(f"{p}: el esquema debe ser un mapa")
    return d


def cargar_esquema(ruta, pregunta_id: Optional[str] = None) -> Tuple[Pregunta, dict]:
    """(pregunta, extra). Esquema: `{id, pregunta, tipo, opciones, [licencias], [dorado]}`; `opciones` es un mapa
    id → descripción, una lista de ids o una lista de `{id, descripcion}`. Con `preguntas: [...]` hay que elegir una
    (un `.chispa` por pregunta, porque L0 se elige por el conjunto de etiquetas)."""
    d = _leer_mapa(ruta)
    extra = {"licencias": d.get("licencias") or {}, "dorado": d.get("dorado") or ""}
    if "preguntas" in d:
        qs = d["preguntas"]
        if pregunta_id:
            qs = [q for q in qs if q.get("id") == pregunta_id]
        if len(qs) != 1:
            raise ChispaError("el esquema trae varias preguntas: elige una con --pregunta ID (un .chispa por pregunta)")
        d = qs[0]
    for k in ("id", "pregunta"):
        if not d.get(k):
            raise ChispaError(f"esquema: falta «{k}»")
    kind = d.get("tipo", d.get("kind", "choice"))
    if kind not in KINDS:
        raise ChispaError(f"esquema: tipo {kind!r} no válido {KINDS}")
    ops = d.get("opciones")
    if kind == "noul" and not ops:
        ops = {"false": "", "true": ""}
    if kind == "score" and isinstance(ops, int):
        ops = [str(i) for i in range(1, ops + 1)]
    if isinstance(ops, dict):
        lista = [Opcion(str(k), str(v or "")) for k, v in ops.items()]
    elif isinstance(ops, list):
        lista = [Opcion(str(o)) if not isinstance(o, dict) else
                 Opcion(str(o["id"]), str(o.get("descripcion", o.get("description")) or "")) for o in ops]
    else:
        raise ChispaError("esquema: «opciones» debe ser un mapa o una lista")
    campos = [("id", d["id"]), ("pregunta", d["pregunta"])]
    campos += [(f"opciones[{j}].{c}", v) for j, o in enumerate(lista) for c, v in (("id", o.id), ("descripcion", o.description))]
    for donde, t in campos:
        if any(c in str(t) for c in SEPARADORES):
            raise ChispaError(f"esquema: {donde}: no admite los caracteres de control U+001D–U+001F (el servidor responde invalid_characters)")
    ids = [o.id for o in lista]
    if len(ids) < 2 or len(set(ids)) != len(ids):
        raise ChispaError("esquema: ≥ 2 opciones con id único")
    if kind == "multi" and any(SEP_MULTI in i for i in ids):
        raise ChispaError(f"esquema: en multi los ids no pueden llevar «{SEP_MULTI}» (separa las etiquetas de los ejemplos)")
    if kind == "noul" and sorted(ids) != ["false", "true"]:
        raise ChispaError("esquema: noul solo admite las opciones false y true")
    return Pregunta(str(d["id"]), str(d["pregunta"]), kind, tuple(lista)), extra


def validar(ejemplos, q: Pregunta) -> Counter:
    ids = {o.id for o in q.options}
    desconocidas = Counter(e for _, e in ejemplos if e not in ids)
    if desconocidas:
        raise ChispaError(f"etiquetas que no son opciones del esquema: {dict(desconocidas.most_common(5))}")
    cuenta = Counter(e for _, e in ejemplos)
    faltan = sorted(ids - set(cuenta))
    if faltan:
        raise ChispaError(f"opciones sin ningún ejemplo: {faltan}")
    return cuenta


def validar_multi(ejemplos, q: Pregunta) -> Counter:
    """Cuenta los ejemplos positivos de cada opción (puede haber opciones con 0: en multi no es un error). Las etiquetas deben ser opciones."""
    ids = {o.id for o in q.options}
    desconocidas = Counter(e for _, es in ejemplos for e in es if e not in ids)
    if desconocidas:
        raise ChispaError(f"etiquetas que no son opciones del esquema: {dict(desconocidas.most_common(5))}")
    cuenta = Counter({i: 0 for i in ids})
    cuenta.update(e for _, es in ejemplos for e in es)
    return cuenta
