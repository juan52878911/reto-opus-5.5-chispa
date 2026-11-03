"""Métricas offline en `dev` con la pregunta de esquema fijo, iguales para los dos modelos: exactitud frente al maestro,
log-loss, ECE (10 tramos), % que escala (Chispa) y p50/p99 de latencia medida en el cliente.

    python -m pong evaluar_dev --dev dev-px.jsonl --chispa URL | --laya URL [--n 1200] [--salida r.json]"""
from __future__ import annotations

import argparse
import json
import math
import time
from typing import Dict, List

from . import imitar as I
from .partida import _post


def pedir_chispa(url: str, texto: str):
    r = _post(url.rstrip("/") + "/v1/decide", I.peticion(texto), 30)
    ch = next(x for x in r["results"] if x["id"] == I.ID)
    return {k: float(v) for k, v in (ch.get("probs") or {}).items()}, bool(ch.get("escalate")), ch.get("layer")


def pedir_laya(url: str, texto: str):
    r = _post(url.rstrip("/") + "/decide", {"state": texto, "instructions": I.PREGUNTA, "criteria": dict(I.DESCRIPCIONES)}, 30)
    return {k: float(v) for k, v in (r.get("probs") or {}).items()}, False, r.get("capa", "laya")


def metricas(filas: List[dict]) -> Dict[str, float]:
    n = len(filas)
    acc = sum(f["pred"] == f["etiqueta"] for f in filas) / n
    ll = -sum(math.log(max(1e-6, f["probs"].get(f["etiqueta"], 0.0))) for f in filas) / n
    tramos = [[] for _ in range(10)]
    for f in filas:
        c = max(f["probs"].values()) if f["probs"] else 0.0
        tramos[min(9, int(c * 10))].append((c, f["pred"] == f["etiqueta"]))
    ece = sum(len(t) / n * abs(sum(c for c, _ in t) / len(t) - sum(o for _, o in t) / len(t)) for t in tramos if t)
    lat = sorted(f["ms"] for f in filas)
    return {"n": n, "exactitud": round(acc, 4), "log_loss": round(ll, 4), "ece": round(ece, 4),
            "escala_pct": round(100 * sum(f["escala"] for f in filas) / n, 1),
            "p50_ms": round(lat[n // 2], 2), "p99_ms": round(lat[min(n - 1, int(0.99 * n))], 2),
            "mayoritaria": round(max(sum(f["etiqueta"] == k for f in filas) for k in I.NOMBRES) / n, 4)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evaluar_dev", description=__doc__.splitlines()[0])
    ap.add_argument("--dev", required=True)
    ap.add_argument("--chispa")
    ap.add_argument("--laya")
    ap.add_argument("--n", type=int, default=1200)
    ap.add_argument("--salida")
    a = ap.parse_args(argv)
    pedir, url = (pedir_chispa, a.chispa) if a.chispa else (pedir_laya, a.laya)
    filas = []
    with open(a.dev, encoding="utf-8") as f:
        for linea in list(f)[:a.n]:
            x = json.loads(linea)
            t0 = time.perf_counter()
            probs, escala, capa = pedir(url, x["texto"])
            ms = (time.perf_counter() - t0) * 1000
            pred = max(I.NOMBRES, key=lambda k: probs.get(k, -1.0)) if probs else "quieta"
            filas.append({"etiqueta": x["etiqueta"], "pred": pred, "probs": probs, "escala": escala, "capa": capa, "ms": ms})
    m = metricas(filas)
    from collections import Counter
    m["capas"] = dict(Counter(f["capa"] for f in filas))
    print(json.dumps(m, ensure_ascii=False))
    if a.salida:
        with open(a.salida, "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
