"""chispa eval: métricas por tarea y globales de un par (filas, predicciones) unido por `id`.

Uso: python -m model.evaluacion.chispa_eval --datos f.jsonl --pred p.jsonl [--pred-b q.jsonl] [--salida x.json]
     python -m model.evaluacion.chispa_eval --jevbench ruta --pred p.jsonl
     python -m model.evaluacion.chispa_eval --arena data/ledger.jsonl
Formato de filas y predicciones: model/esquema.md.
"""
import argparse
import json
import sys
from collections import defaultdict

import numpy as np

from . import metricas as M

TOL_SUMA = 1e-6


class ErrorEval(ValueError):
    """Entrada inválida: el mensaje dice qué id o campo falla."""


def asignar_ids(filas, ruta):
    """El sondeo congelado (T0.2) es anterior al esquema y no trae `id`: si NINGUNA fila lo trae se
    le da `<fichero>:<split>:<n>` con n = nº de línea (0-based). Si solo algunas lo traen, error."""
    sin = [r for r in filas if "id" not in r]
    if not sin:
        return filas
    if len(sin) != len(filas):
        raise ErrorEval(f"{ruta}: solo algunas filas traen 'id'")
    stem = ruta.rsplit("/", 1)[-1].removesuffix(".jsonl")
    for n, r in enumerate(filas):
        r["id"] = f"{stem}:{r.get('split', 'test')}:{n}"
    return filas


def leer_jsonl(ruta):
    filas = []
    with open(ruta, encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            if linea.strip():
                try:
                    filas.append(json.loads(linea))
                except json.JSONDecodeError as e:
                    raise ErrorEval(f"{ruta}:{n}: JSON inválido ({e})") from None
    return filas


def indexar_filas(filas):
    out = {}
    for r in filas:
        for c in ("id", "tarea", "opciones", "etiqueta"):
            if c not in r:
                raise ErrorEval(f"fila {r.get('id', '?')}: falta el campo '{c}'")
        if r["id"] in out:
            raise ErrorEval(f"id repetido en las filas: {r['id']}")
        if r["etiqueta"] not in r["opciones"]:
            raise ErrorEval(f"fila {r['id']}: etiqueta '{r['etiqueta']}' fuera de opciones {r['opciones']}")
        out[r["id"]] = r
    return out


def indexar_preds(preds, filas):
    """Valida las predicciones contra las filas. Devuelve {id: pred}."""
    out = {}
    for p in preds:
        if "id" not in p or "probs" not in p:
            raise ErrorEval(f"predicción sin 'id' o 'probs': {str(p)[:80]}")
        i = p["id"]
        if i in out:
            raise ErrorEval(f"id repetido en las predicciones: {i}")
        out[i] = p
        if i not in filas:
            continue
        probs = p["probs"]
        permitidas = set(filas[i]["opciones"]) | {"escalate"}
        for k, v in probs.items():
            if k not in permitidas:
                raise ErrorEval(f"id {i}: opción desconocida '{k}' (válidas: {sorted(permitidas)})")
            if not isinstance(v, (int, float)) or v < 0 or v != v:
                raise ErrorEval(f"id {i}: probabilidad inválida para '{k}': {v!r}")
        if not probs or abs(sum(probs.values()) - 1.0) > TOL_SUMA:
            raise ErrorEval(f"id {i}: las probs suman {sum(probs.values()):.9f}, no 1 (±{TOL_SUMA})")
    faltan = [i for i in filas if i not in out]
    if faltan:
        raise ErrorEval(f"{len(faltan)} id sin predicción, p. ej. {faltan[:3]}")
    return out


def metricas_grupo(filas, preds):
    """filas: lista de filas; preds: dict id -> pred. Todas las métricas de un grupo."""
    y = [r["etiqueta"] for r in filas]
    tops = [M.top1(preds[r["id"]]["probs"], r.get("tipo"), r["opciones"]) for r in filas]
    p = [t[0] for t in tops]
    conf = np.array([t[1] for t in tops])
    ok = np.array([a == b for a, b in zip(y, p)])
    # Brier por fila sobre las clases de esa fila (opciones + claves de probs); las no dichas valen 0
    b = []
    for r in filas:
        pr = preds[r["id"]]["probs"]
        cs = list(dict.fromkeys(list(r["opciones"]) + list(pr)))
        b.append(sum((pr.get(c, 0.0) - (1.0 if c == r["etiqueta"] else 0.0)) ** 2 for c in cs))
    out = {
        "n": len(filas),
        "exactitud": M.exactitud(y, p),
        "macro_f1": M.macro_f1(y, p),
        "ece": M.ece(conf, ok),
        "brier": float(np.mean(b)),
        "cobertura_p95": M.cobertura_a_precision(conf, ok, 0.95),
        "cobertura_p99": M.cobertura_a_precision(conf, ok, 0.99),
    }
    esc = [r["etiqueta"] == "escalate" for r in filas]
    score = [preds[r["id"]]["probs"].get("escalate", 1.0 - c) for r, c in zip(filas, conf)]
    out["auroc_escalate"] = M.auroc(esc, score)
    lat = M.latencia([preds[r["id"]].get("ms") for r in filas])
    if lat:
        out["latencia"] = lat
    return out


def evaluar(filas, preds, preds_b=None):
    """Devuelve {"global": {...}, "por_tarea": {tarea: {...}}, "deriva": {...}?}."""
    idx = indexar_filas(filas)
    pa = indexar_preds(preds, idx)
    por = defaultdict(list)
    for r in idx.values():
        por[r["tarea"]].append(r)
    res = {
        "global": metricas_grupo(list(idx.values()), pa),
        "por_tarea": {t: metricas_grupo(rs, pa) for t, rs in sorted(por.items())},
    }
    extras = [i for i in pa if i not in idx]
    if extras:
        res["ids_sin_fila_ignorados"] = len(extras)
    if preds_b is not None:
        pb = indexar_preds(preds_b, idx)
        d = {"global": M.deriva([pa[i]["probs"] for i in idx], [pb[i]["probs"] for i in idx])}
        d["por_tarea"] = {t: M.deriva([pa[r["id"]]["probs"] for r in rs], [pb[r["id"]]["probs"] for r in rs])
                          for t, rs in sorted(por.items())}
        res["deriva"] = d
    return res


def _f(v):
    return "-" if v is None else f"{v:.4f}"


def tabla(res):
    cab = ["tarea", "n", "exact", "macroF1", "ECE", "Brier", "cob@.95", "cob@.99", "AUROC-esc", "p50ms", "p99ms"]
    lineas = ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    grupos = list(res["por_tarea"].items()) + [("GLOBAL", res["global"])]
    for t, m in grupos:
        lat = m.get("latencia") or {}
        lineas.append("| " + " | ".join([
            t, str(m["n"]), _f(m["exactitud"]), _f(m["macro_f1"]), _f(m["ece"]), _f(m["brier"]),
            _f(m["cobertura_p95"]["cobertura"]), _f(m["cobertura_p99"]["cobertura"]), _f(m["auroc_escalate"]),
            _f(lat.get("p50_ms")), _f(lat.get("p99_ms"))]) + " |")
    if "deriva" in res:
        lineas += ["", "Deriva A→B: " + ", ".join(f"{t}: cambio top-1 {_f(d['tasa_cambio_top1'])}, TV {_f(d['variacion_total_media'])}"
                                                  for t, d in [*res["deriva"]["por_tarea"].items(), ("GLOBAL", res["deriva"]["global"])])]
    return "\n".join(lineas)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="chispa eval", description=__doc__.split("\n")[0])
    ap.add_argument("--datos", help="filas JSONL (esquema.md)")
    ap.add_argument("--jevbench", help="clon de JevBench, su datasets/public o un .jsonl suelto (en lugar de --datos)")
    ap.add_argument("--pred", help="predicciones JSONL")
    ap.add_argument("--pred-b", help="segundas predicciones, para la deriva")
    ap.add_argument("--arena", help="ledger.jsonl de la Arena: calcula el ASR por detector")
    ap.add_argument("--salida", help="guarda el resultado en JSON")
    a = ap.parse_args(argv)
    try:
        res = {}
        if a.arena:
            from .adaptador_arena import asr_desde_ledger
            res["arena"] = asr_desde_ledger(a.arena)
        if a.datos or a.jevbench:
            if a.datos and a.jevbench:
                raise ErrorEval("usa --datos o --jevbench, no los dos")
            if not a.pred:
                raise ErrorEval("falta --pred")
            if a.jevbench:
                from .jevbench import cargar_jevbench
                filas = cargar_jevbench(a.jevbench)
            else:
                filas = asignar_ids(leer_jsonl(a.datos), a.datos)
            res.update(evaluar(filas, leer_jsonl(a.pred), leer_jsonl(a.pred_b) if a.pred_b else None))
        elif not a.arena:
            raise ErrorEval("falta --datos (o --jevbench) con --pred, o --arena")
        elif a.pred or a.pred_b:
            raise ErrorEval("--pred necesita --datos o --jevbench")
    except (ErrorEval, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if "global" in res:
        print(tabla(res))
    if "arena" in res:
        print(json.dumps(res["arena"], indent=2, ensure_ascii=False))
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
