"""informe.md de G.9: profesor zero-shot frente a G.8 corrida 2 y T2.1b.

    python -m model.evaluacion.profesor_informe RES [--minutos M] [--precio-h USD] [--licencia nombre=texto ...]

RES = la carpeta de `profesor medir` (una carpeta por modelo con resultados.json). JevBench en exactitud, las tareas no vistas en
macro-F1 (como model/l2/resultados/general-20261029b). Hipótesis: el profesor «-c» saca ≥ 0,55 en JevBench sin soporte y mejora a
G.8 en ≥ +10 puntos de macro-F1 en ≥ 2 de las 4 tareas no vistas.
"""
import argparse
import json
import sys
from pathlib import Path

G8 = {"jevbench": 0.463, "massive": 0.309, "hatecheck": 0.531, "inyecciones": 0.326, "tasksource_fuera": 0.192}
T21B = {"jevbench": 0.407, "massive": 0.487, "hatecheck": 0.610, "inyecciones": 0.862, "tasksource_fuera": 0.221}
NO_VISTAS = ("massive", "hatecheck", "inyecciones", "tasksource_fuera")
MET = {"jevbench": "exactitud"}
UMBRAL_JEV, SALTO = 0.55, 0.10
PRINCIPAL = "bge-m3-zeroshot-c"   # el destilable
LICENCIAS = {
    "bge-m3-zeroshot-c": "MIT, solo datos comerciales: destilable",
    "bge-m3-zeroshot": "MIT, pero con ANLI/WANLI/LingNLI (licencia mixta): solo de referencia",
}
PRECIO_H = 0.20   # c6a.2xlarge spot, estimación conservadora en USD/h


def _v(x):
    return "-" if x is None else f"{x:.3f}".replace(".", ",")


def valor(res, c):
    r = (res or {}).get("conjuntos", {}).get(c)
    return None if not r else r[MET.get(c, "macro_f1")]


def veredicto(res):
    j = valor(res, "jevbench")
    mejoras = [c for c in NO_VISTAS if valor(res, c) is not None and valor(res, c) - G8[c] >= SALTO]
    ok = j is not None and j >= UMBRAL_JEV and len(mejoras) >= 2
    return ok, j, mejoras


def informe(resultados, minutos=None, precio_h=PRECIO_H, licencias=None):
    lic = {**LICENCIAS, **(licencias or {})}
    cab = ["fila", "licencia", "JevBench (exact.)", "massive", "hatecheck", "inyecciones", "tasksource apartado", "ms/caso CPU (medio)"]
    L = ["# G.9 Techo del profesor zero-shot (CPU, c6a.2xlarge spot)", "",
         "JevBench en exactitud (231 casos, sin soporte); tareas no vistas en macro-F1 (≤ 300 filas por tarea, `profesor preparar`).", "",
         "| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    for n, res in resultados.items():
        ms = [r["ms_medio"] for r in res["conjuntos"].values() if r.get("ms_medio") is not None]
        L.append("| " + " | ".join([f"profesor {n} (plantilla {res['plantilla']})", lic.get(n, "?")] +
                                    [_v(valor(res, c)) for c in ("jevbench",) + NO_VISTAS] + [f"{sum(ms) / len(ms):.0f}" if ms else "-"]) + " |")
    L.append("| " + " | ".join(["G.8 corrida 2 (L2 sobre e5-small, 12.000 pasos)", "propia"] + [_v(G8[c]) for c in ("jevbench",) + NO_VISTAS] + ["-"]) + " |")
    L.append("| " + " | ".join(["T2.1b (L2; vio las tareas)", "propia"] + [_v(T21B[c]) for c in ("jevbench",) + NO_VISTAS] + ["-"]) + " |")
    L += ["", "Muestras: los conjuntos del profesor son ≤ 300 filas con hash estable y no son los mismos casos que G.8 (tasksource_fuera, allí 40 por tarea): "
          "la comparación es de orden de magnitud, no de décimas.", ""]
    res = resultados.get(PRINCIPAL)
    if res is None:
        L.append(f"**Veredicto: sin datos** (falta el modelo «{PRINCIPAL}»).")
    else:
        ok, j, mejoras = veredicto(res)
        L += [f"**Hipótesis (profesor «-c»):** JevBench sin soporte {_v(j)} (umbral {_v(UMBRAL_JEV)}) y mejora de ≥ +10 puntos de macro-F1 sobre G.8 en "
              f"{len(mejoras)} de 4 tareas no vistas ({', '.join(mejoras) or 'ninguna'}; hacen falta 2).", "",
              "**" + ("SE CUMPLE: destilar es el camino." if ok else "NO SE CUMPLE: el límite parece estar en los datos y no en el modelo.") + "**"]
    L += ["", "Etiqueta: choice y noul por argmax; score, la mediana CORAL de la distribución sobre los niveles (`metricas.top1`). "
          "Plantilla elegida en dev por modelo: " + "; ".join(f"{n}: {r['plantilla']} {r.get('dev_macro_f1') or ''}" for n, r in resultados.items()) + "."]
    if minutos is not None:
        L += ["", f"**Coste:** {minutos:.0f} min de instancia × {precio_h:.2f} USD/h ≈ {minutos / 60 * precio_h:.2f} USD (tope 0,5 USD; spot, estimado, más unos céntimos de disco y tráfico)."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("res")
    ap.add_argument("--minutos", type=float)
    ap.add_argument("--precio-h", type=float, default=PRECIO_H)
    ap.add_argument("--licencia", action="append", default=[])
    a = ap.parse_args(argv)
    resultados = {}
    for p in sorted(Path(a.res).glob("*/resultados.json"), key=lambda p: (p.parent.name != PRINCIPAL, p.parent.name)):
        resultados[p.parent.name] = json.loads(p.read_text(encoding="utf-8"))
    if not resultados:
        print("error: sin resultados.json", file=sys.stderr)
        return 2
    txt = informe(resultados, a.minutos, a.precio_h, dict(x.partition("=")[::2] for x in a.licencia))
    (Path(a.res) / "informe.md").write_text(txt, encoding="utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
