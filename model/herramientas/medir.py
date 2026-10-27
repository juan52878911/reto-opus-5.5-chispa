"""e5-small (prefijo «query: ») + kNN sobre la tarea de herramientas.

Uso (desde la raíz del repo): python model/herramientas/medir.py [--salida DIR]
kNN-k = k ejemplos de train por clase (los k primeros de cada una). Peso por similitud:
softmax(sim / T) sobre los 10 vecinos más cercanos, como en model/eval0/e5_knn.py.
Escribe pred_knn{8,32}.jsonl (formato de predicciones del esquema) y medidas.json.
Provisional: se reemplaza por `chispa eval` al integrar.
"""
import argparse
import glob
import json
import os
import time

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
T, VECINOS = 0.05, 10


def leer(nombre):
    with open(os.path.join(AQUI, nombre), encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def codificador():
    from sentence_transformers import SentenceTransformer
    p = glob.glob(os.path.expanduser("~/hf/hub/models--intfloat--multilingual-e5-small/snapshots/*"))[0]
    return SentenceTransformer(p, device="cpu")


def embeber(m, filas):
    return m.encode(["query: " + r["texto"] for r in filas], normalize_embeddings=True, batch_size=32)


def predecir(xtr, ytr, xq, opciones):
    """Devuelve una lista de dicts opcion->prob, una por consulta."""
    out = []
    for q in xq:
        s = xtr @ q
        idx = np.argsort(-s)[:VECINOS]
        w = np.exp((s[idx] - s[idx].max()) / T)
        p = {o: 0.0 for o in opciones}
        for i, wi in zip(idx, w):
            p[str(ytr[i])] += float(wi)
        tot = sum(p.values())
        out.append({o: v / tot for o, v in p.items()})
    return out


def metricas(test, probs):
    from sklearn.metrics import f1_score, roc_auc_score
    ops = test[0]["opciones"]
    y = [r["etiqueta"] for r in test]
    pred = [max(p, key=p.get) for p in probs]
    esc = [int(e == "escalate") for e in y]
    return {
        "n": len(y),
        "macro_f1": float(f1_score(y, pred, labels=ops, average="macro", zero_division=0)),
        "exactitud": float(np.mean([a == b for a, b in zip(y, pred)])),
        "auroc_escalate": float(roc_auc_score(esc, [p["escalate"] for p in probs])),
        "auroc_escalate_1_menos_max_herramienta": float(
            roc_auc_score(esc, [1 - max(v for o, v in p.items() if o != "escalate") for p in probs])),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=AQUI)
    a = ap.parse_args()
    train, test = leer("train.jsonl"), leer("test.jsonl")
    m = codificador()
    xtr, xte = embeber(m, train), None
    t0 = time.perf_counter()
    xte = embeber(m, test)
    ms = (time.perf_counter() - t0) * 1000 / len(test)
    ops = test[0]["opciones"]
    res = {}
    for k in (8, 32):
        cuenta, sel = {}, []
        for i, r in enumerate(train):
            cuenta[r["etiqueta"]] = cuenta.get(r["etiqueta"], 0) + 1
            if cuenta[r["etiqueta"]] <= k:
                sel.append(i)
        ytr = np.array([train[i]["etiqueta"] for i in sel])
        probs = predecir(xtr[sel], ytr, xte, ops)
        with open(os.path.join(a.salida, f"pred_knn{k}.jsonl"), "w", encoding="utf-8") as f:
            for r, p in zip(test, probs):
                f.write(json.dumps({"id": r["id"], "probs": p, "ms": round(ms, 3)}, ensure_ascii=False) + "\n")
        res[f"knn{k}"] = metricas(test, probs)
        print(f"kNN-{k}", json.dumps(res[f"knn{k}"], ensure_ascii=False))
    with open(os.path.join(a.salida, "medidas.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
