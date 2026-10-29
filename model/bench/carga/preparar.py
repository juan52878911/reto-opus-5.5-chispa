"""Prepara datos de la prueba de carga: MASSIVE es (de ~/hf) → ejemplos.csv, mensajes.txt y esquema.json.

La pregunta y las opciones son las que `server/cmd/carga` manda fijas (compra/queja/saludo/soporte), para que el
generador sin cambiar case con el esquema del modelo. Las 60 intenciones de MASSIVE se agrupan por escenario en esas 4
opciones (agrupación inventada, solo sirve para la carga: la latencia no depende de ella).

    python preparar.py DIR_SALIDA [--por-clase 200]
"""
import argparse
import csv
import glob
import gzip
import json
import os
import random

AGRUPA = {"compra": {"takeaway", "recommendation", "cooking", "play", "music"},
          "queja": {"alarm", "datetime", "lists", "calendar"},
          "saludo": {"general", "social", "qa"},
          "soporte": {"iot", "weather", "news", "email", "transport", "audio"}}
ESC = {e: o for o, es in AGRUPA.items() for e in es}


def leer(split):
    ruta = glob.glob(os.path.expanduser(f"~/hf/hub/datasets--mteb--amazon_massive_intent/snapshots/*/{split}/es.json.gz"))[0]
    with gzip.open(ruta, "rt", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("salida")
    ap.add_argument("--por-clase", type=int, default=200)
    ap.add_argument("--semilla", type=int, default=7)
    a = ap.parse_args()
    os.makedirs(a.salida, exist_ok=True)
    rnd = random.Random(a.semilla)
    por = {o: [] for o in AGRUPA}
    for r in leer("train"):
        esc = r["label_text"].split("_")[0]
        por[ESC[esc]].append(r["text"])
    filas = []
    for o, ts in por.items():
        rnd.shuffle(ts)
        filas += [(t, o) for t in ts[:a.por_clase]]
    rnd.shuffle(filas)
    with open(os.path.join(a.salida, "ejemplos.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["texto", "etiqueta"])
        w.writerows(filas)
    test = [r["text"] for r in leer("test")]
    rnd.shuffle(test)
    with open(os.path.join(a.salida, "mensajes.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(t.replace("\n", " ") for t in test[:2000]) + "\n")
    esquema = {"id": "carga", "pregunta": "¿Qué quiere hacer el cliente?", "tipo": "choice",
               "opciones": {"compra": "", "queja": "", "saludo": "", "soporte": ""}}
    json.dump(esquema, open(os.path.join(a.salida, "esquema.json"), "w"), ensure_ascii=False)
    print({o: len(v) for o, v in por.items()}, "ejemplos:", len(filas), "mensajes:", min(2000, len(test)))


main()
