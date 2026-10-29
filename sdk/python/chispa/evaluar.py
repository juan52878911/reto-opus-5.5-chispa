"""`chispa evaluar`: mide un servidor `/v1/decide` con una muestra etiquetada (texto, etiqueta). Solo biblioteca estándar.

`/v1/decide` recibe un único `state` por petición (las preguntas de una petición comparten texto), así que cada fila es una
petición; `concurrencia` las reparte en hilos. Las métricas son las de `pilotos/metrica.md`."""
from __future__ import annotations

import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from .cliente import Chispa, ChispaError, ErrorSolicitud
from .datos import cargar_ejemplos, cargar_esquema, validar_multi
from .tipos import Pregunta

MAX_ESTADO_BYTES = 256 << 10  # límite por defecto de /v1/decide (max_estado)
_SIN = "(sin respuesta)"
_FALSE = {"false", "0", "no", "falso"}
_TRUE = {"true", "1", "si", "sí", "yes", "verdadero"}
# errores de una petición concreta (no del esquema): no abortan la medición
_ERRORES_DE_FILA = {"state_too_long", "request_too_large"}


def _etiqueta(q: Pregunta, e: str) -> str:
    e = e.strip()
    if q.kind == "noul":
        return "true" if e.lower() in _TRUE else "false" if e.lower() in _FALSE else e
    return e


def _pct(v: List[float], p: float) -> Optional[float]:
    """Percentil sin interpolar, como en pilotos/metrica.md: v[int(p·(n−1))] de los valores ordenados."""
    v = sorted(v)
    return v[int(p * (len(v) - 1))] if v else None


def _div(a: float, b: float) -> Optional[float]:
    return a / b if b else None


def medir(q: Pregunta, ejemplos, cliente: Chispa, concurrencia: int = 4, reloj=time.perf_counter) -> List[dict]:
    """Una fila por ejemplo, en orden: {fila, etiqueta, answer, probs, layer, escalate, ms, cliente_ms, error, error_codigo}.
    La primera petición va sola: un error del esquema (400 que no es de la fila) para todo con ese error."""
    ids = {o.id for o in q.options}
    multi = q.kind == "multi"
    if multi:
        validar_multi(ejemplos, q)
    else:
        malas = Counter(e for _, e in ejemplos if e not in ids)
        if malas:
            raise ChispaError(f"etiquetas que no son opciones del esquema: {dict(malas.most_common(5))}")

    def una(i: int) -> dict:
        texto, et = ejemplos[i]
        f = {"fila": i + 1, "etiqueta": list(et) if multi else et, "answer": "", "probs": {}, "layer": "", "escalate": False, "ms": None,
             "cliente_ms": None, "error": "", "error_codigo": ""}
        if multi:
            f["answers"] = None
        if len(texto.encode("utf-8")) > MAX_ESTADO_BYTES:
            f.update(error="texto mayor que 262144 bytes (max_estado)", error_codigo="state_too_long")
            return f
        t0 = reloj()
        try:
            r = cliente.decidir(texto, [q])[0]
        except ErrorSolicitud as e:
            f.update(error=str(e), error_codigo=e.codigo or f"http_{e.status}")
            if e.codigo not in _ERRORES_DE_FILA and i == 0:
                raise
            return f
        except ChispaError as e:
            f.update(error=str(e), error_codigo="transporte")
            return f
        f.update(answer=r.answer, probs=r.probs, layer=r.layer, escalate=r.escalate, ms=r.ms,
                 cliente_ms=(reloj() - t0) * 1000)
        if multi:
            f["answers"] = r.answers
        return f

    filas = [una(0)]
    if len(ejemplos) > 1:
        with ThreadPoolExecutor(max_workers=max(1, concurrencia)) as ex:
            filas += list(ex.map(una, range(1, len(ejemplos))))
    return filas


def _mejor(f: dict):
    """(respuesta, confianza) de la mejor opción de la fila; la respuesta de la cascada, o el argmax de probs si escaló sin ella."""
    if f["error"] or not f["probs"]:
        return (f["answer"] or None), None
    a = f["answer"] or max(f["probs"], key=f["probs"].get)
    return a, f["probs"].get(a)


def _f1_macro(pares, clases) -> Optional[float]:
    """pares = [(real, predicha)]; macro sobre `clases` con soporte > 0 en lo real (predicha vacía = fallo, sin clase propia)."""
    soporte = Counter(r for r, _ in pares)
    fs = []
    for c in clases:
        if not soporte[c]:
            continue
        tp = sum(1 for r, p in pares if r == c and p == c)
        fp = sum(1 for r, p in pares if r != c and p == c)
        fn = soporte[c] - tp
        fs.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(fs) / len(fs) if fs else None


def barrido(filas: List[dict], objetivo: float) -> dict:
    """Barre un umbral único sobre la confianza (prob. de la mejor opción) de todas las filas con respuesta, ignorando `escalate`.
    Cobertura = aceptadas / total de la muestra. Devuelve el mejor umbral con precisión ≥ objetivo y la curva en pasos de ≈5 % de cobertura."""
    n = len(filas)
    pts = sorted(((c, a == f["etiqueta"]) for f in filas for a, c in [_mejor(f)] if a and c is not None), key=lambda x: -x[0])
    curva, mejor, ok = [], None, 0
    paso, prox = max(1, round(n * 0.05)), 0
    for k, (c, bien) in enumerate(pts, 1):
        ok += bien
        if k < len(pts) and pts[k][0] == c:  # empate: el umbral deja pasar todo el grupo
            continue
        p = ok / k
        if p >= objetivo:
            mejor = {"umbral": c, "cobertura": k / n, "precision": p, "aceptadas": k}
        if k >= prox:
            curva.append({"umbral": c, "cobertura": k / n, "precision": p})
            prox = k + paso
    return {"objetivo": objetivo, "alcanzable": mejor is not None, "mejor": mejor, "curva": curva}


def metricas(q: Pregunta, filas: List[dict], objetivo: float = 0.95) -> dict:
    if q.kind == "multi":
        return metricas_multi(q, filas, objetivo)
    n = len(filas)
    clases = [o.id for o in q.options]
    err = [f for f in filas if f["error"]]
    mej = [(f["etiqueta"], (_mejor(f)[0] or "")) for f in filas]
    ok = sum(1 for r, p in mej if r == p)
    acept = [f for f in filas if not f["error"] and not f["escalate"] and f["answer"]]
    ac_ok = sum(1 for f in acept if f["answer"] == f["etiqueta"])
    escala = sum(1 for f in filas if not f["error"] and f["escalate"])
    ids_ac = {f["fila"] for f in acept}
    esc_fallo = [(f["etiqueta"], f["answer"] if f["fila"] in ids_ac else "") for f in filas]
    conf = {r: Counter() for r in clases}
    for r, p in mej:
        conf[r][p or _SIN] += 1
    cols = clases + [_SIN]
    por_capa = {}
    for f in filas:
        if f["error"]:
            continue
        d = por_capa.setdefault(f["layer"] or _SIN, {"n": 0, "correctas": 0})
        d["n"] += 1
        d["correctas"] += f["answer"] == f["etiqueta"] and bool(f["answer"])
    for d in por_capa.values():
        d["fraccion"], d["precision"] = d["n"] / n, _div(d["correctas"], d["n"])
    cli = [f["cliente_ms"] for f in filas if f["cliente_ms"] is not None]
    srv = [f["ms"] for f in filas if f["ms"] is not None]
    top = Counter((r, p) for r, p in mej if r != p)
    confusiones = [{"real": r, "predicha": p or _SIN, "n": c, "filas": [f["fila"] for f in filas if f["etiqueta"] == r and (_mejor(f)[0] or "") == p][:5]}
                   for (r, p), c in top.most_common(3)]
    m = {
        "pregunta": q.id, "tipo": q.kind, "n": n, "errores": len(err),
        "errores_por_codigo": dict(Counter(f["error_codigo"] for f in err)),
        "por_opcion": {c: sum(1 for f in filas if f["etiqueta"] == c) for c in clases},
        "exactitud": _div(ok, n), "f1_macro_mejor": _f1_macro(mej, clases), "f1_macro_escala_fallo": _f1_macro(esc_fallo, clases),
        "tasa_escalado": _div(escala, n), "cobertura": _div(len(acept), n), "precision_aceptadas": _div(ac_ok, len(acept)),
        "por_capa": por_capa,
        "latencia_cliente_ms": {"p50": _pct(cli, 0.5), "p99": _pct(cli, 0.99)},
        "latencia_servidor_ms": {"p50": _pct(srv, 0.5), "p99": _pct(srv, 0.99)},
        "matriz_confusion": {"clases": cols, "filas": {r: [conf[r][c] for c in cols] for r in clases}},
        "confusiones_frecuentes": confusiones,
        "barrido": barrido(filas, objetivo),
        "coste_por_1000": "sin medir",
    }
    if q.kind == "score":
        def mae(fs):
            d = [abs(int(f["answer"]) - int(f["etiqueta"])) for f in fs if f["answer"].isdigit() and f["etiqueta"].isdigit()]
            return {"mae": _div(sum(d), len(d)), "n": len(d)}
        m["score"] = {"mae_mejor": mae([dict(f, answer=_mejor(f)[0] or "") for f in filas if not f["error"]]), "mae_aceptadas": mae(acept)}
    return m


# ---- multi (multietiqueta) ----
def _activas(f: dict, ids) -> Optional[set]:
    """Opciones activas según el servidor (`answers`); si faltan, las de p ≥ 0,5. None = sin predicción (error de la fila, o escaló con probs vacías)."""
    if f["error"]:
        return None
    if f.get("answers") is not None and (f["probs"] or not f["escalate"]):
        return set(f["answers"])
    if not f["probs"]:
        return None
    return {o for o in ids if f["probs"].get(o, 0.0) >= 0.5}


def _prf(tp: int, fp: int, fn: int) -> dict:
    return {"precision": _div(tp, tp + fp), "recall": _div(tp, tp + fn), "f1": 2 * tp / (2 * tp + fp + fn) if tp else (0.0 if fp + fn else None),
            "tp": tp, "fp": fp, "fn": fn}


def metricas_multi(q: Pregunta, filas: List[dict], objetivo: float = 0.95) -> dict:
    """Métricas multietiqueta. `etiqueta` de cada fila es la lista de opciones activas reales.
    - exactitud (subconjunto): el conjunto predicho es igual al real; sobre todas las filas, una fila sin predicción cuenta como fallo.
    - Hamming, F1 micro/macro y por etiqueta: solo sobre las filas con predicción (`n_con_prediccion`); macro = media de las etiquetas con soporte > 0.
    - barrido por etiqueta: umbral único sobre la confianza de esa decisión (max(p, 1−p)); cobertura = decisiones aceptadas / n."""
    n = len(filas)
    ids = [o.id for o in q.options]
    err = [f for f in filas if f["error"]]
    pred = {f["fila"]: _activas(f, ids) for f in filas}
    con = [f for f in filas if pred[f["fila"]] is not None]
    exactas = {f["fila"] for f in con if pred[f["fila"]] == set(f["etiqueta"])}
    por = {}
    for o in ids:
        tp = sum(1 for f in con if o in pred[f["fila"]] and o in f["etiqueta"])
        fp = sum(1 for f in con if o in pred[f["fila"]] and o not in f["etiqueta"])
        fn = sum(1 for f in con if o not in pred[f["fila"]] and o in f["etiqueta"])
        d = _prf(tp, fp, fn)
        d["soporte"] = sum(1 for f in filas if o in f["etiqueta"])
        d["predichas"] = tp + fp
        # decisión por etiqueta como una fila de `barrido`: real/predicha "1"/"0" y confianza max(p, 1−p)
        sub = []
        for f in filas:
            g = {"etiqueta": "1" if o in f["etiqueta"] else "0", "answer": "", "probs": {}, "error": f["error"], "escalate": False}
            if pred[f["fila"]] is not None and o in f["probs"]:
                p = f["probs"][o]
                g["answer"] = "1" if o in pred[f["fila"]] else "0"
                g["probs"] = {g["answer"]: max(p, 1 - p)}
            sub.append(g)
        d["barrido"] = barrido(sub, objetivo)
        por[o] = d
    tp, fp, fn = (sum(d[k] for d in por.values()) for k in ("tp", "fp", "fn"))
    con_soporte = [d["f1"] for d in por.values() if d["soporte"] and d["f1"] is not None]
    errores_hamming = sum(len(pred[f["fila"]] ^ set(f["etiqueta"])) for f in con)
    acept = [f for f in filas if not f["error"] and not f["escalate"]]
    ac_ok = sum(1 for f in acept if f["fila"] in exactas)
    por_capa = {}
    for f in filas:
        if f["error"]:
            continue
        d = por_capa.setdefault(f["layer"] or _SIN, {"n": 0, "correctas": 0})
        d["n"] += 1
        d["correctas"] += f["fila"] in exactas
    for d in por_capa.values():
        d["fraccion"], d["precision"] = d["n"] / n, _div(d["correctas"], d["n"])
    cli = [f["cliente_ms"] for f in filas if f["cliente_ms"] is not None]
    srv = [f["ms"] for f in filas if f["ms"] is not None]
    return {
        "pregunta": q.id, "tipo": q.kind, "n": n, "errores": len(err),
        "errores_por_codigo": dict(Counter(f["error_codigo"] for f in err)),
        "n_con_prediccion": len(con), "n_sin_etiquetas": sum(1 for f in filas if not f["etiqueta"]),
        "por_opcion": {o: por[o]["soporte"] for o in ids},
        "exactitud_subconjunto": _div(len(exactas), n),
        "hamming": _div(errores_hamming, len(con) * len(ids)),
        "f1_micro": _prf(tp, fp, fn)["f1"], "precision_micro": _prf(tp, fp, fn)["precision"], "recall_micro": _prf(tp, fp, fn)["recall"],
        "f1_macro": sum(con_soporte) / len(con_soporte) if con_soporte else None,
        "por_etiqueta": por,
        "tasa_escalado": _div(sum(1 for f in filas if not f["error"] and f["escalate"]), n),
        "cobertura": _div(len(acept), n), "precision_aceptadas": _div(ac_ok, len(acept)),
        "por_capa": por_capa,
        "latencia_cliente_ms": {"p50": _pct(cli, 0.5), "p99": _pct(cli, 0.99)},
        "latencia_servidor_ms": {"p50": _pct(srv, 0.5), "p99": _pct(srv, 0.99)},
        "objetivo": objetivo,
        "coste_por_1000": "sin medir",
    }


def informe_multi_md(m: dict, fuente: str = "", url: str = "") -> str:
    L = [f"# Evaluación de Chispa: {m['pregunta']} ({m['tipo']})", ""]
    if fuente or url:
        L += [f"Muestra: `{fuente}` · servidor: `{url}` · n = {m['n']} · errores de petición: {m['errores']}"
              + (f" {m['errores_por_codigo']}" if m["errores"] else "") + f" · con predicción: {m['n_con_prediccion']}", ""]
    L += ["## Resultados", "| Exactitud por subconjunto | F1 micro | F1 macro | Hamming | Escalado | Cobertura aceptada | Precisión de lo aceptado | p99 ms (cliente) |",
          "|---|---|---|---|---|---|---|---|",
          f"| {_f(m['exactitud_subconjunto'])} | {_f(m['f1_micro'])} | {_f(m['f1_macro'])} | {_f(m['hamming'])} | {_p(m['tasa_escalado'])} | "
          f"{_p(m['cobertura'])} | {_f(m['precision_aceptadas'])} | {_f(m['latencia_cliente_ms']['p99'], 1)} |", "",
          "Exactitud por subconjunto: sobre todas las filas (sin predicción = fallo). Hamming y F1: solo filas con predicción; Hamming = fracción de decisiones por opción erradas.", "",
          "## Por etiqueta", f"| Etiqueta | Soporte | Precisión | Recall | F1 | Cobertura a {_f(m['objetivo'], 2)} | Umbral de confianza |", "|---|---|---|---|---|---|---|"]
    for o, d in m["por_etiqueta"].items():
        mj = d["barrido"]["mejor"]
        L.append(f"| {o} | {d['soporte']} | {_f(d['precision'])} | {_f(d['recall'])} | {_f(d['f1'])} | "
                 f"{_p(mj['cobertura']) if mj else 'no alcanzable'} | {_f(mj['umbral'], 3) if mj else 'sin medir'} |")
    L += ["", "La cobertura por etiqueta es la fracción de la muestra cuya decisión sobre esa etiqueta (activa o no) se acepta con un umbral único sobre max(p, 1−p) y precisión ≥ objetivo."]
    flojas = [o for o, d in m["por_etiqueta"].items() if d["soporte"] < 30]
    if flojas:
        L += ["", f"Con menos de 30 positivos su F1 no es confiable: {', '.join(flojas)}."]
    L += ["", "## Latencia", "| | p50 ms | p99 ms |", "|---|---|---|",
          f"| cliente (extremo a extremo) | {_f(m['latencia_cliente_ms']['p50'], 2)} | {_f(m['latencia_cliente_ms']['p99'], 2)} |",
          f"| servidor (cascada) | {_f(m['latencia_servidor_ms']['p50'], 2)} | {_f(m['latencia_servidor_ms']['p99'], 2)} |", "",
          "## Por capa (exactitud por subconjunto)", "| Capa | Filas | Fracción | Exactitud |", "|---|---|---|---|"]
    L += [f"| {k} | {d['n']} | {_p(d['fraccion'])} | {_f(d['precision'])} |" for k, d in sorted(m["por_capa"].items())]
    L += ["", "Coste por 1.000 decisiones: sin medir aquí (ver `pilotos/metrica.md`, paso 5)."]
    return "\n".join(L) + "\n"


def _f(x, d=3) -> str:
    return "sin medir" if x is None else f"{x:.{d}f}".replace(".", ",")


def _p(x) -> str:
    return "sin medir" if x is None else f"{100 * x:.1f} %".replace(".", ",")


def informe_md(m: dict, fuente: str = "", url: str = "") -> str:
    if m["tipo"] == "multi":
        return informe_multi_md(m, fuente, url)
    b = m["barrido"]
    mj = b["mejor"]
    L = [f"# Evaluación de Chispa: {m['pregunta']} ({m['tipo']})", ""]
    if fuente or url:
        L += [f"Muestra: `{fuente}` · servidor: `{url}` · n = {m['n']} · errores de petición: {m['errores']}"
              + (f" {m['errores_por_codigo']}" if m["errores"] else ""), ""]
    L += ["## Resultados", "| Exactitud | F1 macro (escala = fallo) | F1 macro (mejor respuesta) | Escalado | Cobertura aceptada | Precisión de lo aceptado | "
          f"Cobertura a {_f(b['objetivo'], 2)} | p99 ms (cliente) | Coste / 1.000 |", "|---|---|---|---|---|---|---|---|---|",
          f"| {_f(m['exactitud'])} | {_f(m['f1_macro_escala_fallo'])} | {_f(m['f1_macro_mejor'])} | {_p(m['tasa_escalado'])} | {_p(m['cobertura'])} | "
          f"{_f(m['precision_aceptadas'])} | {_p(mj['cobertura']) if mj else 'no alcanzable'} | {_f(m['latencia_cliente_ms']['p99'], 1)} | {m['coste_por_1000']} |", ""]
    if "score" in m:
        s = m["score"]
        L += [f"MAE (niveles): {_f(s['mae_mejor']['mae'])} con la mejor respuesta (n = {s['mae_mejor']['n']}); "
              f"{_f(s['mae_aceptadas']['mae'])} solo en lo aceptado (n = {s['mae_aceptadas']['n']}).", ""]
    if mj:
        L += [f"Para precisión ≥ {_f(b['objetivo'], 2)}: umbral de confianza ≥ {_f(mj['umbral'], 3)} → cobertura {_p(mj['cobertura'])} "
              f"({mj['aceptadas']} de {m['n']}), precisión {_f(mj['precision'])}. El umbral se fija en una parte de la muestra y se mide en otra.", ""]
    else:
        L += [f"Ningún umbral llega a precisión {_f(b['objetivo'], 2)}.", ""]
    L += ["## Latencia", "| | p50 ms | p99 ms |", "|---|---|---|",
          f"| cliente (extremo a extremo) | {_f(m['latencia_cliente_ms']['p50'], 2)} | {_f(m['latencia_cliente_ms']['p99'], 2)} |",
          f"| servidor (cascada) | {_f(m['latencia_servidor_ms']['p50'], 2)} | {_f(m['latencia_servidor_ms']['p99'], 2)} |", "",
          "## Por capa", "| Capa | Filas | Fracción | Precisión |", "|---|---|---|---|"]
    L += [f"| {k} | {d['n']} | {_p(d['fraccion'])} | {_f(d['precision'])} |" for k, d in sorted(m["por_capa"].items())]
    L += ["", "## Mensajes por opción", "| Opción | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in m["por_opcion"].items()]
    flojas = [k for k, v in m["por_opcion"].items() if v < 30]
    if flojas:
        L += ["", f"Con menos de 30 mensajes su F1 no es confiable: {', '.join(flojas)}."]
    mc = m["matriz_confusion"]
    L += ["", "## Matriz de confusión (filas = real, columnas = mejor respuesta)", "| real \\ predicha | " + " | ".join(mc["clases"]) + " |",
          "|---|" + "---|" * len(mc["clases"])]
    L += [f"| {r} | " + " | ".join(map(str, v)) + " |" for r, v in mc["filas"].items()]
    if m["confusiones_frecuentes"]:
        L += ["", "## Confusiones más frecuentes"] + [f"- {c['real']} → {c['predicha']}: {c['n']} (filas {', '.join(map(str, c['filas']))})"
                                                       for c in m["confusiones_frecuentes"]]
    L += ["", f"## Cobertura frente a precisión (umbral único sobre la confianza)", "| Umbral | Cobertura | Precisión |", "|---|---|---|"]
    L += [f"| {_f(c['umbral'], 3)} | {_p(c['cobertura'])} | {_f(c['precision'])} |" for c in b["curva"]]
    L += ["", "Coste por 1.000 decisiones: sin medir aquí (ver `pilotos/metrica.md`, paso 5)."]
    return "\n".join(L) + "\n"


def evaluar(url: str, esquema: str, datos: str, pregunta: Optional[str] = None, objetivo: float = 0.95, concurrencia: int = 4,
            timeout: float = 10.0, reintentos: int = 3) -> dict:
    """Lee esquema y muestra, mide contra `url` y devuelve {"metricas", "filas", "informe"}."""
    q, _ = cargar_esquema(esquema, pregunta)
    if q.kind == "multi":  # etiqueta = opciones separadas por «|» (celda vacía = ninguna), como en chispa train
        ej = cargar_ejemplos(datos, q.id, multi=True)
    else:
        ej = [(t, _etiqueta(q, e)) for t, e in cargar_ejemplos(datos, q.id)]
    filas = medir(q, ej, Chispa(url, timeout=timeout, reintentos=reintentos), concurrencia)
    if all(f["error"] for f in filas):
        raise ChispaError(f"todas las peticiones fallaron: {filas[0]['error']}")
    m = metricas(q, filas, objetivo)
    return {"metricas": m, "filas": filas, "informe": informe_md(m, str(datos), url)}
