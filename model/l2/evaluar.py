"""Predicción y evaluación de L2 con `chispa eval`.

    python -m model.l2.evaluar --ckpt mejor.pt --salida DIR [--datos DIR_CONVERTIDOS] [--liston DIR] [--extra nombre=ruta.jsonl]

Escribe `DIR/pred/<conjunto>.jsonl` (`{id, probs, ms}`), `DIR/resultados.json` y `DIR/delta.md` (Δ de macro-F1 por tarea frente
al kNN-32 y L0 de `model/lineas_base/resultados.json`). `ms` es el tiempo del lote repartido entre sus filas (no latencia
de una consulta suelta).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import torch

from model.evaluacion import chispa_eval as CE

from . import datos as D
from .modelo import Codificador, ModeloL2

RAIZ = Path(__file__).resolve().parents[2]
LB = RAIZ / "model" / "lineas_base" / "resultados.json"
TEST_T17A = ("massive", "hatecheck", "clinc150", "inyecciones")


@torch.no_grad()
def predecir(modelo, enc, filas, lote=64):
    modelo.eval()
    out = []
    for i in range(0, len(filas), lote):
        fs = filas[i:i + lote]
        t0 = time.perf_counter()
        probs, _ = modelo(fs, enc, entrenar=False)
        ms = (time.perf_counter() - t0) * 1000 / len(fs)
        for r, p in zip(fs, probs):
            p = p.double().cpu()
            p = (p / p.sum()).tolist()
            out.append({"id": r["id"], "probs": dict(zip(r["opciones"], p)), "ms": round(ms, 3)})
    return out


def macro_f1_medio(filas, preds):
    por = CE.evaluar(filas, preds)["por_tarea"]
    return sum(m["macro_f1"] for m in por.values()) / max(len(por), 1), por


def cargar_modelo(ruta, device="cpu"):
    ck = torch.load(ruta, map_location=device, weights_only=False)
    m = ModeloL2().to(device)
    for k in ck.get("cabezas", []):
        m.asegurar_cabeza(k, device)
    m.load_state_dict(ck["modelo"])
    return m.eval(), ck


def conjuntos_test(datos=None, liston=None, extra=()):
    """{nombre: filas test}: T1.7a (datos convertidos), T1.4 (herramientas) y el listón."""
    out = {}
    for t in TEST_T17A:
        if datos and (Path(datos) / (t + ".jsonl")).exists():
            out[t] = D.leer(str(Path(datos) / (t + ".jsonl")), split="test")
    h = RAIZ / "model" / "herramientas" / "test.jsonl"
    if h.exists():
        out["herramientas"] = D.leer(str(h), split="test")
    if liston:
        for f in sorted(Path(liston).glob("*.jsonl")):
            out["liston_" + f.stem] = D.leer(str(f), split="test")
    for e in extra:
        n, _, r = e.partition("=")
        out[n] = D.leer(r, split="test")
    return {k: v for k, v in out.items() if v}


def tabla_delta(res):
    with open(LB) as f:
        base = json.load(f)
    lin = ["| conjunto | n | L2 macro-F1 | e5 kNN-32 | Δ vs kNN-32 | L0 | Δ vs L0 | L2 ECE | kNN-32 ECE |", "|" + "---|" * 9]
    ganadas = 0
    for nombre, r in res.items():
        g = r["global"]
        b = base.get(nombre, {})
        k, l0 = (b.get("e5_knn32") or {}).get("global", b.get("e5_knn32")), (b.get("l0_tfidf_lr") or {}).get("global", b.get("l0_tfidf_lr"))
        f = lambda x, c: x[c] if isinstance(x, dict) and x.get(c) is not None else None
        mk, ml = f(k, "macro_f1"), f(l0, "macro_f1")
        d = lambda a, c: "-" if c is None else "%+.3f" % (a - c)
        v = lambda x: "-" if x is None else "%.3f" % x
        ganadas += mk is not None and g["macro_f1"] - mk >= 0.05
        lin.append("| %s | %d | %.3f | %s | %s | %s | %s | %.3f | %s |" % (
            nombre, g["n"], g["macro_f1"], v(mk), d(g["macro_f1"], mk), v(ml), d(g["macro_f1"], ml), g["ece"], v(f(k, "ece"))))
    lin += ["", "T2.1 (≥ +0,05 de macro-F1 sobre kNN-32 en ≥ 3 tareas): %d tareas con Δ ≥ 0,05." % ganadas]
    return "\n".join(lin)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--datos", help="directorio de model.datos.convertir")
    ap.add_argument("--liston")
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--max-filas", type=int, default=0, help="tope de filas por conjunto (0 = todas)")
    a = ap.parse_args(argv)
    sal = Path(a.salida)
    (sal / "pred").mkdir(parents=True, exist_ok=True)
    modelo, ck = cargar_modelo(a.ckpt, a.device)
    enc = Codificador(device=a.device)
    res = {}
    for nombre, filas in conjuntos_test(a.datos, a.liston, a.extra).items():
        if a.max_filas:
            filas = filas[:a.max_filas]
        filas = CE.asignar_ids(filas, nombre) if any("id" not in r for r in filas) else filas
        preds = predecir(modelo, enc, filas)
        with open(sal / "pred" / (nombre + ".jsonl"), "w", encoding="utf-8") as f:
            for p in preds:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        res[nombre] = CE.evaluar(filas, preds)
        print("== %s\n%s" % (nombre, CE.tabla(res[nombre])), flush=True)
    with open(sal / "resultados.json", "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    t = tabla_delta(res)
    (sal / "delta.md").write_text(t + "\n", encoding="utf-8")
    print(t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
