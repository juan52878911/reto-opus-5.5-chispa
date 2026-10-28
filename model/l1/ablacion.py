"""Ablación de la ponderación SIF del L1 propio (256 dim): macro-F1 de zs y proto por tarea.

    python -m model.l1.ablacion --sif 1e-3 1e-5 1e6 --salida /tmp/l1abl

Reutiliza los vectores crudos de e5 que dejó `destilar` en /tmp/l1propio/crudo.npy (sif = 1e6 ≈ sin ponderar).
"""
import argparse
import json
from pathlib import Path

import numpy as np

from . import comun, destilar, evaluar


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sif", type=float, nargs="+", required=True)
    ap.add_argument("--salida", default="/tmp/l1abl")
    ap.add_argument("--cache", default="/tmp/l1propio/crudo.npy")
    a = ap.parse_args(argv)
    from model.lineas_base import correr
    ids = json.loads((comun.RAIZ / "model/bench/vocab-podado-e5-small.json").read_text())["ids_originales"]
    res = {}
    for sif in a.sif:
        ruta = destilar.destilar(comun.snapshot("intfloat/multilingual-e5-small"), ids, 256, "%s/sif%g" % (a.salida, sif), sif,
                                 cache=a.cache)
        for tarea in comun.TAREAS:
            train, _, test = correr.cargar(tarea, comun.DATOS)
            ops, sop = test[0]["opciones"], correr.soporte(train)
            r = evaluar.tarea_modelo("abl", ruta, 256, tarea, train, test, sop, ops, None, False, "/tmp/l1eval")
            res.setdefault(str(sif), {})[tarea] = r
        for k in ("zs", "proto"):
            print("sif=%g %s media %.3f" % (sif, k, np.mean([res[str(sif)][t][k] for t in comun.TAREAS])), flush=True)
    Path(a.salida, "ablacion.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
