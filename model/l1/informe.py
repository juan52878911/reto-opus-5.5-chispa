"""Informe en markdown a partir de `resultados.json` de evaluar.py.

    python -m model.l1.informe model/l1/resultados/<fecha>
"""
import json
import sys
from pathlib import Path

import numpy as np

from . import comun


def tabla(res):
    sist = [("potion-zs", "potion", "zs"), ("potion-proto", "potion", "proto")]
    for m in res["tamano"]:
        if m.startswith("propio"):
            sist += [(m + "-zs", m, "zs"), (m + "-proto", m, "proto"), (m + "-cabeza", m, "cabeza")]
    out = ["| tarea | " + " | ".join(s[0] for s in sist) + " |", "|---" * (len(sist) + 1) + "|"]
    medias = {s[0]: [] for s in sist}
    for t in comun.TAREAS:
        if t not in res["f1"]:
            continue
        fila = []
        for nombre, m, k in sist:
            v = res["f1"][t][m][k]
            medias[nombre].append(v)
            fila.append("%.3f" % v)
        out.append("| %s | %s |" % (t, " | ".join(fila)))
    out.append("| **media** | %s |" % " | ".join("**%.3f**" % np.mean(medias[s[0]]) for s in sist))
    return out, medias


def main(d):
    d = Path(d)
    res = json.loads((d / "resultados.json").read_text())
    t, medias = tabla(res)
    n_cab = sum(res["f1"][x][m]["cabeza"] > res["f1"][x][m]["proto"] for x in res["f1"] for m in res["f1"][x] if m == "propio-256")
    L = ["# L1 propio (T3.1c): informe", "", "Host: %s" % res["host"], "Maestro de la cabeza: `%s` (fuera de pliegue, k = 5)." % res["maestro"], "",
         "## Macro-F1 por tarea (test de T2.2; soporte = 32 por clase del train)", ""] + t
    L += ["", "Cabeza > proto en %d de %d tareas con propio-256 (H2 pide ≥ 3)." % (n_cab, len(res["f1"])), "",
          "## Tamaño en disco y coseno frente a e5-small (2 274 frases del sondeo)", "",
          "| modelo | tamaño (MB) | coseno tras ridge (2 mitades) | Spearman de cosenos de pares | frases sin vector |", "|---|---|---|---|---|"]
    for m, tam in res["tamano"].items():
        c = res["coseno"][m]
        L.append("| %s | %.1f | %.4f | %.4f | %d |" % (m, tam / 1e6, c[0], c[1], c[2]))
    L += ["", "## Latencia de Embed (runtime/l1, 2 000 repeticiones por tamaño)", "",
          "| modelo | 16 tok p50 / p99 | 64 tok p50 / p99 | 256 tok p50 / p99 |", "|---|---|---|---|"]
    for m, lat in res["latencia"].items():
        ks = sorted(lat, key=int)
        L.append("| %s | %s |" % (m, " | ".join("%s / %s" % tuple(lat[k]) for k in ks)))
    if (d / "conclusiones.md").exists():
        L.append((d / "conclusiones.md").read_text().rstrip("\n"))
    (d / "informe.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main(sys.argv[1])
