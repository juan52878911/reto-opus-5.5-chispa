"""Genera catalogo.json, train.jsonl y test.jsonl desde datos.py (determinista).

Uso: python model/herramientas/construir.py
"""
import json
import os
import random
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import datos  # noqa: E402

PREGUNTA = "¿Qué herramienta o agente debe usar para atender esta petición?"
DESC_ESC = "Ninguna sirve o la petición es ambigua: preguntar a la persona qué quiere."
LICENCIA = dict(licencia="propia (Chispa)", uso_comercial=True, fuente="chispa T1.4")


def catalogo():
    c = [{"id": i, "tipo": t, "descripcion": d} for i, (t, d, _) in datos.H.items()]
    c.append({"id": "escalate", "tipo": "herramienta", "descripcion": DESC_ESC})
    return c


def fila(cat, n, split, texto, etiqueta, plantilla, idioma):
    return {
        "id": f"herr:{split}:{n}", "tarea": "herramientas", "tipo": "choice", "pregunta": PREGUNTA,
        "texto": texto, "opciones": [x["id"] for x in cat],
        "descripciones": {x["id"]: x["descripcion"] for x in cat},
        "etiqueta": etiqueta, "idioma": idioma, "split": split, **LICENCIA, "plantilla": plantilla,
    }


def idioma(t):
    return ("es-CO", t[1:]) if t.startswith("~") else ("es", t)


def train(cat):
    out = []
    for i, (plantillas, rellenos) in datos.TRAIN.items():
        for r in rellenos:  # relleno-mayor: los 8 primeros por clase ya cubren las 4 plantillas
            for j, p in enumerate(plantillas):
                out.append((p.format(x=r), i, f"{i}-p{j}", "es"))
    esc = list(datos.ESC_TRAIN)
    random.Random(0).shuffle(esc)
    out += [(t, "escalate", f"escalate-t{n}", "es") for n, t in enumerate(esc)]
    return [fila(cat, n, "train", *a[:3], idioma=a[3]) for n, a in enumerate(out)]


def test(cat):
    out = []
    for i, (_, _, casos) in datos.H.items():
        for n, t in enumerate(casos):
            out.append((t, i, f"man-{i}-{n}"))
    out += [(t, "escalate", f"man-escalate-{n}") for n, t in enumerate(datos.ESC_TEST)]
    filas = []
    for n, (t, e, p) in enumerate(out):
        lang, t = idioma(t)
        filas.append(fila(cat, n, "test", t.strip(), e, p, lang))
    return filas


def escribir(ruta, filas):
    with open(ruta, "w", encoding="utf-8") as f:
        for r in filas:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


if __name__ == "__main__":
    cat = catalogo()
    with open(os.path.join(AQUI, "catalogo.json"), "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=1)
        f.write("\n")
    escribir(os.path.join(AQUI, "train.jsonl"), train(cat))
    escribir(os.path.join(AQUI, "test.jsonl"), test(cat))
    print(len(cat), "entradas;", len(train(cat)), "train;", len(test(cat)), "test")
