#!/usr/bin/env python3
"""T4.6c: prepara las filas de validación de `chispa train --validacion` para una tarea. Solo biblioteca estándar.

  validacion.py --dir DIR --esquema DIR/esquema.json [--dev dev.jsonl] [--frac 0.2] [--semilla 1]

Con --dev y filas de la tarea (campo `tarea` = id del esquema): escribe DIR/validacion.jsonl (texto, etiqueta) y no toca el train.
Sin ellas (o sin --dev): reserva --frac del train; escribe DIR/ejemplos-entrenar.jsonl y DIR/validacion.jsonl, uno por línea,
con el reparto estratificado por etiqueta y determinista. Imprime «dev» o «reservado» y el tamaño."""
import argparse
import json
import random
from pathlib import Path


def leer(ruta):
    return [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]


def escribir(ruta, filas):
    with open(ruta, "w", encoding="utf-8") as f:
        for r in filas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def reservar(filas, frac, semilla):
    """-> (entrenar, validación): `frac` de cada etiqueta (al menos 1, y deja al menos 1 en train si la etiqueta tiene 2+)."""
    por = {}
    for r in filas:
        por.setdefault(r["etiqueta"], []).append(r)
    ent, val = [], []
    for e in sorted(por):
        g = por[e][:]
        random.Random(f"{semilla}:{e}").shuffle(g)
        k = min(max(1, round(frac * len(g))), len(g) - 1) if len(g) > 1 else 0
        val += g[:k]
        ent += g[k:]
    return ent, val


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", required=True)
    ap.add_argument("--esquema", required=True)
    ap.add_argument("--dev")
    ap.add_argument("--frac", type=float, default=0.2)
    ap.add_argument("--semilla", type=int, default=1)
    a = ap.parse_args(argv)
    d = Path(a.dir)
    tid = json.loads(Path(a.esquema).read_text(encoding="utf-8"))["id"]
    dev = [r for r in leer(a.dev) if r.get("tarea") == tid] if a.dev and Path(a.dev).is_file() else []
    if dev:
        escribir(d / "validacion.jsonl", [{"texto": r["texto"], "etiqueta": r["etiqueta"]} for r in dev])
        print(f"dev {len(dev)}")
        return 0
    ent, val = reservar(leer(d / "ejemplos.jsonl"), a.frac, a.semilla)
    escribir(d / "ejemplos-entrenar.jsonl", ent)
    escribir(d / "validacion.jsonl", val)
    print(f"reservado {len(val)} de {len(ent) + len(val)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
