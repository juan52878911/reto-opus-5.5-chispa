"""Datos de la prueba G.7: filas para calibrar la torre estática y un dev con una tarea `score` de K ≥ 3 niveles.

    python -m model.bench.torre.datos_g7 calib SALIDA.jsonl [--train FICHERO.jsonl[.gz]…] [--n 500]
    python -m model.bench.torre.datos_g7 dev SALIDA.jsonl --jevbench RUTA

calib: filas `train` cuyos `texto_opcion` calibran las activaciones int8. Con `--train` (filas de train reales) las copia; sin él, usa
las intenciones de massive-es (split train del dataset) con redacciones de la pregunta distintas de las que mide la paridad
(`exportar.textos_golden`), para no calibrar con los mismos textos que se miden.
dev: todas las filas de JevBench como `split=dev` (calibrar.py, y las torres del .chispa), para que la calibración lleve
las cabezas `scoreK` de las tareas score. Falla si no hay ninguna con K ≥ 3.
"""
import argparse
import json
import sys
from pathlib import Path

PREGUNTAS_CALIB = ("¿Cuál es la intención del mensaje?", "Indica qué quiere conseguir el usuario con su mensaje.",
                   "Clasifica la solicitud en una de las intenciones.", "¿Qué le está pidiendo el usuario al asistente?",
                   "Elige la categoría que corresponde a esta orden.", "¿Para qué sirve este mensaje?",
                   "Determina el tipo de acción que solicita la persona.", "¿Qué tarea doméstica o de consulta se menciona?",
                   "Etiqueta el mensaje con la intención adecuada.", "¿Qué intención tiene la frase?")


def filas_calib_massive(n):
    from model.datos.massive import DESCRIPCIONES
    ops = sorted(DESCRIPCIONES)
    filas = []
    for i, q in enumerate(PREGUNTAS_CALIB):
        for j in range(0, len(ops), 8):
            o = ops[j:j + 8]
            filas.append({"id": "calib:%d:%d" % (i, j), "tarea": "massive", "tipo": "choice", "split": "train", "pregunta": q, "texto": "",
                          "opciones": o, "descripciones": {x: DESCRIPCIONES[x] for x in o}, "etiqueta": o[0]})
    return filas


def filas_dev(jevbench):
    from model.evaluacion.jevbench import cargar_jevbench
    filas = [{**r, "split": "dev"} for r in cargar_jevbench(jevbench)]
    k = sorted({len(r["opciones"]) for r in filas if r["tipo"] == "score"})
    if not k or max(k) < 3:
        raise SystemExit("JevBench no trae ninguna tarea score de 3 o más niveles (K vistos: %s)" % k)
    return filas


def escribir(filas, ruta):
    Path(ruta).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in filas), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("que", choices=("calib", "dev"))
    ap.add_argument("salida")
    ap.add_argument("--train", nargs="*", default=[])
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--jevbench")
    a = ap.parse_args(argv)
    if a.que == "calib":
        if a.train:
            from model.l2 import datos as D
            filas = [r for r in D.leer(a.train) if r["split"] == "train"]
        else:
            filas = filas_calib_massive(a.n)
    else:
        if not a.jevbench:
            ap.error("dev pide --jevbench")
        filas = filas_dev(a.jevbench)
    escribir(filas, a.salida)
    print("%s: %d filas en %s" % (a.que, len(filas), a.salida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
