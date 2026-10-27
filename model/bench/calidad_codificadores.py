#!/usr/bin/env python
"""Calidad de e5-small y mmBERT-small como codificadores + kNN sobre el sondeo (train_*.jsonl contra *.jsonl).

Uso: python model/bench/calidad_codificadores.py [--n 120] [--salida model/bench/calidad.md]
  e5-small: prefijo «query: », media de tokens normalizada. mmBERT-small: media de la última capa, normalizada.
  kNN igual que model/eval0/e5_knn.py: k ejemplos por clase (idx_clase < k), 10 vecinos, softmax(sim/0,05).
  --n 0 = test completo; --n 120 = el subconjunto fijo (semilla 0) de la fase 0, para comparar con 75,9.
Las métricas salen de model.evaluacion.chispa_eval.evaluar.
"""
import argparse, glob, json, os, random, sys
import numpy as np

RAIZ = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, RAIZ)
from model.evaluacion import chispa_eval as CE  # noqa: E402

SONDEO = os.path.join(RAIZ, "model", "sondeo")
TAREAS = ["intencion", "toxicidad", "whatsapp_comercio", "herramientas"]
T, VECINOS = 0.05, 10
HF = os.environ.get("HF_HOME", os.path.expanduser("~/hf"))
MODELOS = {"e5-small": ("intfloat--multilingual-e5-small", "query: "),
           "mmBERT-small": ("jhu-clsp--mmBERT-small", "")}


def cargar(tarea, n):
    test = CE.asignar_ids(CE.leer_jsonl(f"{SONDEO}/{tarea}.jsonl"), f"{tarea}.jsonl")
    train = CE.leer_jsonl(f"{SONDEO}/train_{tarea}.jsonl")
    if n:
        test = [test[i] for i in sorted(random.Random(0).sample(range(len(test)), min(n, len(test))))]
    return test, train


class Codificador:
    def __init__(self, nombre):
        import torch
        from transformers import AutoModel, AutoTokenizer
        d, self.prefijo = MODELOS[nombre]
        ruta = glob.glob(f"{HF}/hub/models--{d}/snapshots/*")[0]
        self.tok = AutoTokenizer.from_pretrained(ruta)
        self.mod = AutoModel.from_pretrained(ruta).eval()
        self.torch = torch

    def codificar(self, textos, lote=32):
        torch, out = self.torch, []
        with torch.no_grad():
            for i in range(0, len(textos), lote):
                b = self.tok([self.prefijo + t for t in textos[i:i + lote]], padding=True, truncation=True,
                             max_length=512, return_tensors="pt")
                h = self.mod(**b).last_hidden_state
                m = b["attention_mask"].unsqueeze(-1).to(h.dtype)
                v = (h * m).sum(1) / m.sum(1)
                out.append(torch.nn.functional.normalize(v, dim=-1).numpy())
        return np.concatenate(out)


def knn(xtr, ytr, xte, filas, k, idx_clase):
    sel = np.array([c < k for c in idx_clase])
    x, y = xtr[sel], np.array(ytr)[sel]
    preds = []
    for q, f in zip(xte, filas):
        s = x @ q
        idx = np.argsort(-s)[:VECINOS]
        w = np.exp((s[idx] - s[idx].max()) / T)
        p = {o: 0.0 for o in f["opciones"]}
        for i, wi in zip(idx, w):
            p[str(y[i])] += float(wi)
        tot = sum(p.values())
        preds.append({"id": f["id"], "probs": {o: float(v / tot) for o, v in p.items()}})
    return preds


def correr(n):
    """Devuelve {(modelo, k): {tarea: (macro_f1, ece)}} y el n de test por tarea."""
    datos = {t: cargar(t, n) for t in TAREAS}
    res = {}
    for nombre in MODELOS:
        enc = Codificador(nombre)
        for t, (test, train) in datos.items():
            xtr = enc.codificar([r["texto"] for r in train])
            xte = enc.codificar([r["texto"] for r in test])
            for k in (8, 32):
                m = CE.evaluar(test, knn(xtr, [r["etiqueta"] for r in train], xte, test, k,
                                         [r["idx_clase"] for r in train]))["global"]
                res.setdefault((nombre, k), {})[t] = (100 * m["macro_f1"], m["ece"])
            print(nombre, t, "listo", flush=True)
        del enc
    return res, {t: len(d[0]) for t, d in datos.items()}


def tabla(res, ns):
    cab = "| codificador | kNN | " + " | ".join(TAREAS) + " | media macro-F1 | ECE medio |"
    o = [cab, "|" + "---|" * (len(TAREAS) + 4)]
    for (nombre, k), r in res.items():
        f = [r[t][0] for t in TAREAS]
        o.append(f"| {nombre} | {k} | " + " | ".join(f"{v:.1f}" for v in f)
                 + f" | **{np.mean(f):.1f}** | {np.mean([r[t][1] for t in TAREAS]):.3f} |")
    return "\n".join(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, nargs="*", default=[0, 120])
    ap.add_argument("--salida", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "calidad.md"))
    a = ap.parse_args()
    o = ["# Calidad de e5-small y mmBERT-small (codificador + kNN)", "",
         "Macro-F1 (×100) y ECE de `model.evaluacion.chispa_eval` sobre las 4 tareas de `model/sondeo/` (train_*.jsonl "
         "como memoria, *.jsonl como test). e5-small: prefijo `query: `, media de tokens normalizada. mmBERT-small "
         "(pesos reales de `pytorch_model.bin`): media de la última capa normalizada, sin entrenar para embeddings. "
         "kNN-k = k ejemplos por clase, 10 vecinos, softmax(sim/0,05) (igual que `model/eval0/e5_knn.py`). "
         "Generado por `model/bench/calidad_codificadores.py`.", ""]
    for n in a.n:
        res, ns = correr(n)
        o += [f"## {'Test completo' if not n else f'Subconjunto fijo de {n} (semilla 0, el de la fase 0)'}"
              f" (n por tarea: {', '.join(f'{t} {v}' for t, v in ns.items())})", "", tabla(res, ns), ""]
        e5, mm = np.mean([v[0] for v in res[("e5-small", 32)].values()]), np.mean([v[0] for v in res[("mmBERT-small", 32)].values()])
        o += [f"mmBERT − e5 con kNN-32: {mm - e5:+.1f} puntos de macro-F1 media (umbral de la hipótesis: +3).", ""]
    open(a.salida, "w", encoding="utf-8").write("\n".join(o))
    print("\n".join(o))


if __name__ == "__main__":
    main()
