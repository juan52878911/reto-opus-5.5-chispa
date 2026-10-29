"""Informe de JevBench público: exactitud y macro-F1 por variante, cobertura y escalado de la cascada, y comparación con 0,55.

    python -m model.evaluacion.jevbench_informe DIR

Lee de DIR `jevbench_filas.jsonl` y `pred/{l2_k0,l2_k8,l2_k32,cascada_k8,cascada_k32}.jsonl` (los que existan; con
`pred/cascada_k<k>_omitidos.json`), y escribe `DIR/informe.md` y `DIR/informe.json`. Solo biblioteca estándar y numpy (vía chispa_eval).
Subconjuntos: «todos»; «con soporte» (casos con otros casos de su esquema fuera de sus paráfrasis); «cascada» (los que la cascada pudo
medir limpio: soporte con todas las opciones). H2 se mide siempre sobre los MISMOS casos que la variante de referencia.
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

from . import chispa_eval as CE

UMBRAL = 0.55          # Qwen3-0.6B sin entrenar en JevBench público (criterio de la fase 2)
CHARS_TRUNCA = 400     # ≈ MAX_TOK = 128 tokens de e5: por encima, L2 no ve el final del estado
VARIANTES = ("l2_k0", "l2_k8", "l2_k32", "cascada_k8", "cascada_k32")


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def wilson(a, n, z=1.96):
    if not n:
        return (None, None)
    p = a / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def top1(probs, opciones):
    """La opción más probable; None si la predicción no da ninguna (escalado sin respuesta o error): cuenta como fallo."""
    if sum(probs.get(o, 0.0) for o in opciones) <= 0:
        return None
    return max(opciones, key=lambda o: probs.get(o, 0.0))


def metricas(filas, preds):
    """Exactitud (con IC de Wilson 95 %) y macro-F1 (global agrupado y media por familia) de las `filas` con predicción."""
    fs = [r for r in filas if r["id"] in preds]
    if not fs:
        return {"n": 0}
    ev = CE.evaluar(fs, [{"id": r["id"], "probs": preds[r["id"]]["probs"]} for r in fs])
    ok = sum(top1(preds[r["id"]]["probs"], r["opciones"]) == r["etiqueta"] for r in fs)
    lo, hi = wilson(ok, len(fs))
    fam = ev["por_tarea"]
    out = {"n": len(fs), "aciertos": ok, "exactitud": ok / len(fs), "ic95": [lo, hi], "macro_f1": ev["global"]["macro_f1"],
           "macro_f1_familias": sum(m["macro_f1"] for m in fam.values()) / len(fam), "ece": ev["global"]["ece"]}
    esc = [preds[r["id"]].get("escalate") for r in fs]
    if any(e is not None for e in esc):
        resp = [r for r, e in zip(fs, esc) if not e]
        okr = sum(top1(preds[r["id"]]["probs"], r["opciones"]) == r["etiqueta"] for r in resp)
        out.update({"escalados": len(fs) - len(resp), "errores": sum(preds[r["id"]].get("layer") == "error" for r in fs), "cobertura": len(resp) / len(fs),
                    "exactitud_respondidos": okr / len(resp) if resp else None,
                    "capas": dict(Counter(preds[r["id"]].get("layer", "?") for r in fs))})
    return out


def pares(filas, a, b):
    """(a acierta y b no, b acierta y a no) sobre los casos que tienen predicción en las dos."""
    fa = fb = 0
    for r in filas:
        if r["id"] in a and r["id"] in b:
            x, y = (top1(p[r["id"]]["probs"], r["opciones"]) == r["etiqueta"] for p in (a, b))
            fa += x and not y
            fb += y and not x
    return fa, fb


def f3(x):
    return "-" if x is None else f"{x:.3f}"


def informe(d):
    d = Path(d)
    filas = leer(d / "jevbench_filas.jsonl")
    preds = {v: {p["id"]: p for p in leer(d / "pred" / f"{v}.jsonl")} for v in VARIANTES if (d / "pred" / f"{v}.jsonl").exists()}
    omitidos = {v: json.loads((d / "pred" / f"{v}_omitidos.json").read_text()) for v in VARIANTES
                if (d / "pred" / f"{v}_omitidos.json").exists()}
    ids_sop = {i for i, p in preds.get("l2_k8", {}).items() if p.get("soporte_n", 0) > 0}
    ids_cas = set(preds.get("cascada_k8", {}))
    subs = {"todos": filas, "con soporte": [r for r in filas if r["id"] in ids_sop] if ids_sop else [],
            "cascada": [r for r in filas if r["id"] in ids_cas]}
    res = {"variantes": {}, "n_casos": len(filas), "umbral": UMBRAL}
    md = ["# JevBench público (231 decisiones): L2 y la cascada de un cliente nuevo", ""]
    md += [f"Casos: {len(filas)} ({dict(Counter(r['tipo'] for r in filas))}), esquemas distintos: {len({r['esquema'] for r in filas})}, "
           f"con algún otro caso de su esquema fuera de sus paráfrasis: {len(ids_sop)}, medibles por la cascada: {len(ids_cas)}.", ""]
    md += ["## Exactitud y macro-F1 por variante y subconjunto", "",
           "| variante | subconjunto | n | exactitud | IC95 | macro-F1 (agrupado) | macro-F1 (media por familia) | ECE |", "|---|---|---|---|---|---|---|---|"]
    for v, p in preds.items():
        res["variantes"][v] = {}
        for s, fs in subs.items():
            m = metricas(fs, p)
            res["variantes"][v][s] = m
            if m["n"]:
                md.append(f"| {v} | {s} | {m['n']} | {m['exactitud']:.3f} | {f3(m['ic95'][0])}–{f3(m['ic95'][1])} | {m['macro_f1']:.3f} | "
                          f"{m['macro_f1_familias']:.3f} | {m['ece']:.3f} |")
    cas = [v for v in preds if v.startswith("cascada")]
    if cas:
        md += ["", "## Cobertura y escalado de la cascada (sobre los casos que midió)", "",
               "| variante | n | cobertura (no escala) | escalados | exactitud respondidos | exactitud total (sin respuesta = fallo) | errores | capas |", "|---|---|---|---|---|---|---|---|"]
        for v in cas:
            m = res["variantes"][v]["cascada"]
            if m["n"]:
                md.append(f"| {v} | {m['n']} | {f3(m.get('cobertura'))} | {m.get('escalados', '-')} | {f3(m.get('exactitud_respondidos'))} | "
                          f"{m['exactitud']:.3f} | {m.get('errores', '-')} | {m.get('capas')} |")
        for v in cas:
            om = omitidos.get(v, [])
            if om:
                md.append(f"\nOmitidos en {v}: {len(om)} casos: " + ", ".join(f"{n} {m}" for m, n in Counter(o['motivo'].split(':')[0] for o in om).most_common()))
    md += ["", "## Hipótesis", ""]
    z = res["variantes"].get("l2_k0", {}).get("todos")
    if z and z["n"]:
        v = "confirmada" if z["exactitud"] >= UMBRAL else "refutada"
        dentro = z["ic95"][0] <= UMBRAL <= z["ic95"][1]
        md.append(f"- **H1** (L2 zero-shot ≥ {UMBRAL}): exactitud {z['exactitud']:.3f} (IC95 {f3(z['ic95'][0])}–{f3(z['ic95'][1])}, n={z['n']}) → {v} "
                  "en estimación puntual" + ("; el intervalo incluye 0,55: con 231 casos no se distingue de él" if dentro else "") + ".")
        res["H1"] = {"exactitud": z["exactitud"], "ic95": z["ic95"], "cumple": z["exactitud"] >= UMBRAL}
    for v in ("l2_k8", "l2_k32", "cascada_k8", "cascada_k32"):
        if v not in preds or not preds.get("l2_k0"):
            continue
        s = "cascada" if v.startswith("cascada") else "con soporte"
        fs = subs[s]
        mv, m0 = res["variantes"][v].get(s), metricas(fs, preds["l2_k0"])
        if not mv or not mv["n"] or not m0["n"]:
            continue
        a, b = pares(fs, preds[v], preds["l2_k0"])
        res.setdefault("H2", {})[v] = {"n": mv["n"], "exactitud": mv["exactitud"], "zero_shot": m0["exactitud"], "delta": mv["exactitud"] - m0["exactitud"],
                                       "mejora_en": a, "empeora_en": b}
        md.append(f"- **H2** {v} frente a L2 zero-shot en los mismos {mv['n']} casos ({s}): {mv['exactitud']:.3f} vs {m0['exactitud']:.3f} "
                  f"(Δ {mv['exactitud'] - m0['exactitud']:+.3f}); acierta donde el zero-shot falla en {a}, y al revés en {b}.")
    if "cascada_k8" in preds and "cascada_k32" in preds and preds["cascada_k8"].keys() == preds["cascada_k32"].keys():
        igual = all(preds["cascada_k8"][i]["probs"] == preds["cascada_k32"][i]["probs"] for i in preds["cascada_k8"])
        md.append(f"- k = 8 y k = 32 {'son idénticos' if igual else 'difieren'} en la cascada: ningún esquema de JevBench público tiene más de 8 ejemplos "
                  "por opción, así que el tope k no actúa y el soporte es el mismo.")
    largos = sum(len(r["texto"]) > CHARS_TRUNCA for r in filas)
    md += ["", "## Límites", "",
           f"- {largos} de {len(filas)} casos tienen estados de más de {CHARS_TRUNCA} caracteres (≈ 128 tokens): L2 trunca el estado (MAX_TOK) y no ve el final.",
           "- Los esquemas son casi todos de un solo caso: el soporte sale de otros casos del mismo esquema (misma pregunta, opciones y criterios), "
           "sin el caso ni sus paráfrasis (`grupo`); donde no hay, el caso queda sin soporte y no cuenta como «con soporte».",
           "- La cascada solo se mide donde `chispa train` puede entrenar sin forzar: el soporte debe cubrir todas las opciones. No se recorta el esquema.",
           "- Es el split público de JevBench (231 casos): no es la puntuación oficial de la tabla (sellada, otra escala)."]
    (d / "informe.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (d / "informe.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return "\n".join(md)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__.split("\n")[0] + "\nuso: python -m model.evaluacion.jevbench_informe DIR", file=sys.stderr)
        return 2
    print(informe(argv[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
