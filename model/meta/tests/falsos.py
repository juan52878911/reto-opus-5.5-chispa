"""Fuentes inventadas (sin datos reales) con la forma de las cuatro de metaentrenamiento, en una caché HF falsa."""
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def snap(hub, repo):
    d = Path(hub) / "hub" / ("datasets--" + repo.replace("/", "--")) / "snapshots" / "abc123"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tarjeta(d, licencia, cuerpo=""):
    (d / "README.md").write_text("---\nlicense: %s\n---\n# inventado\n%s\n" % (licencia, cuerpo), encoding="utf-8")


def parquet(ruta, filas):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(filas), ruta)


def fila_ts(i, source="demo/colores", uso="commercial", kind="choice", **kw):
    f = {"state": "Texto inventado número %d." % i, "question": "¿Cuál es el color?", "kind": kind,
         "options": ["rojo", "verde", "azul"], "target": [0.2, 0.7, 0.1], "source": source,
         "license": "mit", "license_use": uso}
    if kind == "noul":
        f.update(options=[], target=[0.8], question="El cielo es azul.")
    if kind == "score":
        f.update(options=["muy mal", "mal", "bien", "muy bien"], target=[0.0, 0.1, 0.3, 0.6])
    f.update(kw)
    return f


def yaml_ts(d, fichas):
    """fichas: {tarea: (dataset, license_use, license)}"""
    lineas = ["repo_id: x/y", "sources:"]
    for t, (ds, uso, lic) in fichas.items():
        lineas += ["  %s:" % t, "    rows:", "      train: 5", "    dataset: %s" % ds, "    license: %s" % lic,
                   "    license_use: %s" % uso]
    (d / "sources.yaml").write_text("\n".join(lineas) + "\n", encoding="utf-8")


def tasksource(hub, filas_train, fichas, filas_val=(), filas_test=()):
    d = snap(hub, "tasksource/tasksource-jev-typed-decisions")
    parquet(d / "data" / "train-00000-of-00001.parquet", list(filas_train))
    if filas_val:
        parquet(d / "data" / "validation-00000-of-00001.parquet", list(filas_val))
    if filas_test:
        parquet(d / "data" / "test-00000-of-00001.parquet", list(filas_test))
    yaml_ts(d, fichas)
    return d


def synthetic(hub, licencia="apache-2.0", n_textos=40):
    d = snap(hub, "MoritzLaurer/synthetic_zeroshot_mixtral_v0.1")
    tarjeta(d, licencia)
    filas = []
    for i in range(n_textos):
        for j, h in enumerate(("Habla de gatos.", "Habla de perros.")):
            filas.append({"hypothesis": h, "text": "Texto sintético %d" % i, "labels": j})
    parquet(d / "mixtral_refinedweb_categories" / "train-00000-of-00001.parquet", filas)
    parquet(d / "mixtral_written_texts_for_tasks_v2" / "train-00000-of-00001.parquet",
            [dict(f, text=f["text"] + " v2", extra="x") for f in filas[:10]])
    return d


def pawsx(hub, licencia="other", cuerpo="The dataset may be freely used for any purpose, although ..."):
    d = snap(hub, "google-research-datasets/paws-x")
    tarjeta(d, licencia, cuerpo)
    for nombre, n in (("train", 6), ("validation", 3), ("test", 3)):
        parquet(d / "es" / ("%s-00000-of-00001.parquet" % nombre),
                [{"id": i, "sentence1": "Frase uno %d." % i, "sentence2": "Frase dos %d." % i, "label": i % 2}
                 for i in range(n)])
    return d


def sib200(hub, licencia="cc-by-sa-4.0"):
    d = snap(hub, "Davlan/sib200")
    tarjeta(d, licencia)
    carpeta = d / "data" / "spa_Latn"
    carpeta.mkdir(parents=True, exist_ok=True)
    cats = ["science/technology", "travel", "politics", "sports", "health", "entertainment", "geography"]
    (carpeta / "labels.txt").write_text("\n".join(cats) + "\n", encoding="utf-8")
    for nombre, n in (("train", 14), ("dev", 7), ("test", 7)):
        lineas = ["index_id\tcategory\ttext"]
        for i in range(n):
            lineas.append('%d\t%s\tEl texto "%d" habla de cosas.' % (i, cats[i % 7], i))
        (carpeta / (nombre + ".tsv")).write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return d


def instruct(hub, filas_train, filas_val=()):
    """tasksource-instruct-v0 inventado: columnas inputs, targets, task."""
    d = snap(hub, "tasksource/tasksource-instruct-v0")
    parquet(d / "data" / "train-00000-of-00001.parquet", list(filas_train))
    if filas_val:
        parquet(d / "data" / "validation-00000-of-00001.parquet", list(filas_val))
    return d


def fila_inst(i, task="demo/sentimiento", clases=("negativo", "positivo", "neutro")):
    return {"inputs": "Opinión inventada número %d." % i, "targets": clases[i % len(clases)], "task": task}
