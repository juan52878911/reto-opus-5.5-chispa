"""Comprueba que L1-zs en Python (`capas.l1_zs`) da el mismo top-1 que `runtime/l1` (Go) en N frases.

    python -m model.cascada.verificar_l1 --datos DIR [--n 50] [--l1 /tmp/potion.chispa-l1]

Exporta el modelo con `runtime/l1/exportar.py` si falta el `.chispa-l1`, y corre `model/cascada/verificar_l1` (Go).
Las frases salen de las 5 tareas, repartidas por igual, con semilla fija. Termina con código 1 si algún top-1 difiere.
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
from pathlib import Path

from . import capas as C


def frases(datos, n, semilla=0):
    rng = random.Random(semilla)
    por = max(1, n // len(C.TAREAS))
    out = []
    for t in C.TAREAS:
        test = C.cargar_tarea(t, datos)[2]
        out += rng.sample(test, min(por, len(test)))
    return out[:n]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--l1", default="/tmp/potion.chispa-l1")
    a = ap.parse_args(argv)
    if not Path(a.l1).exists():
        subprocess.run([sys.executable, str(C.RAIZ / "runtime" / "l1" / "exportar.py"), C.resolver_potion(), a.l1], check=True)
    rows = frases(a.datos, a.n)
    casos = "".join(json.dumps({"mensaje": r["texto"], "opciones": [C.texto_opcion(r, o) for o in r["opciones"]]},
                               ensure_ascii=False) + "\n" for r in rows)
    go = os.environ.get("GO", str(Path.home() / "go-sdk" / "bin" / "go"))
    env = {**os.environ, "GOTOOLCHAIN": "local", "GOFLAGS": "-mod=mod"}
    p = subprocess.run([go, "run", ".", a.l1], cwd=C.AQUI / "verificar_l1", input=casos, capture_output=True, text=True, env=env)
    if p.returncode:
        sys.exit("go falló: " + p.stderr[-800:])
    m = C.cargar_potion()
    py = C.l1_zs(m, rows)
    mal = 0
    for r, linea in zip(rows, p.stdout.splitlines()):
        g = json.loads(linea)
        pr = py[r["id"]]["probs"]
        t = r["opciones"].index(max(pr, key=pr.get))
        if r["tipo"] == "noul":   # l1.go: solo cuenta el coseno de «true», σ(A·cos+B) ≥ θ; el argmax de los dos cosenos no vale
            z = C.NOUL_A * g["cos"][r["opciones"].index("true")] + C.NOUL_B
            g = r["opciones"].index("true" if 1 / (1 + math.exp(-z)) >= C.NOUL_THETA else "false")
        else:
            g = g["top1"]
        if t != g:
            mal += 1
            print("difiere", r["id"], "python", r["opciones"][t], "go", r["opciones"][g])
    print("frases: %d, top-1 distintos: %d" % (len(rows), mal))
    sys.exit(1 if mal else 0)


if __name__ == "__main__":
    main()
