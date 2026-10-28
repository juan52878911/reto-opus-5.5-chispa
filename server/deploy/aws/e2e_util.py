#!/usr/bin/env python3
"""Piezas de Python de e2e.sh (T4.5): preparar los datos, mandar el test a /v1/decide e informar.

  e2e_util.py preparar --datos DIR_CONVERTIDOS --salida DIR [--tareas massive,clinc150] [--recortar]
      por tarea: <t>/ejemplos.jsonl (train: texto, etiqueta), <t>/esquema.json (para `chispa train`), <t>/test.jsonl
      (filas completas para chispa_eval) y DIR/dev.jsonl (dev de todas, para calibrar y exportar L2).
  e2e_util.py cliente --url URL --test test.jsonl --salida pred.jsonl [--max N]
      una pregunta por petición, en serie; pred.jsonl = {id, probs, ms, layer, escalate, cliente_ms[, error]}.
  e2e_util.py informe --dir DIR --ref resultados.json [--tareas ...] [--modos cascada,forzado]
      lee DIR/<tarea>/<modo>/{pred.jsonl,eval.json}; escribe DIR/informe.md y DIR/informe.json.
Solo biblioteca estándar.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

H2_MARGEN = 0.01   # H2: macro-F1 de /v1/decide a ≤ 1 punto del de conjunta.py


def leer(ruta):
    return [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]


def escribir(ruta, filas):
    with open(ruta, "w", encoding="utf-8") as f:
        for r in filas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def recortar_opciones(filas):
    """Prueba en seco con fixtures: deja solo las opciones con algún ejemplo de train (el entrenador las exige)."""
    con = {r["etiqueta"] for r in filas if r["split"] == "train"}
    for r in filas:
        r["opciones"] = [o for o in r["opciones"] if o in con]
    return [r for r in filas if r["etiqueta"] in con]


def preparar(a):
    out = Path(a.salida)
    dev = []
    for t in a.tareas.split(","):
        filas = leer(Path(a.datos) / f"{t}.jsonl")
        if a.recortar:
            filas = recortar_opciones(filas)
        por = {s: [r for r in filas if r["split"] == s] for s in ("train", "dev", "test")}
        if not por["train"] or not por["test"]:
            sys.exit(f"{t}: sin train o sin test")
        q = por["train"][0]
        if q["tipo"] != "choice" or any(r["pregunta"] != q["pregunta"] or r["opciones"] != q["opciones"] for r in filas):
            sys.exit(f"{t}: la tarea debe ser una sola pregunta choice")
        d = out / t
        d.mkdir(parents=True, exist_ok=True)
        escribir(d / "ejemplos.jsonl", [{"texto": r["texto"], "etiqueta": r["etiqueta"]} for r in por["train"]])
        (d / "esquema.json").write_text(json.dumps(
            {"id": q["tarea"], "pregunta": q["pregunta"], "tipo": "choice",
             "opciones": {o: q["descripciones"].get(o, "") for o in q["opciones"]}}, ensure_ascii=False))
        escribir(d / "test.jsonl", por["test"])
        dev += por["dev"]
        print(f"{t}: train {len(por['train'])}, test {len(por['test'])}, {len(q['opciones'])} opciones")
    escribir(out / "dev.jsonl", dev)


def cliente(a):
    test = leer(a.test)[: a.max or None]
    pred, errores, desvio = [], 0, 0.0
    for r in test:
        cuerpo = {"state": r["texto"], "questions": [{
            "id": r["id"], "question": r["pregunta"], "kind": "choice", "nonce": r["id"],
            "options": [{"id": o, "description": r["descripciones"].get(o, "")} for o in r["opciones"]]}]}
        t0 = time.perf_counter()
        try:
            req = urllib.request.Request(a.url + "/v1/decide", json.dumps(cuerpo).encode(), {"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as x:
                res = json.loads(x.read())["results"][0]
            ms_cli = (time.perf_counter() - t0) * 1000
            probs = {o: float(res["probs"].get(o, 0.0)) for o in r["opciones"]}
            s = sum(probs.values())
            if s <= 0:
                raise ValueError("sin probabilidades")
            desvio = max(desvio, abs(s - 1))
            pred.append({"id": r["id"], "probs": {o: p / s for o, p in probs.items()}, "ms": res["ms"], "layer": res["layer"],
                         "escalate": bool(res["escalate"]), "cliente_ms": ms_cli})
        except (urllib.error.URLError, ValueError, KeyError, TimeoutError, OSError) as e:
            errores += 1
            pred.append({"id": r["id"], "probs": {"escalate": 1.0}, "ms": 0.0, "layer": "error", "escalate": True,
                         "cliente_ms": (time.perf_counter() - t0) * 1000, "error": f"{type(e).__name__}: {e}"})
    escribir(a.salida, pred)
    print(f"{len(pred)} preguntas, {errores} con error, desvío máximo de Σp respecto a 1: {desvio:.2g}")
    return 1 if errores else 0


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    i = int(k)
    return xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * (k - i)


def informe(a):
    ref = json.loads(Path(a.ref).read_text())
    res, md = {}, ["| tarea | modo | n | macro-F1 /v1/decide | macro-F1 conjunta.py (T2.2c) | Δ | H2 (Δ ≥ −0,01) |", "|---|---|---|---|---|---|---|"]
    capas = ["| tarea | modo | capa | fracción | p50 ms | p99 ms | p50 ms (cliente) | p99 ms (cliente) |", "|---|---|---|---|---|---|---|---|"]
    for t in a.tareas.split(","):
        for m in a.modos.split(","):
            d = Path(a.dir) / t / m
            if not (d / "pred.jsonl").exists() or not (d / "eval.json").exists():
                md.append(f"| {t} | {m} | – | sin resultados | | | |")
                continue
            pred, ev = leer(d / "pred.jsonl"), json.loads((d / "eval.json").read_text())
            f1 = ev["global"]["macro_f1"]
            r = ref.get(t, {}).get("global", {}).get("macro_f1")
            delta = None if r is None else f1 - r
            h2 = "–" if (delta is None or m != "forzado") else ("sí" if delta >= -H2_MARGEN else "NO")
            md.append(f"| {t} | {m} | {len(pred)} | {f1:.4f} | {'–' if r is None else f'{r:.4f}'} | "
                      f"{'–' if delta is None else f'{delta:+.4f}'} | {h2} |")
            por = {}
            for p in pred:
                por.setdefault(p["layer"], []).append(p)
            res[f"{t}/{m}"] = {"n": len(pred), "macro_f1": f1, "ref": r, "delta": delta, "h2": h2,
                               "errores": sum("error" in p for p in pred), "capas": {}}
            for nombre, ps in [("(total)", pred)] + sorted(por.items()):
                ms, cl = [p["ms"] for p in ps], [p["cliente_ms"] for p in ps]
                v = {"fraccion": len(ps) / len(pred), "p50": pct(ms, 50), "p99": pct(ms, 99), "p50_cliente": pct(cl, 50),
                     "p99_cliente": pct(cl, 99)}
                res[f"{t}/{m}"]["capas"][nombre] = v
                capas.append(f"| {t} | {m} | {nombre} | {v['fraccion']:.3f} | {v['p50']:.1f} | {v['p99']:.1f} | "
                             f"{v['p50_cliente']:.1f} | {v['p99_cliente']:.1f} |")
    texto = "# T4.5: /v1/decide de punta a punta\n\n" + "\n".join(md) + "\n\n" + "\n".join(capas) + "\n"
    (Path(a.dir) / "informe.md").write_text(texto)
    (Path(a.dir) / "informe.json").write_text(json.dumps(res, indent=1))
    print(texto)
    return 1 if any(v["errores"] for v in res.values()) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar")
    p.add_argument("--datos", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--tareas", default="massive,clinc150")
    p.add_argument("--recortar", action="store_true", help="solo las opciones con ejemplos de train (fixtures)")
    p = sub.add_parser("cliente")
    p.add_argument("--url", required=True)
    p.add_argument("--test", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--max", type=int, default=0)
    p = sub.add_parser("informe")
    p.add_argument("--dir", required=True)
    p.add_argument("--ref", required=True)
    p.add_argument("--tareas", default="massive,clinc150")
    p.add_argument("--modos", default="cascada,forzado")
    a = ap.parse_args()
    return {"preparar": lambda x: preparar(x) or 0, "cliente": cliente, "informe": informe}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
