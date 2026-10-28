#!/usr/bin/env python3
"""Solo para la prueba en seco de aws.sh (CHISPA_LOCAL=1): fabrica un cvtest/pred/ INVENTADO con la forma de T2.2d.

  curvas_fixture.py --datos DIR_CONVERTIDOS --herramientas test.jsonl --salida DIR
Por cada tarea, una predicción por fila de test con la etiqueta verdadera acertada con probabilidad creciente en la confianza.
"""
import argparse
import json
import random
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True)
    ap.add_argument("--herramientas", required=True)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    fuentes = {"massive": Path(a.datos) / "massive.jsonl", "hatecheck": Path(a.datos) / "hatecheck.jsonl", "herramientas": Path(a.herramientas)}
    rng = random.Random(0)
    out = Path(a.salida) / "cvtest" / "pred"
    out.mkdir(parents=True, exist_ok=True)
    for t, ruta in fuentes.items():
        filas = [r for r in map(json.loads, open(ruta, encoding="utf-8")) if r.get("split", "test") == "test"]
        with open(out / f"{t}.jsonl", "w", encoding="utf-8") as f:
            for r in filas:
                ops, conf = r["opciones"], rng.random() ** 0.5
                top = r["etiqueta"] if rng.random() < 0.4 + 0.6 * conf else rng.choice(ops)
                resto = (1 - conf) / max(len(ops) - 1, 1)
                f.write(json.dumps({"id": r["id"], "probs": {o: (conf if o == top else resto) for o in ops}, "ms": 1.0}) + "\n")
        print(t, len(filas))


if __name__ == "__main__":
    main()
