"""`chispa evaluar --bateria`: batería de regresión de un `.chispa` (o de un servidor) con línea base y umbrales. Solo biblioteca estándar.

Un manifiesto JSON lista conjuntos de datos (filas de `model/esquema.md` o JevBench crudo). Cada fila lleva su propia pregunta y
opciones, así que un conjunto puede mezclar esquemas (JevBench) o ser una sola tarea (massive). Se manda cada fila a `/v1/decide`
(un `state` por petición), se miden exactitud, F1 macro, ECE (10 cubos), cobertura a la precisión objetivo, % escalado y p50/p99 por
conjunto, por tipo, por grupo y en global, y se compara con una línea base: si una métrica empeora más que su umbral, el comando sale ≠ 0.

El formato de JevBench está copiado en lo mínimo de `model/evaluacion/jevbench.py` (el SDK no importa `model/`). JevBench:
https://github.com/fstandhartinger/jevbench, harness bajo licencia MIT (© sus autores; la licencia de cada caso va en su `provenance`).
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import math
import os
import shutil
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional

from .cliente import Chispa, ChispaError, ErrorSolicitud
from .evaluar import (MAX_ESTADO_BYTES, _ERRORES_DE_FILA, _FALSE, _TRUE, _activas, _f, _mejor, _p, _pct)
from .tipos import KINDS, Opcion, Pregunta

VERSION = 1
OBJETIVO = 0.95
CUBOS_ECE = 10
MODULO_VARIANTES = "chispa.variantes"
HOLGURA_MS = 1.0

# Umbral = empeoramiento máximo tolerado. Absoluto (en fracción, 0,01 = un punto) salvo p50_ms/p99_ms, que son relativos (0,5 = +50 %).
UMBRALES = {"exactitud": 0.01, "f1_macro": 0.01, "cobertura": 0.02, "ece": 0.02, "escalado": 0.03, "errores": 0.0, "mae": 0.05,
            "estabilidad": 0.02, "delta_conf": 0.05, "p50_ms": 0.5, "p99_ms": 1.0}
MEJOR_ALTO = {"exactitud", "f1_macro", "cobertura", "estabilidad"}  # el resto: menos es mejor
METRICAS = tuple(UMBRALES)
SECCIONES = ("global", "tipos", "grupos", "conjuntos")


class ErrorBateria(ChispaError):
    """Manifiesto, datos o servidor mal puestos (no una regresión): el CLI sale con 2."""


# ---------------------------------------------------------------- carga de datos
@dataclass
class Fila:
    id: str
    tipo: str
    esquema: str
    q: Pregunta
    texto: str
    etiqueta: object  # str; en multi, tuple de ids


def _esquema_id(tipo, pregunta, opciones, desc) -> str:
    clave = json.dumps([tipo, pregunta, opciones, desc], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(clave.encode("utf-8")).hexdigest()[:10]


def _jev_a_fila(c: dict, origen: str) -> dict:
    """Caso JevBench crudo → fila de model/esquema.md (choice: opciones = labels; noul: no→false, yes→true; score: nivel + 1)."""
    for k in ("id", "state", "question", "labels", "expected"):
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
    st = c["state"]
    return {"id": f"jev:{origen}:{c['id']}", "tipo": tipo, "pregunta": q.get("instructions", ""), "texto": st if isinstance(st, str) else json.dumps(st, ensure_ascii=False),
            "opciones": ops, "descripciones": desc, "etiqueta": etq}


def _booleano(e) -> str:
    s = str(e).strip().lower()
    if s in _TRUE:
        return "true"
    if s in _FALSE:
        return "false"
    raise ValueError(f"etiqueta noul {e!r}: se espera true/false")


def _a_fila(r: dict) -> Fila:
    for k in ("id", "tipo", "texto", "etiqueta"):
        if k not in r:
            raise ValueError(f"falta '{k}'")
    tipo, preg, desc = r["tipo"], str(r.get("pregunta", "")), r.get("descripciones") or {}
    if tipo not in KINDS:
        raise ValueError(f"tipo {tipo!r}: debe ser uno de {', '.join(KINDS)}")
    if not isinstance(r["texto"], str):
        raise ValueError("'texto' debe ser una cadena")
    if tipo == "noul":
        ops = ["false", "true"]
    else:
        ops = [str(o) for o in (r.get("opciones") or [])]
        if len(ops) < 2:
            raise ValueError(f"{tipo} necesita ≥ 2 'opciones'")
    et = r["etiqueta"]
    if tipo == "multi":
        et = et.split("|") if isinstance(et, str) else list(et)
        et = tuple(sorted({str(x).strip() for x in et if str(x).strip()}))
        malas = [x for x in et if x not in ops]
        if malas:
            raise ValueError(f"etiquetas {malas} fuera de las opciones {ops}")
    else:
        et = _booleano(et) if tipo == "noul" else str(et).strip()
        if et not in ops:
            raise ValueError(f"etiqueta {et!r} fuera de las opciones {ops}")
    # como `cuerpo_decide` de model/evaluacion/jevbench_cascada.py: las descripciones de todas las opciones viajan, también en noul y score
    q = Pregunta("q", preg, tipo, tuple(Opcion(o, str(desc.get(o, ""))) for o in ops))
    return Fila(str(r["id"]), tipo, _esquema_id(tipo, preg, ops, {o: desc.get(o, "") for o in ops}), q, r["texto"], et)


def _ficheros(ruta: str) -> List[str]:
    if os.path.isfile(ruta):
        return [ruta]
    d = os.path.join(ruta, "datasets", "public")
    d = d if os.path.isdir(d) else ruta
    fs = [os.path.join(d, f"{s}.jsonl") for s in ("easy", "hard", "original") if os.path.isfile(os.path.join(d, f"{s}.jsonl"))]
    return fs or sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".jsonl"))


def cargar_filas(ruta: str, formato: str = "auto", tipo: Optional[str] = None, limite: Optional[int] = None, split: Optional[str] = "test") -> List[Fila]:
    """JSONL de filas (`model/esquema.md`) o JevBench crudo (`auto` lo distingue por línea: JevBench trae `state` y `question`).
    `ruta` puede ser un fichero o, para JevBench, el clon / su `datasets/public/`. `tipo` ≠ mixto exige que todas las filas lo sean.
    `split`: solo las filas con ese `split` (por defecto `test`; las filas sin campo `split`, como JevBench, entran siempre); None = todas."""
    filas, vistos = [], set()
    for fich in _ficheros(ruta):
        origen = os.path.splitext(os.path.basename(fich))[0]
        with open(fich, encoding="utf-8") as fh:
            for n, linea in enumerate(fh, 1):
                if not linea.strip():
                    continue
                try:
                    r = json.loads(linea)
                    if not isinstance(r, dict):
                        raise ValueError("la línea no es un objeto JSON")
                    if split and isinstance(r.get("split"), str) and r["split"] != split and not ("state" in r and "question" in r):
                        continue
                    jev = formato == "jevbench" or (formato == "auto" and "state" in r and "question" in r)
                    f = _a_fila(_jev_a_fila(r, origen) if jev else r)
                    if f.id in vistos:
                        raise ValueError(f"id repetido: {f.id}")
                    if tipo and tipo != "mixto" and f.tipo != tipo:
                        raise ValueError(f"tipo {f.tipo!r} en un conjunto declarado {tipo!r}")
                except (ValueError, KeyError, TypeError) as e:
                    raise ErrorBateria(f"{fich}:{n}: {e}") from None
                vistos.add(f.id)
                filas.append(f)
    if limite:
        filas = filas[:limite]
    return filas


# ---------------------------------------------------------------- manifiesto y umbrales
def _fusionar(base: dict, otro: Optional[dict]) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in (otro or {}).items():
        if k == "por_conjunto":
            pc = out.setdefault("por_conjunto", {})
            for nombre, d in (v or {}).items():
                pc[nombre] = dict(pc.get(nombre, {}), **d)
        else:
            out[k] = v
    return out


def _validar_umbrales(u: dict):
    malos = [k for k in u if k not in UMBRALES and k != "por_conjunto"]
    for d in (u.get("por_conjunto") or {}).values():
        malos += [k for k in d if k not in UMBRALES]
    if malos:  # una errata desactivaría la puerta en silencio
        raise ErrorBateria(f"umbrales desconocidos: {sorted(set(malos))}; válidos: {list(METRICAS)}")


def cargar_json(ruta: str, que: str) -> dict:
    try:
        with open(ruta, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ErrorBateria(f"{que} {ruta}: {e}") from None
    if not isinstance(d, dict):
        raise ErrorBateria(f"{que} {ruta}: se espera un objeto JSON")
    return d


def leer_manifiesto(ruta: str) -> dict:
    m = cargar_json(ruta, "manifiesto")
    cs = m.get("conjuntos")
    if not isinstance(cs, list) or not cs:
        raise ErrorBateria(f"manifiesto {ruta}: 'conjuntos' debe ser una lista no vacía")
    nombres = [c.get("nombre") for c in cs if isinstance(c, dict)]
    if len(nombres) != len(cs) or not all(isinstance(n, str) and n for n in nombres) or len(set(nombres)) != len(nombres):
        raise ErrorBateria(f"manifiesto {ruta}: cada conjunto necesita un 'nombre' único")
    for c in cs:
        if not c.get("ruta"):
            raise ErrorBateria(f"manifiesto {ruta}: el conjunto {c['nombre']!r} no tiene 'ruta'")
        if c.get("tipo", "mixto") not in KINDS + ("mixto",):
            raise ErrorBateria(f"manifiesto {ruta}: conjunto {c['nombre']!r}: tipo {c['tipo']!r}")
        if c.get("formato", "auto") not in ("auto", "filas", "jevbench"):
            raise ErrorBateria(f"manifiesto {ruta}: conjunto {c['nombre']!r}: formato {c['formato']!r}")
    _validar_umbrales(m.get("umbrales") or {})
    m["_dir"] = os.path.dirname(os.path.abspath(ruta))
    return m


def resolver_ruta(ruta: str, base: str) -> Optional[str]:
    """Expande `$VAR`/`${VAR}`; relativa al manifiesto. None si queda una variable sin definir o no existe."""
    r = os.path.expandvars(ruta)
    if "$" in r:
        return None
    r = os.path.expanduser(r)
    r = r if os.path.isabs(r) else os.path.join(base, r)
    return r if os.path.exists(r) else None


# ---------------------------------------------------------------- servidor
@contextlib.contextmanager
def servidor_local(modelo: str, servidor: Optional[str] = None, tok: Optional[str] = None, config: Optional[str] = None,
                   extra=(), espera: float = 60.0):
    """Arranca `chispa-server -modelo MODELO` en un puerto libre de loopback, espera a /healthz y lo apaga al salir. Devuelve la URL."""
    exe = servidor or os.environ.get("CHISPA_SERVER") or shutil.which("chispa-server")
    if not exe:
        raise ErrorBateria("no encuentro chispa-server: pasa --servidor RUTA, fija CHISPA_SERVER o ponlo en el PATH (o usa --url)")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    cmd = [exe, "-addr", f"127.0.0.1:{puerto}", "-modelo", modelo] + (["-tok", tok] if tok else []) + (["-config", config] if config else []) + list(extra)
    log = tempfile.TemporaryFile()
    try:
        p = subprocess.Popen(cmd, stdout=log, stderr=log)
    except OSError as e:
        log.close()
        raise ErrorBateria(f"no pude lanzar {exe}: {e}") from None
    try:
        url, c, limite = f"http://127.0.0.1:{puerto}", Chispa(f"http://127.0.0.1:{puerto}", reintentos=0, timeout=2.0), time.monotonic() + espera
        while not c.salud():
            if p.poll() is not None:
                log.seek(0)
                raise ErrorBateria(f"chispa-server terminó con código {p.returncode}: {log.read()[-600:].decode('utf-8', 'replace').strip()}")
            if time.monotonic() > limite:
                raise ErrorBateria(f"chispa-server no respondió a /healthz en {espera:.0f} s")
            time.sleep(0.2)
        yield url
    finally:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
        log.close()


# ---------------------------------------------------------------- ejecución
def _decidir(cliente: Chispa, f: Fila, texto: Optional[str] = None, reloj=time.perf_counter) -> dict:
    texto = f.texto if texto is None else texto
    r = {"id": f.id, "tipo": f.tipo, "esquema": f.esquema, "etiqueta": list(f.etiqueta) if f.tipo == "multi" else f.etiqueta,
         "opciones": [o.id for o in f.q.options] or ["false", "true"], "answer": "", "answers": None, "probs": {}, "layer": "",
         "escalate": False, "ms": None, "cliente_ms": None, "error": "", "error_codigo": ""}
    if len(texto.encode("utf-8")) > MAX_ESTADO_BYTES:
        r.update(error="texto mayor que 262144 bytes (max_estado)", error_codigo="state_too_long")
        return r
    t0 = reloj()
    try:
        x = cliente.decidir(texto, [f.q])[0]
    except ErrorSolicitud as e:
        r.update(error=str(e), error_codigo=e.codigo or f"http_{e.status}")
    except ChispaError as e:
        r.update(error=str(e), error_codigo="transporte")
    else:
        r.update(answer=x.answer, answers=x.answers, probs=x.probs, layer=x.layer, escalate=x.escalate, ms=x.ms, cliente_ms=(reloj() - t0) * 1000)
    return r


def _correr(cliente: Chispa, tareas: List[tuple], concurrencia: int) -> List[dict]:
    """tareas = [(Fila, texto|None)] → un resultado por tarea, en orden."""
    with ThreadPoolExecutor(max_workers=max(1, concurrencia)) as ex:
        return list(ex.map(lambda t: _decidir(cliente, t[0], t[1]), tareas))


# ---------------------------------------------------------------- métricas
def decisiones(r: dict) -> List[tuple]:
    """[(confianza|None, acierto)] de una fila: una por fila (choice, noul, score) o una por opción (multi: p si activa, 1−p si no)."""
    if r["tipo"] == "multi":
        act = _activas(r, r["opciones"])
        return [((None if act is None or o not in r["probs"] else (r["probs"][o] if o in act else 1 - r["probs"][o])),
                 act is not None and ((o in act) == (o in r["etiqueta"]))) for o in r["opciones"]]
    a, c = _mejor(r)
    return [(c, bool(a) and a == r["etiqueta"])]


def _acierto_fila(r: dict) -> bool:
    if r["tipo"] == "multi":
        act = _activas(r, r["opciones"])
        return act is not None and act == set(r["etiqueta"])
    return decisiones(r)[0][1]


def ece(pares, cubos: int = CUBOS_ECE) -> Optional[float]:
    """ECE de [(confianza, acierto)] con `cubos` de igual ancho, cubo = (k/cubos, (k+1)/cubos]; conf = 0 va al primero. Ignora conf None."""
    pares = [(c, o) for c, o in pares if c is not None]
    if not pares:
        return None
    n = [0] * cubos
    sc, so = [0.0] * cubos, [0.0] * cubos
    for c, o in pares:
        k = min(max(math.ceil(c * cubos - 1e-12) - 1, 0), cubos - 1)
        n[k] += 1
        sc[k] += c
        so[k] += bool(o)
    return sum(n[k] / len(pares) * abs(so[k] / n[k] - sc[k] / n[k]) for k in range(cubos) if n[k])


def cobertura(pares, total: int, objetivo: float = OBJETIVO) -> Optional[float]:
    """Mayor fracción de `total` que un umbral único sobre la confianza acepta con precisión ≥ objetivo (0 si ninguno la alcanza).
    Lo que no tiene confianza (error, sin probs) cuenta en `total` y nunca se acepta."""
    if not total:
        return None
    pts = sorted(((c, o) for c, o in pares if c is not None), key=lambda x: -x[0])
    mejor, ok = 0, 0
    for k, (c, o) in enumerate(pts, 1):
        ok += bool(o)
        if k < len(pts) and pts[k][0] == c:  # empate: el umbral deja pasar todo el grupo
            continue
        if ok / k >= objetivo - 1e-12:
            mejor = k
    return mejor / total


def _f1_macro(rs: List[dict]) -> Optional[float]:
    """Macro sobre las clases (esquema, opción) con soporte > 0; una fila sin predicción es fallo. En multi, cada opción es una clase."""
    tp, fp, soporte = {}, {}, {}
    for r in rs:
        e = r["esquema"]
        if r["tipo"] == "multi":
            act = _activas(r, r["opciones"])
            for o in r["opciones"]:
                real, pred = o in r["etiqueta"], act is not None and o in act
                soporte[(e, o)] = soporte.get((e, o), 0) + real
                tp[(e, o)] = tp.get((e, o), 0) + (real and pred)
                fp[(e, o)] = fp.get((e, o), 0) + (pred and not real)
        else:
            a = _mejor(r)[0] or ""
            soporte[(e, r["etiqueta"])] = soporte.get((e, r["etiqueta"]), 0) + 1
            if a == r["etiqueta"]:
                tp[(e, a)] = tp.get((e, a), 0) + 1
            elif a:
                fp[(e, a)] = fp.get((e, a), 0) + 1
    fs = [(2 * tp.get(k, 0) / (2 * tp.get(k, 0) + fp.get(k, 0) + (s - tp.get(k, 0)))) for k, s in soporte.items() if s]
    return sum(fs) / len(fs) if fs else None


def agregar(rs: List[dict], objetivo: float = OBJETIVO) -> dict:
    """Métricas de un grupo de filas medidas (un conjunto, un tipo o todo). Las fracciones van en [0, 1]; las latencias, en ms de cliente.
    exactitud: acierto de la mejor respuesta (en multi, subconjunto exacto) sobre todas las filas; un error cuenta como fallo."""
    n = len(rs)
    if not n:
        return {"n": 0}
    dec = [d for r in rs for d in decisiones(r)]
    total = sum(len(r["opciones"]) if r["tipo"] == "multi" else 1 for r in rs)
    cli = [r["cliente_ms"] for r in rs if r["cliente_ms"] is not None]
    m = {"n": n, "errores": sum(1 for r in rs if r["error"]) / n, "exactitud": sum(_acierto_fila(r) for r in rs) / n, "f1_macro": _f1_macro(rs),
         "ece": ece(dec), "cobertura": cobertura(dec, total, objetivo), "escalado": sum(1 for r in rs if not r["error"] and r["escalate"]) / n,
         "p50_ms": _pct(cli, 0.5), "p99_ms": _pct(cli, 0.99)}
    d = [abs(int(_mejor(r)[0]) - int(r["etiqueta"])) for r in rs if r["tipo"] == "score" and (_mejor(r)[0] or "").isdigit()]
    if d:
        m["mae"] = sum(d) / len(d)
    return m


# ---------------------------------------------------------------- robustez
TRANSFORMACIONES_CON_IDS = ("permutar", "renombrar")  # solo en choice y multi: los ids de noul (false/true) y de score (niveles) llevan significado


def cargar_variantes():
    """El módulo `chispa.variantes` (con `generar` y `estabilidad`). None si no existe."""
    try:
        mod = importlib.import_module(MODULO_VARIANTES)
    except ModuleNotFoundError as e:
        if e.name == MODULO_VARIANTES:
            return None
        raise
    for nombre in ("generar", "estabilidad"):
        if not callable(getattr(mod, nombre, None)):
            raise ErrorBateria(f"{MODULO_VARIANTES} no trae `{nombre}`")
    return mod


def _prediccion(r: dict):
    """Lo que decidió el servidor: la mejor respuesta, o en multi el conjunto de opciones activas (None = sin predicción)."""
    if r["tipo"] == "multi":
        act = _activas(r, r["opciones"])
        return None if act is None else frozenset(act)
    return _mejor(r)[0]


def _confianza(r: dict) -> Optional[float]:
    cs = [c for c, _ in decisiones(r) if c is not None]
    return sum(cs) / len(cs) if cs else None


def _caso(f: Fila) -> dict:
    """Fila → caso de `variantes.generar`: {texto, pregunta, kind, opciones[{id, description}], etiqueta}."""
    return {"texto": f.texto, "pregunta": f.q.question, "kind": f.tipo, "opciones": [{"id": o.id, "description": o.description} for o in f.q.options],
            "etiqueta": list(f.etiqueta) if f.tipo == "multi" else f.etiqueta}


def _fila_variante(f: Fila, v: dict) -> Fila:
    ops = tuple(Opcion(o["id"], o["description"]) for o in v["opciones"])
    return Fila(f.id, f.tipo, f.esquema, Pregunta(f.q.id, v["pregunta"], f.tipo, ops), v["texto"], f.etiqueta)


def _tipos_aplicables(tipo: str, tipos) -> tuple:
    return tuple(t for t in tipos if tipo in ("choice", "multi") or t not in TRANSFORMACIONES_CON_IDS)


def _prediccion_id(r: dict, inverso: Optional[dict] = None) -> str:
    """La decisión como un id comparable (en multi, los ids activos ordenados y unidos por `|`); `inverso` devuelve los ids de la variante a los originales."""
    p = _prediccion(r)
    if p is None:
        return ""
    if r["tipo"] == "multi":
        return "|".join(sorted((inverso or {}).get(o, o) for o in p))
    return p


def medir_robustez(cliente: Chispa, conjuntos: List[tuple], mod, concurrencia: int, maximo: int, tipos=None, semilla: int = 0) -> List[dict]:
    """conjuntos = [(nombre, grupo, [Fila], [resultado])]. Para hasta `maximo` filas por conjunto (a paso fijo) genera con `mod.generar` una variante por
    transformación aplicable, la manda y la compara con la decisión original vía `mod.estabilidad` (que traduce los ids con el mapa de la variante):
    {conjunto, grupo, tipo, transformacion, igual, dconf}. Una variante con error cuenta como decisión cambiada; una que no cambia nada, no cuenta."""
    tipos = tuple(tipos or mod.TIPOS)
    tareas, meta = [], []
    for nombre, grupo, filas, rs in conjuntos:
        paso = max(1, math.ceil(len(filas) / maximo)) if maximo else 1
        for f, r in list(zip(filas, rs))[::paso]:
            if r["error"]:
                continue
            caso = _caso(f)
            for v in mod.generar(caso, _tipos_aplicables(f.tipo, tipos), semilla):
                if (v["texto"], v["pregunta"], v["opciones"]) == (caso["texto"], caso["pregunta"], caso["opciones"]):
                    continue
                tareas.append((_fila_variante(f, v), None))
                meta.append((nombre, grupo, r, v))
    pares = []
    for (nombre, grupo, r0, v), rv in zip(meta, _correr(cliente, tareas, concurrencia)):
        c0, c1 = _confianza(r0), _confianza(rv)
        inverso = {nuevo: orig for orig, nuevo in v["mapa"].items()}
        # en multi la decisión ya viaja traducida a los ids originales: `estabilidad` no la vuelve a mapear (el id compuesto no está en el mapa)
        nuevo_id = "" if rv["error"] else (_prediccion_id(rv, inverso) if r0["tipo"] == "multi" else _prediccion_id(rv))
        e = mod.estabilidad({"id": _prediccion_id(r0), "confianza": c0 if c0 is not None else 0.0}, [v],
                            [{"id": nuevo_id, "confianza": c1 if c1 is not None else (c0 if c0 is not None else 0.0)}])
        pares.append({"conjunto": nombre, "grupo": grupo, "tipo": r0["tipo"], "transformacion": v["variante"], "igual": bool(e["estables"]),
                      "dconf": e["delta_media"] * (1 if c1 >= c0 else -1) if c0 is not None and c1 is not None else None})
    return pares


def _p95(xs):
    xs = sorted(xs)
    return xs[max(0, math.ceil(0.95 * len(xs)) - 1)]


def agregar_robustez(pares: List[dict], por_transformacion: bool = True) -> dict:
    """estabilidad = fracción de variantes cuya decisión no cambia; delta_conf (y su p95) = |confianza variante − confianza original|;
    `transformaciones` repite las tres por tipo de transformación."""
    if not pares:
        return {}
    d = [abs(p["dconf"]) for p in pares if p["dconf"] is not None]
    s = [p["dconf"] for p in pares if p["dconf"] is not None]
    m = {"estabilidad": sum(p["igual"] for p in pares) / len(pares), "delta_conf": sum(d) / len(d) if d else None,
         "delta_conf_p95": _p95(d) if d else None, "delta_conf_firmado": sum(s) / len(s) if s else None, "n_variantes": len(pares)}
    if por_transformacion:
        m["transformaciones"] = {t: agregar_robustez([p for p in pares if p["transformacion"] == t], False)
                                 for t in sorted({p["transformacion"] for p in pares})}
    return m


# ---------------------------------------------------------------- comparación con la línea base
def _umbral(u: dict, conjunto: Optional[str], metrica: str):
    pc = (u.get("por_conjunto") or {}).get(conjunto, {}) if conjunto else {}
    return pc[metrica] if metrica in pc else u.get(metrica, UMBRALES[metrica])


def comparar(actual: dict, base: dict, umbrales: dict, parcial: bool = False) -> dict:
    """{"ok", "fallos", "avisos"}. Falla si una métrica de la línea base empeora más que su umbral (o desaparece), o falta un conjunto.
    Un umbral `null` desactiva esa métrica. `parcial` (--solo u opcionales omitidos): solo se comparan los conjuntos medidos."""
    fallos, avisos = [], []
    secs = ("conjuntos",) if parcial else SECCIONES
    if parcial:
        avisos.append("comparación parcial: solo los conjuntos medidos (global, tipos y grupos no se comparan)")
    for sec in secs:
        a, b = actual.get(sec), base.get(sec)
        if b is None:
            continue
        if sec == "global":
            a, b = {"global": a}, {"global": b}
        for nombre, mb in (b or {}).items():
            ma = (a or {}).get(nombre)
            if parcial and ma is None:
                continue
            if ma is None:
                fallos.append({"seccion": sec, "nombre": nombre, "metrica": None, "detalle": f"{sec[:-1] if sec != 'global' else sec} {nombre!r} está en la línea base y no se midió"})
                continue
            if mb.get("n") != ma.get("n"):
                avisos.append(f"{sec}/{nombre}: n = {ma.get('n')} frente a {mb.get('n')} en la línea base (no es la misma muestra)")
            minimo = mb.get("estabilidad_min", base.get("estabilidad_min") if sec in ("global", "conjuntos") else None)
            if minimo is not None:
                ea = ma.get("estabilidad")
                if ea is None or ea < minimo - 1e-9:
                    fallos.append({"seccion": sec, "nombre": nombre, "metrica": "estabilidad_min", "base": minimo, "actual": ea, "umbral": minimo,
                                   "detalle": f"estabilidad {'sin medir' if ea is None else format(ea, '.4g')} por debajo del mínimo {minimo:.4g}"})
            for met in METRICAS:
                vb, va = mb.get(met), ma.get(met)
                u = _umbral(umbrales, nombre if sec == "conjuntos" else None, met)
                if vb is None or u is None:
                    continue
                if va is None:
                    fallos.append({"seccion": sec, "nombre": nombre, "metrica": met, "base": vb, "actual": None, "umbral": u, "detalle": f"{met} sin medir (base {vb:.4g})"})
                    continue
                rel = met in ("p50_ms", "p99_ms")
                peor = (vb - va) if met in MEJOR_ALTO else (va - vb)
                tope = max(vb, 0.0) * u if rel else u
                if peor > tope + 1e-9 and not (rel and peor <= HOLGURA_MS):  # ±1 ms de ruido no es una regresión
                    fallos.append({"seccion": sec, "nombre": nombre, "metrica": met, "base": vb, "actual": va, "umbral": u,
                                   "detalle": f"{met}: {vb:.4g} → {va:.4g} (empeora {peor:.4g}; tope {tope:.4g}{' = +' + format(100 * u, 'g') + ' %' if rel else ''})"})
    return {"ok": not fallos, "fallos": fallos, "avisos": avisos}


# ---------------------------------------------------------------- orquestación
def bateria(manifiesto: str, *, url: Optional[str] = None, modelo: Optional[str] = None, servidor: Optional[str] = None, tok: Optional[str] = None,
            config: Optional[str] = None, extra=(), linea_base: Optional[str] = None, umbrales: Optional[str] = None, robustez: bool = False,
            robustez_max: int = 200, solo: Optional[List[str]] = None, objetivo: Optional[float] = None, concurrencia: int = 4, timeout: float = 10.0,
            reintentos: int = 3, filas: bool = False, aviso=lambda m: None) -> dict:
    """Corre la batería y devuelve el reporte (JSON-able, con `informe` markdown y `ok`). Contra `url`, o arrancando `chispa-server` con `modelo`."""
    if bool(url) == bool(modelo):
        raise ErrorBateria("indica exactamente uno: --url (servidor ya en marcha) o --modelo (arranca chispa-server con ese .chispa)")
    man = leer_manifiesto(manifiesto)
    objetivo = objetivo if objetivo is not None else man.get("objetivo", OBJETIVO)
    um = _fusionar(_fusionar(UMBRALES, man.get("umbrales")), cargar_json(umbrales, "umbrales") if umbrales else None)
    _validar_umbrales(um)
    base = cargar_json(linea_base, "línea base") if linea_base else None
    if base is not None and base.get("version") != VERSION:
        raise ErrorBateria(f"línea base {linea_base}: versión {base.get('version')!r}, se espera {VERSION}")
    specs = man["conjuntos"]
    if solo:
        desconocidos = set(solo) - {c["nombre"] for c in specs}
        if desconocidos:
            raise ErrorBateria(f"--solo: conjuntos que no están en el manifiesto: {sorted(desconocidos)}")
        specs = [c for c in specs if c["nombre"] in solo]
    cargados, omitidos = [], {}
    for c in specs:
        ruta = resolver_ruta(c["ruta"], man["_dir"])
        if ruta is None:
            if c.get("opcional"):
                omitidos[c["nombre"]] = f"sin datos: {c['ruta']}"
                aviso(f"conjunto opcional {c['nombre']!r} omitido ({c['ruta']} no existe o tiene una variable sin definir)")
                continue
            raise ErrorBateria(f"conjunto {c['nombre']!r}: no encuentro {c['ruta']!r} (¿variable de entorno sin definir?)")
        fs = cargar_filas(ruta, c.get("formato", "auto"), c.get("tipo"), c.get("limite"), c.get("split", "test"))
        if not fs:
            raise ErrorBateria(f"conjunto {c['nombre']!r}: {ruta} no tiene filas")
        cargados.append((c, fs))
    if not cargados:
        raise ErrorBateria("ningún conjunto con datos")

    mod_var = None
    if robustez:
        mod_var = cargar_variantes()
        if mod_var is None:
            aviso(f"--robustez: no existe {MODULO_VARIANTES}; se mide sin estabilidad")

    with contextlib.ExitStack() as pila:
        u = url or pila.enter_context(servidor_local(modelo, servidor, tok, config, extra))
        cliente = Chispa(u, timeout=timeout, reintentos=reintentos)
        tareas = [(f, None) for _, fs in cargados for f in fs]
        res = _correr(cliente, tareas, concurrencia)
        por_conjunto, i = [], 0
        for c, fs in cargados:
            rs = res[i:i + len(fs)]
            i += len(fs)
            if all(r["error"] for r in rs):
                raise ErrorBateria(f"conjunto {c['nombre']!r}: todas las peticiones fallaron: {rs[0]['error']}")
            por_conjunto.append((c["nombre"], c.get("grupo", ""), fs, rs, c))
        pares = medir_robustez(cliente, [(n, g, fs, rs) for n, g, fs, rs, _ in por_conjunto], mod_var, concurrencia, robustez_max) if mod_var else []

    def con_robustez(m, ps):
        return dict(m, **agregar_robustez(ps))

    rep = {"version": VERSION, "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"), "manifiesto": man.get("nombre", os.path.basename(manifiesto)),
           "fuente": modelo or url, "objetivo": objetivo, "conjuntos": {}, "tipos": {}, "grupos": {}, "omitidos": omitidos}
    todas = [r for _, _, _, rs, _ in por_conjunto for r in rs]
    for nombre, grupo, fs, rs, c in por_conjunto:
        rep["conjuntos"][nombre] = con_robustez(dict(agregar(rs, objetivo), tipo=c.get("tipo", "mixto"), grupo=grupo), [p for p in pares if p["conjunto"] == nombre])
    for t in KINDS:
        sub = [r for r in todas if r["tipo"] == t]
        if sub:
            rep["tipos"][t] = con_robustez(agregar(sub, objetivo), [p for p in pares if p["tipo"] == t])
    for g in sorted({g for _, g, _, _, _ in por_conjunto if g}):
        rep["grupos"][g] = con_robustez(agregar([r for n, gg, _, rs, _ in por_conjunto if gg == g for r in rs], objetivo), [p for p in pares if p["grupo"] == g])
    rep["global"] = con_robustez(agregar(todas, objetivo), pares)
    if base is not None:
        rep["comparacion"] = comparar(rep, base, um, parcial=bool(solo) or bool(omitidos))
        rep["comparacion"]["linea_base"] = linea_base
    rep["ok"] = rep.get("comparacion", {"ok": True})["ok"]
    if filas:
        rep["filas"] = todas
    rep["informe"] = informe_md(rep)
    return rep


def linea_base(rep: dict) -> dict:
    """Lo que se guarda como línea base: el reporte sin filas, informe ni comparación (cualquier `.json` de --salida sirve igual)."""
    return {k: v for k, v in rep.items() if k not in ("filas", "informe", "comparacion", "ok")}


def json_reporte(rep: dict) -> dict:
    return {k: v for k, v in rep.items() if k != "informe"}


# ---------------------------------------------------------------- informe
def _fila_md(nombre: str, m: dict, rob: bool) -> str:
    c = [nombre, str(m["n"]), _f(m["exactitud"]), _f(m["f1_macro"]), _f(m["ece"]), _p(m["cobertura"]), _p(m["escalado"]), _p(m["errores"]),
         _f(m["p50_ms"], 1), _f(m["p99_ms"], 1)]
    if rob:
        c += [_p(m.get("estabilidad")), _f(m.get("delta_conf")), _f(m.get("delta_conf_p95"))]
    return "| " + " | ".join(c) + " |"


def informe_md(rep: dict) -> str:
    rob = "estabilidad" in rep["global"]
    cab = ["n", "exactitud", "F1 macro", "ECE", f"cobertura a {_f(rep['objetivo'], 2)}", "escalado", "errores", "p50 ms", "p99 ms"] + (["estabilidad", "Δ confianza", "Δ conf. p95"] if rob else [])
    L = [f"# Batería de regresión: {rep['manifiesto']}", "",
         f"Fuente: `{rep['fuente']}` · objetivo de precisión: {_f(rep['objetivo'], 2)} · {rep['fecha']}", ""]
    for titulo, sec in (("Global", None), ("Por tipo", "tipos"), ("Por grupo", "grupos"), ("Por conjunto", "conjuntos")):
        filas = [("global", rep["global"])] if sec is None else list((rep[sec] or {}).items())
        if not filas:
            continue
        L += [f"## {titulo}", "| " + ("" if sec is None else sec[:-1] if sec != "tipos" else "tipo") + " | " + " | ".join(cab) + " |", "|---|" + "---|" * len(cab)]
        L += [_fila_md(n, m, rob) for n, m in filas]
        L.append("")
    if rob:
        L += ["## Robustez por transformación", "| conjunto | transformación | variantes | estabilidad | Δ confianza | Δ conf. p95 |", "|---|---|---|---|---|---|"]
        for n, m in [("global", rep["global"])] + list(rep["conjuntos"].items()):
            L += [f"| {n} | {t} | {x['n_variantes']} | {_p(x['estabilidad'])} | {_f(x['delta_conf'])} | {_f(x['delta_conf_p95'])} |" for t, x in (m.get("transformaciones") or {}).items()]
        L.append("")
    score = {n: m for n, m in rep["conjuntos"].items() if "mae" in m}
    if score:
        L += ["MAE de score (niveles): " + ", ".join(f"{n} {_f(m['mae'])}" for n, m in score.items()), ""]
    if rep["omitidos"]:
        L += ["## Conjuntos omitidos"] + [f"- {n}: {w}" for n, w in rep["omitidos"].items()] + [""]
    L += ["Exactitud y F1 cuentan un error de petición o una fila sin respuesta como fallo. ECE con 10 cubos sobre la confianza de la mejor respuesta "
          "(en multi, una decisión por opción). Cobertura = fracción de decisiones que un umbral único de confianza acepta con precisión ≥ objetivo. "
          "p50/p99: cliente, extremo a extremo.", ""]
    cmp = rep.get("comparacion")
    if cmp:
        L += [f"## Línea base `{cmp.get('linea_base')}`: {'APRUEBA' if cmp['ok'] else 'FALLA'}", ""]
        if cmp["fallos"]:
            L += ["| sección | nombre | detalle |", "|---|---|---|"] + [f"| {x['seccion']} | {x['nombre']} | {x['detalle']} |" for x in cmp["fallos"]] + [""]
        L += [f"- aviso: {a}" for a in cmp["avisos"]]
    return "\n".join(L).rstrip() + "\n"
