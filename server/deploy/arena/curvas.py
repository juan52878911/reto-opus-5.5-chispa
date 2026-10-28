#!/usr/bin/env python3
"""Curvas de cobertura (T2.4) de la cabeza `cvtest` de T2.2d: precisión frente a cobertura al barrer τ.

  curvas.py --pred DIR_PRED --verdad tarea=ruta.jsonl [--verdad ...] --salida DIR
      DIR_PRED/<tarea>.jsonl = {id, probs, ms} (cvtest/pred/ de resultados.tgz); ruta.jsonl = filas con id y etiqueta (si traen
      `split`, solo las de test). La confianza es la probabilidad máxima; se acepta lo que la supera (conf ≥ τ) y se cuenta
      el acierto de la etiqueta de mayor probabilidad.
  Escribe, por tarea, DIR/<tarea>.md (una fila cada 5 % de cobertura, con su τ) y DIR/<tarea>.svg, y DIR/curvas.json.
Solo biblioteca estándar.
"""
import argparse
import json
import sys
from pathlib import Path

PASO = 5   # % de cobertura entre filas de la tabla


def leer(ruta):
    return [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]


def curva(preds, verdad):
    """-> (n, [(cobertura, precisión, τ)]) ordenada por cobertura creciente, un punto por cada fila aceptada."""
    pares = []
    for p in preds:
        if p["id"] not in verdad:
            continue
        etq, conf = max(p["probs"].items(), key=lambda kv: kv[1])
        pares.append((conf, etq == verdad[p["id"]]))
    n = len(pares)
    if not n:
        raise SystemExit("ninguna predicción coincide con la verdad (¿ids distintos?)")
    pares.sort(key=lambda c: -c[0])
    puntos, ok = [], 0
    for i, (conf, acierto) in enumerate(pares, 1):
        ok += acierto
        if i == n or pares[i][0] != conf:   # un punto por τ: se acepta todo el empate
            puntos.append((i / n, ok / i, conf))
    return n, puntos


def tabla(puntos):
    """Una fila por cada 5 % de cobertura: el primer punto de la curva que la alcanza."""
    filas, j = [], 0
    for c in range(PASO, 101, PASO):
        while j < len(puntos) - 1 and puntos[j][0] < c / 100 - 1e-9:
            j += 1
        cob, prec, tau = puntos[j]
        filas.append((c, cob, prec, tau))
    return filas


def svg(tarea, n, puntos, filas):
    W, H, L, R, T, B = 640, 400, 56, 20, 36, 48
    x = lambda v: L + v * (W - L - R)
    lo = min(p for _, p, _ in puntos)
    lo = max(0.0, (int(lo * 10) - 1) / 10) if lo < 0.9 else 0.8
    y = lambda v: T + (1 - (v - lo) / (1 - lo)) * (H - T - B)
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="#fff"/>',
         f'<text x="{L}" y="22" font-size="14" font-weight="bold">{tarea}: precisión frente a cobertura (n = {n})</text>']
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
    if lo <= 0.95:
        s.append(f'<line x1="{L}" y1="{y(0.95):.1f}" x2="{W - R}" y2="{y(0.95):.1f}" stroke="#b45309" stroke-dasharray="5 4"/>'
                 f'<text x="{W - R - 4}" y="{y(0.95) - 5:.1f}" text-anchor="end" fill="#b45309">precisión 0,95</text>')
    pts = " ".join(f"{x(c):.1f},{y(max(p, lo)):.1f}" for c, p, _ in puntos)
    s.append(f'<polyline points="{pts}" fill="none" stroke="#2563eb" stroke-width="2"/>')
    for c, _, p, _ in filas:
        s.append(f'<circle cx="{x(c / 100):.1f}" cy="{y(max(p, lo)):.1f}" r="2.5" fill="#2563eb"/>')
    s.append(f'<text x="{(L + W - R) / 2}" y="{H - 10}" text-anchor="middle" fill="#333">cobertura (fracción que se contesta sin escalar)</text>')
    s.append(f'<text transform="translate(14 {(T + H - B) / 2}) rotate(-90)" text-anchor="middle" fill="#333">precisión</text>')
    s.append("</svg>")
    return "\n".join(s) + "\n"


def cobertura_a(puntos, objetivo):
    ok = [c for c, p, _ in puntos if p >= objetivo - 1e-12]
    return max(ok) if ok else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--verdad", action="append", required=True, help="tarea=ruta.jsonl")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    resumen = {}
    for kv in a.verdad:
        tarea, _, ruta = kv.partition("=")
        verdad = {r["id"]: r["etiqueta"] for r in leer(ruta) if r.get("split", "test") == "test"}
        preds = leer(Path(a.pred) / f"{tarea}.jsonl")
        n, puntos = curva(preds, verdad)
        filas = tabla(puntos)
        md = [f"# {tarea}: precisión frente a cobertura (cabeza cvtest, T2.2d)", "",
              f"n = {n} filas de test. Se contesta lo que tiene probabilidad máxima ≥ τ; el resto escala.",
              f"Cobertura a precisión 0,95: {100 * cobertura_a(puntos, 0.95):.1f} %. Precisión sin escalar nada: {puntos[-1][1]:.3f}.", "",
              "| cobertura | cobertura real | precisión | τ |", "|---|---|---|---|"]
        md += [f"| {c} % | {100 * cob:.1f} % | {prec:.3f} | {tau:.3f} |" for c, cob, prec, tau in filas]
        (out / f"{tarea}.md").write_text("\n".join(md) + "\n")
        (out / f"{tarea}.svg").write_text(svg(tarea, n, puntos, filas))
        resumen[tarea] = {"n": n, "precision_total": puntos[-1][1], "cobertura_p95": cobertura_a(puntos, 0.95),
                          "tabla": [{"cobertura": c, "cobertura_real": cob, "precision": prec, "tau": tau} for c, cob, prec, tau in filas]}
        print(f"{tarea}: n={n}, cobertura a precisión 0,95 = {100 * resumen[tarea]['cobertura_p95']:.1f} %")
    (out / "curvas.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
