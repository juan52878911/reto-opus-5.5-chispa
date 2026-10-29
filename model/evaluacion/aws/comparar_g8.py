"""comparacion.md de G.8 (lo corre model/l2/aws/general.sh): H1 y H2 con lo que haya en disco.

    python comparar_g8.py --out DIR --ref DIR --kappa K [--excluir massive,hatecheck,inyecciones]

Disposición (la escribe general.sh; lo que falte sale como «-» y la hipótesis como «sin datos», nunca como cumplida):
  OUT|REF/k8|k32/{resultados,resultados_soporte}.json     evaluar.py con κ = 0 (T2.1b es el REF, entrenado con las tareas)
  OUT/kappa-k8|k32/resultados_soporte.json                evaluar.py con κ = K
  OUT/jev/{jevbench_filas.jsonl,pred/l2_k0|k8|k32.jsonl}  jevbench_l2 con κ = 0;  OUT/jev-kappa/pred/l2_k8|k32.jsonl con κ = K
"""
import argparse
import json
import sys
from pathlib import Path

JEV_G1 = {"zero-shot": 0.407, "con soporte": 0.230}   # exactitud de G.1 con T2.1b (resultados/jevbench-20261029)
TAREAS = ["massive", "hatecheck", "inyecciones", "tasksource_fuera", "clinc150", "herramientas"]
MARGEN_H2 = 0.01


def leer_json(ruta):
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def f1s(ruta):
    r = leer_json(ruta)
    return {t: v["global"]["macro_f1"] for t, v in r.items()} if r else {}


def celda(d, t):
    return "%.3f" % d[t] if t in d else "-"


def razon(a, b):
    return a / b if a is not None and b else None


def jev(dir_, k):
    """(exactitud, macro-F1) de JevBench para el k dado, o None."""
    p = Path(dir_) / "pred" / ("l2_k%d.jsonl" % k)
    fp = Path(dir_) / "jevbench_filas.jsonl"
    if not (p.exists() and fp.exists()):
        return None
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from model.evaluacion import chispa_eval as CE
    filas = [json.loads(l) for l in fp.read_text(encoding="utf-8").splitlines() if l.strip()]
    preds = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    g = CE.evaluar(filas, [{x: q[x] for x in ("id", "probs", "ms")} for q in preds])["global"]
    return g["exactitud"], g["macro_f1"]


def comparar(out, ref, kappa, excluir):
    out, ref = Path(out), Path(ref)
    n0 = f1s(out / "k8" / "resultados.json")
    r0 = f1s(ref / "k8" / "resultados.json")
    s = {k: f1s(out / ("k%d" % k) / "resultados_soporte.json") for k in (8, 32)}
    sk = {k: f1s(out / ("kappa-k%d" % k) / "resultados_soporte.json") for k in (8, 32)}
    rs = {k: f1s(ref / ("k%d" % k) / "resultados_soporte.json") for k in (8, 32)}
    lin = ["# G.8 L2 de propósito general: comparación", "",
           "## Tareas no vistas y control (macro-F1 global; κ = %g; «ref» = T2.1b, que sí vio las tareas)" % kappa, "",
           "| tarea | no vista | zero-shot | ref zero-shot | razón | k=8 | k=8 κ | k=32 | k=32 κ | ref k=32 |", "|" + "---|" * 10]
    h1_ok, h1_n = True, 0
    for t in TAREAS:
        if t not in n0:
            continue
        e = t in excluir or t == "tasksource_fuera"
        rz = razon(n0.get(t), r0.get(t))
        if e and rz is not None:
            h1_n += 1
            h1_ok &= rz >= 0.9
        elif e:
            h1_ok = False
        lin.append("| %s | %s | %.3f | %s | %s | %s | %s | %s | %s | %s |" % (
            t, "sí" if e else "no (control)", n0[t], celda(r0, t), "-" if rz is None else "%.2f" % rz, celda(s[8], t),
            celda(sk[8], t), celda(s[32], t), celda(sk[32], t), celda(rs[32], t)))
    lin.append("")
    lin.append("**H1 (no vistas)** zero-shot ≥ 0,9 × T2.1b en todas las no vistas: " + (
        "sin datos" if not h1_n else "se cumple" if h1_ok else "SE REFUTA"))

    lin += ["", "## JevBench público (231 casos; exactitud / macro-F1)", "", "| variante | exactitud | macro-F1 |", "|---|---|---|"]
    filas_jev = [("zero-shot", out / "jev", 0), ("k=8", out / "jev", 8), ("k=8 κ=%g" % kappa, out / "jev-kappa", 8),
                 ("k=32", out / "jev", 32), ("k=32 κ=%g" % kappa, out / "jev-kappa", 32)]
    m = {}
    for nombre, d, k in filas_jev:
        m[nombre] = jev(d, k)
        lin.append("| %s | %s | %s |" % ((nombre,) + (("%.3f" % m[nombre][0], "%.3f" % m[nombre][1]) if m[nombre] else ("-", "-"))))
    lin.append("")
    lin.append("T2.1b (G.1): zero-shot %.3f, con soporte %.3f (exactitud)." % (JEV_G1["zero-shot"], JEV_G1["con soporte"]))
    z = m["zero-shot"]
    lin.append("**H1 (JevBench)** exactitud sin soporte ≥ 0,55: " + ("sin datos" if not z else "se cumple (%.3f)" % z[0] if z[0] >= 0.55
                                                                    else "SE REFUTA (%.3f)" % z[0]))

    lin += ["", "## H2: el soporte con shrinkage no empeora el zero-shot en más de 1 punto y mejora con k ≥ 4", "",
            "| conjunto | zero-shot | k=8 κ | Δ k=8 | k=32 κ | Δ k=32 |", "|" + "---|" * 6]
    nunca, mejora, hay = True, True, False
    for t in TAREAS:
        if t not in n0 or t == "tasksource_fuera":
            continue
        d8, d32 = (sk[k][t] - n0[t] if t in sk[k] else None for k in (8, 32))
        hay |= d8 is not None
        for d in (d8, d32):
            nunca &= d is None or d >= -MARGEN_H2
        mejora &= all(d is None or d > 0 for d in (d8, d32))
        lin.append("| %s | %.3f | %s | %s | %s | %s |" % (t, n0[t], celda(sk[8], t), "-" if d8 is None else "%+.3f" % d8,
                                                          celda(sk[32], t), "-" if d32 is None else "%+.3f" % d32))
    jz = m["zero-shot"]
    for nombre in ("k=8 κ=%g" % kappa, "k=32 κ=%g" % kappa):
        if jz and m[nombre]:
            d = m[nombre][0] - jz[0]
            hay = True
            nunca &= d >= -MARGEN_H2
            mejora &= d > 0
            lin.append("| JevBench %s | %.3f | %.3f | %+.3f | | |" % (nombre, jz[0], m[nombre][0], d))
    lin.append("")
    lin.append("**H2** nunca peor que el zero-shot en más de 1 punto: " + ("sin datos" if not hay else "se cumple" if nunca else "SE REFUTA"))
    lin.append("**H2** mejora con k ≥ 4 (en todas): " + ("sin datos" if not hay else "se cumple" if mejora else "NO EN TODAS"))
    return "\n".join(lin) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--kappa", type=float, default=4.0)
    ap.add_argument("--excluir", default="massive,hatecheck,inyecciones")
    a = ap.parse_args(argv)
    t = comparar(a.out, a.ref, a.kappa, set(a.excluir.split(",")))
    (Path(a.out) / "comparacion.md").write_text(t, encoding="utf-8")
    print(t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
