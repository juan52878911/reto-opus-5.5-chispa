"""Evalúa el L1 propio frente a potion: macro-F1 por tarea, tamaño, p99 con runtime/l1 y coseno con e5-small.

    python -m model.l1.evaluar --propio 256=/tmp/l1propio/d256/propio-256.chispa-l1 128=... --potion /tmp/potion.chispa-l1

Sistemas por tarea (todos sobre el soporte de 32 por clase del train y el test de T2.2, métrica de `chispa eval`):
  zs      coseno entre el texto y «pregunta · opción · descripción» (argmax; softmax con T = 0,02 para las probs);
  proto   coseno contra el prototipo (media normalizada) de cada clase;
  cabeza  (solo L1 propio) `model.l1.cabeza` con L0 fuera de pliegue como maestro, pesos int8.
Coseno frente al maestro (2 274 frases del sondeo): el estático y e5 viven en espacios distintos, así que se
ajusta una regresión lineal (ridge) en dos mitades de las frases y se mide el coseno en la mitad no vista; además
la correlación de Spearman entre los cosenos de 5 000 pares al azar (sin ajuste).
"""
import argparse
import contextlib
import datetime
import io
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from . import cabeza as cab
from . import comun

TAU = 0.02


def textos_zs(fila):
    return ["%s · %s · %s" % (fila["pregunta"], o, fila["descripciones"].get(o, "")) for o in fila["opciones"]]


def proto_logits(xs, y, xt, n):
    P = np.stack([xs[y == c].mean(axis=0) if (y == c).any() else np.zeros(xs.shape[1]) for c in range(n)])
    P /= np.linalg.norm(P, axis=1, keepdims=True) + 1e-12
    return xt @ P.T


def macro_f1(test, probs, ops, tmp):
    from model.lineas_base import correr
    datos, pred = Path(tmp) / "t.jsonl", Path(tmp) / "p.jsonl"
    datos.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in test))
    correr.guardar_pred(pred, test, probs, [0.0] * len(test))
    with contextlib.redirect_stdout(io.StringIO()):
        return correr.evaluar(datos, pred)["macro_f1"]


def tarea_modelo(nombre, modelo, dim, tarea, train, test, sop, ops, maestro, con_cabeza, tmp):
    xs = comun.embeber(modelo, [r["texto"] for _, r in sop], dim)
    xt = comun.embeber(modelo, [r["texto"] for r in test], dim)
    y = np.array([ops.index(r["etiqueta"]) for _, r in sop])
    zs = comun.embeber(modelo, textos_zs(test[0]), dim)
    res = {"zs": macro_f1(test, cab.softmax(xt @ zs.T / TAU), ops, tmp),
           "proto": macro_f1(test, cab.softmax(proto_logits(xs, y, xt, len(ops)) / TAU), ops, tmp)}
    if con_cabeza:
        m = cab.cuantizar(cab.entrenar(xs, y, maestro, len(ops)))
        res["cabeza"] = macro_f1(test, cab.softmax(cab.logits(cab.descuantizar(m), xt)), ops, tmp)
    return res


def p99(modelo, n=2000):
    exe = Path("/tmp/l1medir")
    if not exe.exists():
        subprocess.run(["go", "build", "-o", str(exe), "chispa/runtime/l1/cmd/l1medir"], cwd=comun.AQUI / "go", check=True)
    sal = subprocess.run([str(exe), "-n", str(n), str(modelo)], capture_output=True, text=True, check=True).stdout
    return {int(m.group(1)): (m.group(2), m.group(3)) for m in
            re.finditer(r"tokens=\s*(\d+) \(pedido\s+\d+\)\s+p50=(\S+)\s+p99=(\S+)", sal)}, sal.splitlines()[0]


def coseno_maestro(modelo, dim, frases, teacher):
    x = comun.embeber(modelo, frases, dim).astype(np.float64)
    ok = (np.linalg.norm(x, axis=1) > 0)
    x, t = x[ok], teacher[ok].astype(np.float64)
    n = len(x)
    idx = np.random.RandomState(0).permutation(n)
    mitades = [idx[: n // 2], idx[n // 2:]]
    cos = []
    for a, b in (mitades, mitades[::-1]):
        W = np.linalg.solve(x[a].T @ x[a] + 1e-2 * np.eye(dim), x[a].T @ t[a])
        p = x[b] @ W
        cos.append((p * t[b]).sum(1) / (np.linalg.norm(p, axis=1) * np.linalg.norm(t[b], axis=1)))
    rng = np.random.RandomState(1)
    i, j = rng.randint(0, n, 5000), rng.randint(0, n, 5000)
    from scipy.stats import spearmanr
    rho = spearmanr((x[i] * x[j]).sum(1), (t[i] * t[j]).sum(1)).statistic
    return float(np.concatenate(cos).mean()), float(rho), int((~ok).sum())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--propio", nargs="+", required=True, help="DIMS=ruta.chispa-l1 (uno o más)")
    ap.add_argument("--potion", required=True)
    ap.add_argument("--tareas", default=",".join(comun.TAREAS))
    ap.add_argument("--datos", default=comun.DATOS)
    ap.add_argument("--maestro", default="l0")
    ap.add_argument("--n-lat", type=int, default=2000)
    ap.add_argument("--salida", default=None)
    a = ap.parse_args(argv)
    from model.lineas_base import correr
    modelos = [("potion", a.potion, 256, False)] + [("propio-" + s.split("=")[0], s.split("=")[1], int(s.split("=")[0]), True)
                                                  for s in a.propio]
    salida = Path(a.salida or comun.AQUI / "resultados" / datetime.date.today().isoformat())
    salida.mkdir(parents=True, exist_ok=True)
    tmp = Path("/tmp/l1eval")
    tmp.mkdir(exist_ok=True)
    res = {"f1": {}, "tamano": {}, "latencia": {}, "coseno": {}, "maestro": a.maestro}
    for tarea in a.tareas.split(","):
        train, _, test = correr.cargar(tarea, a.datos)
        ops, sop = test[0]["opciones"], correr.soporte(train)
        m = cab.maestro_l0(sop, ops) if a.maestro == "l0" else cab.maestro_jsonl(a.maestro, sop, ops)
        for nombre, ruta, dim, con in modelos:
            res["f1"].setdefault(tarea, {})[nombre] = tarea_modelo(nombre, ruta, dim, tarea, train, test, sop, ops, m, con, tmp)
        print(tarea, json.dumps(res["f1"][tarea]), flush=True)
    from sentence_transformers import SentenceTransformer
    enc = SentenceTransformer(comun.snapshot("intfloat/multilingual-e5-small"), device="cpu")
    frases = [r["texto"] for r in comun.leer(comun.RAIZ / "runtime/l1/testdata/ids_sondeo.jsonl")]
    teacher = enc.encode(["query: " + t for t in frases], normalize_embeddings=True, batch_size=32)
    for nombre, ruta, dim, _ in modelos:
        res["tamano"][nombre] = Path(ruta).stat().st_size
        res["latencia"][nombre], host = p99(ruta, a.n_lat)
        res["coseno"][nombre] = coseno_maestro(ruta, dim, frases, teacher)
        print(nombre, res["tamano"][nombre], res["latencia"][nombre], res["coseno"][nombre], flush=True)
    res["host"] = host
    (salida / "resultados.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print("->", salida / "resultados.json")


if __name__ == "__main__":
    main()
