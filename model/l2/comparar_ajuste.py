"""Comparación del ajuste fino (ajuste.sh): `python -m model.l2.comparar_ajuste DIR` escribe en stdout el markdown con JevBench k=0, M3 y M4
del checkpoint nuevo frente a G.8 (`DIR/nuevo/` y `DIR/g8/`). `--una {ajuste,m3,m4} FICHERO` da la línea de resumen de estado.tsv."""
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


def comparacion(r):
    out = ["# Ajuste fino de G.8 (aumento + español) frente a G.8, medidos en la misma máquina", "",
           "## JevBench k=0", "", "| | exactitud | macro-F1 |", "|---|---|---|"]
    for etiqueta, n in (("nuevo", "nuevo"), ("G.8", "g8")):
        v = _jev(r, n)
        out.append("| %s | %s | %s |" % (etiqueta, *(("%.4f" % x for x in v) if v else ("—", "—"))))
    n3, g3 = _json("%s/nuevo/m3/robustez.json" % r), _json("%s/g8/m3/robustez.json" % r)
    L2 = lambda d: d["global"]["L2"] if d else {}
    out += ["", "## M3: % de decisiones de L2 que cambian (umbral 5 %)", "", "| variante | nuevo | G.8 |", "|---|---|---|"]
    for t in sorted(set(L2(n3)) | set(L2(g3))):
        out.append("| %s | %s | %s |" % (ETIQUETA.get(t, t) + (" (sin criterio)" if t in SIN_CRITERIO else ""), *("%.1f %%" % (100 * L2(d)[t]["pct_cambia"]) if t in L2(d) else "—" for d in (n3, g3))))
    n4, g4 = _json("%s/nuevo/m4/espanol.json" % r), _json("%s/g8/m4/espanol.json" % r)
    T = lambda d: d["tareas"] if d else {}
    out += ["", "## M4: exactitud es − en (puntos)", "", "| par | nuevo | G.8 |", "|---|---|---|"]
    for t in sorted(set(T(n4)) | set(T(g4))):
        out.append("| %s | %s | %s |" % ("**media**" if t == "__media__" else t,
                                         *("%+.1f" % (100 * T(d)[t]["d_acc"]) if t in T(d) else "—" for d in (n4, g4))))
    return "\n".join(out)


def una(que, ruta):
    d = _json(ruta)
    if que == "ajuste":
        return "%d pasos, %d filas, mejor dev %.4f en el paso %d, %.0f s" % (d["pasos"], d["filas"], d["mejor"]["f1"], d["mejor"]["paso"], d["segundos"])
    if que == "m3":
        g = d["global"]["L2"]
        return "L2 cambia > 5 %%: %d de %d tipos" % (sum(1 for t, r in g.items() if r["pct_cambia"] > d["umbral_cambio"] and t not in SIN_CRITERIO), len([t for t in g if t not in SIN_CRITERIO]))
    return "Δ(es−en) exactitud %+.1f pts" % (100 * d["tareas"]["__media__"]["d_acc"])


if __name__ == "__main__":
    if sys.argv[1] == "--una":
        print(una(sys.argv[2], sys.argv[3]))
    else:
        print(comparacion(sys.argv[1]))
