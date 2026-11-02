"""Comparación del ajuste fino (ajuste.sh): `python -m model.l2.comparar_ajuste DIR [--base v2]` escribe en stdout el markdown con JevBench k=0, M3 y M4
del checkpoint nuevo frente a la base (`DIR/nuevo/` y `DIR/g8/`; con `--base v2`, `DIR/v2/`, el ajuste v3). Las filas de M4 solo en español (MMMLU
sin pareja en inglés) se listan aparte. `--una {ajuste,m3,m4} FICHERO` da la línea de resumen de estado.tsv."""
import json
import re
import sys

from .robustez import ETIQUETA, SIN_CRITERIO


def _json(ruta):
    try:
        return json.load(open(ruta))
    except (OSError, ValueError):
        return None


def _jev(r, n):
    try:
        m = re.search(r"L2 k=0: exactitud ([\d.]+), macro-F1 ([\d.]+)", open("%s/%s/jev.log" % (r, n)).read())
        return (float(m[1]), float(m[2])) if m else None
    except OSError:
        return None


def comparacion(r, base="g8"):
    et = {"g8": "G.8", "v2": "v2"}.get(base, base)
    out = ["# Ajuste fino (aumento + español) frente a %s, medidos en la misma máquina" % et, "",
           "## JevBench k=0", "", "| | exactitud | macro-F1 |", "|---|---|---|"]
    for etiqueta, n in (("nuevo", "nuevo"), (et, base)):
        v = _jev(r, n)
        out.append("| %s | %s | %s |" % (etiqueta, *(("%.4f" % x for x in v) if v else ("—", "—"))))
    n3, g3 = _json("%s/nuevo/m3/robustez.json" % r), _json("%s/%s/m3/robustez.json" % (r, base))
    L2 = lambda d: d["global"]["L2"] if d else {}
    out += ["", "## M3: % de decisiones de L2 que cambian (umbral 5 %)", "", "| variante | nuevo | %s |" % et, "|---|---|---|"]
    for t in sorted(set(L2(n3)) | set(L2(g3))):
        out.append("| %s | %s | %s |" % (ETIQUETA.get(t, t) + (" (sin criterio)" if t in SIN_CRITERIO else ""), *("%.1f %%" % (100 * L2(d)[t]["pct_cambia"]) if t in L2(d) else "—" for d in (n3, g3))))
    n4, g4 = _json("%s/nuevo/m4/espanol.json" % r), _json("%s/%s/m4/espanol.json" % (r, base))
    T = lambda d: d["tareas"] if d else {}
    out += ["", "## M4: exactitud es − en (puntos)", "", "| par | nuevo | %s |" % et, "|---|---|---|"]
    for t in sorted(set(T(n4)) | set(T(g4))):
        out.append("| %s | %s | %s |" % ("**media**" if t == "__media__" else t,
                                         *("%+.1f" % (100 * T(d)[t]["d_acc"]) if t in T(d) else "—" for d in (n4, g4))))
    se = lambda d: (d or {}).get("solo_es", {})
    if se(n4) or se(g4):
        out += ["", "## M4: solo en español (sin pareja en inglés, no entra en la media), exactitud", "", "| tarea | nuevo | %s |" % et, "|---|---|---|"]
        for t in sorted(set(se(n4)) | set(se(g4))):
            out.append("| %s (sin pareja en inglés) | %s | %s |" % (t, *("%.3f" % se(d)[t]["acc_es"] if t in se(d) else "—" for d in (n4, g4))))
    return "\n".join(out)


def una(que, ruta):
    d = _json(ruta)
    if que == "ajuste":
        return "%d pasos, %d filas, mejor dev %.4f en el paso %d, %.0f s" % (d["pasos"], d["filas"], d["mejor"]["f1"], d["mejor"]["paso"], d["segundos"])
    if que == "m3":
        g = d["global"]["L2"]
        return "L2 cambia > 5 %%: %d de %d tipos" % (sum(1 for t, r in g.items() if r["pct_cambia"] > d["umbral_cambio"] and t not in SIN_CRITERIO), len([t for t in g if t not in SIN_CRITERIO]))
    media = "Δ(es−en) exactitud %+.1f pts" % (100 * d["tareas"]["__media__"]["d_acc"]) if d["tareas"] else "sin pares es/en"
    return media + "".join("; %s solo es %.3f (sin pareja en inglés)" % (t, r["acc_es"]) for t, r in d.get("solo_es", {}).items())


if __name__ == "__main__":
    if sys.argv[1] == "--una":
        print(una(sys.argv[2], sys.argv[3]))
    else:
        print(comparacion(sys.argv[1], sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "g8"))
