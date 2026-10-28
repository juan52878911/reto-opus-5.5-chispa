"""Cabeza por tarea sobre el L1: prototipos por clase más una capa lineal pequeña, entrenada con KL.

    python -m model.l1.cabeza --modelo X.chispa-l1 --tarea massive [--maestro l0|<jsonl {id, probs}>] --salida DIR

logits = a·cos(x, P_c) + W x + b, con P inicializado en los prototipos (media de los vectores del soporte), W = 0,
a = 20. Pérdida: KL(maestro || softmax(logits)) sobre el soporte de la tarea (32 por clase del train, el mismo que
usan las líneas base). Maestros:
  l0        distribuciones de L0 (TF-IDF de caracteres + regresión logística) fuera de pliegue, k = 5, con
            `model.lineas_base.correr.correr_l0`;
  <jsonl>   una línea `{"id": <id de fila del soporte>, "probs": {opción: prob}}` por fila del soporte (así se
            enchufan las distribuciones de L2 con soporte, que se calculan fuera: aquí no hay GPU ni S3).
La cabeza se exporta cuantizada: P y W en int8 con una escala por fila, `b` y `a` en float32 (`cabeza-<tarea>.npz`);
`predecir` usa los pesos ya descuantizados, igual que lo que se desplegaría.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

from . import comun

PASOS, LR, L2, A0 = 300, 0.02, 1e-3, 20.0


def maestro_l0(sop, ops, k=5, semilla=0):
    """Distribuciones de L0 fuera de pliegue (k pliegues estratificados por clase) sobre las filas del soporte."""
    from model.lineas_base import correr
    filas = [r for _, r in sop]
    por_clase = {}
    for i, r in enumerate(filas):
        por_clase.setdefault(r["etiqueta"], []).append(i)
    rng = np.random.RandomState(semilla)
    pliegue = np.zeros(len(filas), dtype=int)
    for c in sorted(por_clase):
        idx = np.array(por_clase[c])
        rng.shuffle(idx)
        pliegue[idx] = np.arange(len(idx)) % k
    probs = np.zeros((len(filas), len(ops)))
    for f in range(k):
        ent = [(i, r) for (i, r), p in zip(sop, pliegue) if p != f]
        fuera = [i for i in range(len(filas)) if pliegue[i] == f]
        p, _ = correr.correr_l0(ent, [filas[i] for i in fuera], ops)
        probs[fuera] = np.array(p)
    return probs


def maestro_jsonl(ruta, sop, ops):
    por_id = {m["id"]: m["probs"] for m in comun.leer(ruta)}
    faltan = [r["id"] for _, r in sop if r["id"] not in por_id]
    if faltan:
        raise SystemExit("al maestro le faltan %d ids del soporte (p. ej. %s)" % (len(faltan), faltan[0]))
    p = np.array([[por_id[r["id"]].get(o, 0.0) for o in ops] for _, r in sop])
    return p / p.sum(axis=1, keepdims=True)


def entrenar(x, y_idx, maestro, ops_n, pasos=PASOS, lr=LR, l2=L2, semilla=0):
    """x: n × d unitarios; maestro: n × C. -> dict con P, W, b, a (float32)."""
    import torch
    torch.manual_seed(semilla)
    torch.set_num_threads(2)
    X = torch.tensor(x, dtype=torch.float32)
    T = torch.tensor(maestro, dtype=torch.float32).clamp_min(1e-8)
    T = T / T.sum(dim=1, keepdim=True)
    protos = np.zeros((ops_n, x.shape[1]), dtype=np.float32)
    for c in range(ops_n):
        m = y_idx == c
        if m.any():
            v = x[m].mean(axis=0)
            protos[c] = v / (np.linalg.norm(v) + 1e-12)
    P = torch.nn.Parameter(torch.tensor(protos))
    W = torch.nn.Parameter(torch.zeros(ops_n, x.shape[1]))
    b = torch.nn.Parameter(torch.zeros(ops_n))
    la = torch.nn.Parameter(torch.tensor(float(np.log(A0))))
    opt = torch.optim.Adam([P, W, b, la], lr=lr)
    for _ in range(pasos):
        opt.zero_grad()
        lg = la.exp() * (X @ torch.nn.functional.normalize(P, dim=1).T) + X @ W.T + b
        kl = (T * (T.log() - torch.log_softmax(lg, dim=1))).sum(dim=1).mean()
        (kl + l2 * (W ** 2).sum()).backward()
        opt.step()
    return {"P": P.detach().numpy(), "W": W.detach().numpy(), "b": b.detach().numpy(), "a": np.float32(la.exp().item())}


def cuantizar(m):
    """P y W a int8 con escala por fila (max|fila|/127), como los pesos de L1; b y a siguen en float32."""
    out = {"b": m["b"].astype(np.float32), "a": np.float32(m["a"])}
    for k in ("P", "W"):
        esc = (np.abs(m[k]).max(axis=1) / 127).astype(np.float32)
        seguro = np.where(esc > 0, esc, 1)
        out[k + "_q"] = np.clip(np.rint(m[k] / seguro[:, None]), -127, 127).astype(np.int8)
        out[k + "_esc"] = esc
    return out


def descuantizar(q):
    return {"P": q["P_q"].astype(np.float32) * q["P_esc"][:, None], "W": q["W_q"].astype(np.float32) * q["W_esc"][:, None],
            "b": q["b"], "a": q["a"]}


def logits(m, x):
    P = m["P"] / (np.linalg.norm(m["P"], axis=1, keepdims=True) + 1e-12)
    return float(m["a"]) * (x @ P.T) + x @ m["W"].T + m["b"]


def softmax(z):
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--modelo", required=True, help=".chispa-l1 (el de dims = --dim)")
    ap.add_argument("--dim", type=int, default=256)
    ap.add_argument("--tarea", required=True, choices=comun.TAREAS)
    ap.add_argument("--maestro", default="l0", help="`l0` o jsonl {id, probs} sobre el soporte")
    ap.add_argument("--datos", default=comun.DATOS)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    from model.lineas_base import correr
    train, _, test = correr.cargar(a.tarea, a.datos)
    ops = test[0]["opciones"]
    sop = correr.soporte(train)
    maestro = maestro_l0(sop, ops) if a.maestro == "l0" else maestro_jsonl(a.maestro, sop, ops)
    x = comun.embeber(a.modelo, [r["texto"] for _, r in sop], a.dim)
    y = np.array([ops.index(r["etiqueta"]) for _, r in sop])
    q = cuantizar(entrenar(x, y, maestro, len(ops)))
    Path(a.salida).mkdir(parents=True, exist_ok=True)
    ruta = Path(a.salida) / ("cabeza-%s.npz" % a.tarea)
    np.savez(ruta, **q)
    print(ruta, ruta.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
