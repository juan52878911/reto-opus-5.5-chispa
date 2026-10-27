"""Muestra estratificada por clase del test de cada tarea, para etiquetar a mano.

Uso: python -m model.etiquetado.preparar --entrada a.jsonl b.jsonl --por-tarea 300 --semilla 7 --salida m.jsonl
"""
import argparse
import json
import random
import sys
from collections import defaultdict


def leer(rutas):
    filas = []
    for ruta in rutas:
        with open(ruta, encoding="utf-8") as f:
            for linea in f:
                if linea.strip():
                    filas.append(json.loads(linea))
    return filas


def estratificar(filas, n, rng):
    """n filas repartidas a partes iguales entre clases; lo que sobra de una clase pequeña va a las demás."""
    clases = defaultdict(list)
    for f in filas:
        clases[f["etiqueta"]].append(f)
    for c in clases.values():
        c.sort(key=lambda f: f["id"])
        rng.shuffle(c)
    elegidas = []
    activas = sorted(clases)
    resto = min(n, len(filas))
    while resto > 0 and activas:
        cuota = max(resto // len(activas), 1)
        siguientes = []
        for c in activas:
            toma = min(cuota, len(clases[c]), resto)
            elegidas.extend(clases[c][:toma])
            del clases[c][:toma]
            resto -= toma
            if clases[c]:
                siguientes.append(c)
        activas = siguientes
    return elegidas


def preparar(filas, por_tarea, semilla, incluir_no_comercial=False):
    por = defaultdict(list)
    for f in filas:
        if f.get("split") != "test":
            continue
        if f.get("uso_comercial") is False and not incluir_no_comercial:
            continue
        por[f["tarea"]].append(f)
    salida = []
    for tarea in sorted(por):
        rng = random.Random("%s:%s" % (semilla, tarea))
        salida.extend(sorted(estratificar(por[tarea], por_tarea, rng), key=lambda f: f["id"]))
    return salida


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--entrada", nargs="+", required=True)
    p.add_argument("--por-tarea", type=int, default=300)
    p.add_argument("--semilla", type=int, default=7)
    p.add_argument("--salida", required=True)
    p.add_argument("--incluir-no-comercial", action="store_true",
                   help="incluye filas con uso_comercial=false")
    a = p.parse_args(argv)
    muestra = preparar(leer(a.entrada), a.por_tarea, a.semilla, a.incluir_no_comercial)
    with open(a.salida, "w", encoding="utf-8") as f:
        for r in muestra:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    cuenta = defaultdict(int)
    for r in muestra:
        cuenta[r["tarea"]] += 1
    for t in sorted(cuenta):
        print("%s: %d" % (t, cuenta[t]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
