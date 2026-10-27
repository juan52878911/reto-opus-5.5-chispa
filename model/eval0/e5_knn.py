"""multilingual-e5-small + kNN con k ejemplos por clase (8 o 32) del conjunto de entrenamiento del sondeo.
Uso del autor (model card de intfloat): prefijo «query: » en ambos lados y similitud coseno de embeddings normalizados.
Probabilidad: softmax(sim/T) ponderado sobre los 10 vecinos más cercanos, sumado por clase."""
import glob, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

T, VECINOS = 0.05, 10


class E5Knn:
    def __init__(self, train, k):
        from sentence_transformers import SentenceTransformer
        p = glob.glob(os.path.expanduser("~/hf/hub/models--intfloat--multilingual-e5-small/snapshots/*"))[0]
        self.m = SentenceTransformer(p, device="cpu")
        tr = [r for r in train if r["idx_clase"] < k]
        self.y = np.array([r["etiqueta"] for r in tr])
        self.x = self.m.encode(["query: " + r["texto"] for r in tr], normalize_embeddings=True, batch_size=32)

    def predecir(self, f):
        q = self.m.encode(["query: " + f["texto"]], normalize_embeddings=True)[0]
        s = self.x @ q
        idx = np.argsort(-s)[:VECINOS]
        w = np.exp((s[idx] - s[idx].max()) / T)
        p = {o: 0.0 for o in f["opciones"]}
        for i, wi in zip(idx, w):
            p[self.y[i]] += wi
        tot = sum(p.values())
        return [p[o] / tot for o in f["opciones"]]


if __name__ == "__main__":
    import argparse
    k = int(sys.argv[sys.argv.index("--k") + 1])
    common.main(f"e5_knn{k}", lambda t, tr, a: E5Knn(tr, k), "MIT (intfloat/multilingual-e5-small)",
                extra_args=[("--k", dict(type=int, required=True))])
