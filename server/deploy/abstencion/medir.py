#!/usr/bin/env python3
"""T4.6: abstención de la cascada con tráfico no adversarial. Solo biblioteca estándar.

  medir.py --pred tarea=pred.jsonl --verdad tarea=test.jsonl --salida DIR [--max-abstencion 0.20]   (--pred y --verdad, una vez por tarea)

pred.jsonl es el de e2e_util.py cliente en modo cascada: {id, probs, layer, escalate[, error]}; test.jsonl, el del test limpio
(id, etiqueta). Las filas con error del cliente (layer «error») cuentan como escaladas y se avisan aparte; no entran en la curva.
Por tarea (DIR/<tarea>.md, <tarea>.svg y DIR/abstencion.json, DIR/informe.md):
  · escala: fracción que escala en la cascada (τ de CALIB);
  · precisión y macro-F1 SOLO sobre lo contestado; macro-F1 contando lo escalado como fallo; macro-F1 de la mejor respuesta de todas;
  · curva τ → (abstención, precisión): una sola τ sobre la probabilidad máxima devuelta; tabla cada 5 % de abstención y SVG.
H1: escala ≤ 30 % y precisión contestada ≥ 0,95 (en las tareas con macro-F1 de la mejor respuesta ≥ 0,85).
H2: la τ con abstención ≤ --max-abstencion y la precisión que cuesta.
"""
import argparse
import json
import math
import sys
from pathlib import Path

PASO = 5            # % de abstención entre filas de la tabla
H1_ESCALA = 0.30
H1_PRECISION = 0.95
H1_F1 = 0.85


def leer(ruta):
    return [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]


def mejor(probs):
    """(etiqueta, probabilidad) máxima; desempata por el nombre para ser determinista."""
    return max(sorted(probs.items()), key=lambda kv: kv[1])


def macro_f1(pares, clases):
    """pares: (verdad, predicción o None). None nunca acierta (cuenta como falso negativo de su clase). Media sobre `clases`."""
    fs = []
    for c in clases:
        tp = sum(1 for v, p in pares if v == c and p == c)
        fp = sum(1 for v, p in pares if v != c and p == c)
        fn = sum(1 for v, p in pares if v == c and p != c)
        fs.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(fs) / len(fs) if fs else 0.0


def curva(pares):
    """pares: (confianza, acierto) -> [(abstención, precisión, τ)] por abstención decreciente; un punto por τ (se acepta todo el empate)."""
    n = len(pares)
    pares = sorted(pares, key=lambda c: -c[0])
    puntos, ok = [], 0
    for i, (conf, acierto) in enumerate(pares, 1):
        ok += acierto
        if i == n or pares[i][0] != conf:
            puntos.append(((n - i) / n, ok / i, conf))
    return puntos


def tabla(puntos):
    """Una fila por cada 5 % de abstención a: el punto con la mayor abstención ≤ a, (a, abstención real, precisión, τ).
    Si los empates no dejan ningún punto con abstención ≤ a, la fila se omite."""
    filas = []
    for a in range(0, 100, PASO):
        cand = [p for p in puntos if p[0] <= a / 100 + 1e-9]
        if not cand:
            continue
        abst, prec, tau = max(cand, key=lambda p: p[0])
        filas.append((a, abst, prec, tau))
    return filas


def medir(preds, verdad):
    """-> dict de métricas para una tarea. preds: filas de pred.jsonl; verdad: {id: etiqueta}."""
    filas = [p for p in preds if p["id"] in verdad]
    if not filas:
        raise SystemExit("ninguna predicción coincide con la verdad (¿ids distintos?)")
    n = len(filas)
    malo = [p.get("layer") == "error" or "error" in p for p in filas]
    esc = [m or bool(p.get("escalate")) for p, m in zip(filas, malo)]
    mj = [None if m else mejor(p["probs"]) for p, m in zip(filas, malo)]   # (etiqueta, confianza) o None si hubo error
    ver = [verdad[p["id"]] for p in filas]
    par_cont = [(v, m[0]) for v, m, e in zip(ver, mj, esc) if not e]
    par_todas = [(v, None if e else m[0]) for v, m, e in zip(ver, mj, esc)]
    par_mejor = [(v, m[0]) for v, m in zip(ver, mj) if m]
    usables = [(m[1], m[0] == v) for v, m in zip(ver, mj) if m]
    puntos = curva(usables) if usables else []
    cl = lambda pares: sorted({v for v, _ in pares} | {p for _, p in pares if p})
    t = {
        "n": n, "errores_cliente": sum(malo), "escalan": sum(esc), "escala": sum(esc) / n,
        "contestadas": len(par_cont),
        "precision_contestada": sum(v == p for v, p in par_cont) / len(par_cont) if par_cont else None,
        "macro_f1_contestada": macro_f1(par_cont, cl(par_cont)) if par_cont else None,
        "macro_f1_escala_fallo": macro_f1(par_todas, cl(par_todas)),
        "macro_f1_mejor_respuesta": macro_f1(par_mejor, cl(par_mejor)) if par_mejor else None,
        "capas": {},
        "puntos": puntos,
        "tabla": tabla(puntos),
    }
    for p in filas:
        t["capas"][p.get("layer", "?")] = t["capas"].get(p.get("layer", "?"), 0) + 1
    return t


def veredicto_h1(t):
    """None si la tarea no entra en H1 (macro-F1 de la mejor respuesta < 0,85); si entra, (escala ok, precisión ok)."""
    f1 = t["macro_f1_mejor_respuesta"]
    if f1 is None or f1 < H1_F1:
        return None
    pc = t["precision_contestada"]
    return t["escala"] <= H1_ESCALA, pc is not None and pc >= H1_PRECISION


def fila_h2(t, tope):
    """Fila de la tabla con la mayor abstención real ≤ tope (la que más precisión compra sin pasarse)."""
    cand = [f for f in t["tabla"] if f[1] <= tope + 1e-9]
    return max(cand, key=lambda f: f[1]) if cand else None


def fmt(x, pct=False):
    if x is None:
        return "—"
    return f"{100 * x:.1f} %" if pct else f"{x:.3f}"


def svg(tarea, t):
    W, H, L, R, T, B = 640, 400, 56, 20, 36, 48
    puntos = t["puntos"]
    x = lambda v: L + v * (W - L - R)
    lo = min([p for _, p, _ in puntos] + [0.9])
    lo = max(0.0, math.floor(lo * 10) / 10 - (0.1 if lo < 0.9 else 0))
    y = lambda v: T + (1 - (max(v, lo) - lo) / (1 - lo)) * (H - T - B)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="#fff"/>',
         f'<text x="{L}" y="22" font-size="14" font-weight="bold">{tarea}: precisión frente a abstención (n = {t["n"]})</text>']
    for k in range(0, 11, 2):
        v = k / 10
        s.append(f'<line x1="{x(v):.1f}" y1="{T}" x2="{x(v):.1f}" y2="{H - B}" stroke="#e5e5e5"/>'
                 f'<text x="{x(v):.1f}" y="{H - B + 16}" text-anchor="middle" fill="#555">{k * 10} %</text>')
    paso = 0.05 if 1 - lo <= 0.3 else 0.1
    v = lo
    while v <= 1 + 1e-9:
        s.append(f'<line x1="{L}" y1="{y(v):.1f}" x2="{W - R}" y2="{y(v):.1f}" stroke="#e5e5e5"/>'
                 f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end" fill="#555">{v:.2f}</text>')
        v += paso
    s.append(f'<line x1="{L}" y1="{y(H1_PRECISION):.1f}" x2="{W - R}" y2="{y(H1_PRECISION):.1f}" stroke="#b45309" stroke-dasharray="5 4"/>'
             f'<text x="{W - R - 4}" y="{y(H1_PRECISION) - 5:.1f}" text-anchor="end" fill="#b45309">precisión 0,95</text>')
    s.append(f'<line x1="{x(H1_ESCALA):.1f}" y1="{T}" x2="{x(H1_ESCALA):.1f}" y2="{H - B}" stroke="#b45309" stroke-dasharray="5 4"/>')
    if puntos:
        pts = " ".join(f"{x(a):.1f},{y(p):.1f}" for a, p, _ in sorted(puntos))
        s.append(f'<polyline points="{pts}" fill="none" stroke="#2563eb" stroke-width="2"/>')
    pc = t["precision_contestada"]
    if pc is not None:
        s.append(f'<circle cx="{x(t["escala"]):.1f}" cy="{y(pc):.1f}" r="5" fill="#dc2626"/>'
                 f'<text x="{x(t["escala"]) + 8:.1f}" y="{y(pc) + 4:.1f}" fill="#dc2626">cascada con τ de CALIB</text>')
    s.append(f'<text x="{(L + W - R) / 2}" y="{H - 10}" text-anchor="middle" fill="#333">abstención (fracción que escala)</text>')
    s.append(f'<text transform="translate(14 {(T + H - B) / 2}) rotate(-90)" text-anchor="middle" fill="#333">precisión de lo contestado</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"


def md_tarea(tarea, t, tope):
    h2 = fila_h2(t, tope)
    m = [f"# {tarea}", "",
         f"n = {t['n']}; escalan {t['escalan']} ({fmt(t['escala'], True)}); errores del cliente: {t['errores_cliente']}. Capas: "
         + ", ".join(f"{k} {v}" for k, v in sorted(t["capas"].items())) + ".", "",
         f"- Precisión de lo contestado: {fmt(t['precision_contestada'])}; macro-F1 de lo contestado: {fmt(t['macro_f1_contestada'])}.",
         f"- Macro-F1 con lo escalado como fallo: {fmt(t['macro_f1_escala_fallo'])}; con la mejor respuesta de todas: {fmt(t['macro_f1_mejor_respuesta'])}.",
         f"- H2: con abstención ≤ {100 * tope:.0f} %: " + (f"τ = {h2[3]:.3f} (abstención {100 * h2[1]:.1f} %), precisión {h2[2]:.3f}." if h2 else "ningún τ."), "",
         "| abstención ≤ | abstención real | precisión | τ |", "|---|---|---|---|"]
    m += [f"| {a} % | {100 * ab:.1f} % | {p:.3f} | {tau:.3f} |" for a, ab, p, tau in t["tabla"]]
    return "\n".join(m) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pred", action="append", required=True, help="tarea=pred.jsonl")
    ap.add_argument("--verdad", action="append", required=True, help="tarea=test.jsonl")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--max-abstencion", type=float, default=0.20)
    a = ap.parse_args()
    preds = dict(kv.partition("=")[::2] for kv in a.pred)
    verdades = dict(kv.partition("=")[::2] for kv in a.verdad)
    if set(preds) != set(verdades):
        sys.exit(f"--pred y --verdad deben cubrir las mismas tareas: {sorted(preds)} frente a {sorted(verdades)}")
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    res = {}
    for tarea in sorted(preds):
        verdad = {r["id"]: r["etiqueta"] for r in leer(verdades[tarea]) if r.get("split", "test") == "test"}
        t = medir(leer(preds[tarea]), verdad)
        res[tarea] = t
        (out / f"{tarea}.md").write_text(md_tarea(tarea, t, a.max_abstencion))
        (out / f"{tarea}.svg").write_text(svg(tarea, t))
        print(f"{tarea}: n={t['n']} escala={fmt(t['escala'], True)} precisión contestada={fmt(t['precision_contestada'])} "
              f"F1 contestada={fmt(t['macro_f1_contestada'])} F1 escala=fallo={fmt(t['macro_f1_escala_fallo'])}")
    inf = ["# Abstención de la cascada con tráfico no adversarial (T4.6)", "",
           "| tarea | n | escala | precisión contestada | macro-F1 contestada | macro-F1 escala=fallo | macro-F1 mejor respuesta | H1 | "
           f"τ (abst. ≤ {100 * a.max_abstencion:.0f} %) | abstención | precisión |", "|" + "---|" * 11]
    for tarea, t in res.items():
        v = veredicto_h1(t)
        h1 = "no aplica (F1 < 0,85)" if v is None else ("se cumple" if all(v) else "se refuta (" + ", ".join(
            k for k, ok in zip(("escala > 30 %", "precisión < 0,95"), v) if not ok) + ")")
        h2 = fila_h2(t, a.max_abstencion)
        inf.append(f"| {tarea} | {t['n']} | {fmt(t['escala'], True)} | {fmt(t['precision_contestada'])} | {fmt(t['macro_f1_contestada'])} | "
                   f"{fmt(t['macro_f1_escala_fallo'])} | {fmt(t['macro_f1_mejor_respuesta'])} | {h1} | "
                   + (f"{h2[3]:.3f} | {100 * h2[1]:.1f} % | {h2[2]:.3f} |" if h2 else "— | — | — |"))
    (out / "informe.md").write_text("\n".join(inf) + "\n")
    (out / "abstencion.json").write_text(json.dumps(
        {k: {kk: vv for kk, vv in t.items() if kk != "puntos"} for k, t in res.items()}, ensure_ascii=False, indent=1))
    print("\n".join(inf))


if __name__ == "__main__":
    main()
