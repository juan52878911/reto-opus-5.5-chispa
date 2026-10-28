"""Referencia independiente (Python, aritmética entera) del embedding de un `.chispa-l1` propio y su hash dorado.

    python -m model.l1.dorado --dir /tmp/l1propio/d256 --modelo /tmp/l1propio/d256/propio-256.chispa-l1 \\
        --escribir model/l1/go/testdata/dorado-256.json

Reproduce `runtime/l1.Embed`: ids de `tokenizers` con el tokenizer.json estático (sin tokens especiales; `<unk>`
descartado, con el tokenizador recortado a las piezas conservadas; texto recortado a 512·mediana caracteres y 512 tokens), M = round(escala·2^32), acc = Σ q·M en
enteros, norma = sqrt(Σ float64(acc)²) en orden fijo y out = float32(acc / norma). El test de Go
(`go/dorado_test.go`) exige el mismo hash para las 200 primeras frases del sondeo; como la aritmética es solo
entera más + * / sqrt de IEEE-754, vale igual en amd64 y arm64.
"""
import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np

from . import comun

FRASES = comun.RAIZ / "runtime/l1/testdata/ids_sondeo.jsonl"


def cargar(modelo):
    """-> dim, vocab, pesos (v × dim int8), escalas (v), params, sha256 del cuerpo, desde el propio fichero."""
    b = Path(modelo).read_bytes()
    dim, vocab = struct.unpack_from("<II", b, 12)
    sec = [struct.unpack_from("<QQ", b, 36 + 16 * i) for i in range(9)]
    trozo = lambda i: b[sec[i][0]:sec[i][0] + sec[i][1]]
    pesos = np.frombuffer(trozo(6), dtype=np.int8).reshape(vocab, dim)
    esc = np.frombuffer(trozo(7), dtype="<f4")
    return dim, vocab, pesos, esc, json.loads(trozo(0)), b[36 + 16 * 9:36 + 16 * 9 + 32].hex()


class Referencia:
    def __init__(self, dir_modelo, modelo):
        from tokenizers import Tokenizer
        tj = json.loads((Path(dir_modelo) / "tokenizer.json").read_text())
        self.dim, _, self.pesos, esc, self.params, self.hash_cuerpo = cargar(modelo)
        ids = json.loads((Path(dir_modelo) / "vocab.json").read_text())["ids_originales"]
        self.remap = {o: i for i, o in enumerate(sorted(set(ids) | set(comun.ESPECIALES)))}
        # Tokenizador recortado: solo las piezas conservadas, con los ids renumerados como en el .chispa-l1. El
        # runtime usa el min_score del modelo completo para los caracteres sin pieza; aquí se reproduce con una
        # pieza de relleno (nunca aparece en el texto) que lleva ese score.
        vocab = tj["model"]["vocab"]
        orden = sorted(self.remap)
        tj["model"]["vocab"] = [vocab[o] for o in orden] + [["\ue000\ue001\ue002", self.params["min_score"]]]
        tj["model"]["unk_id"] = self.remap[tj["model"]["unk_id"]]
        for t in tj["added_tokens"]:
            t["id"] = self.remap[t["id"]]
        self.tok = Tokenizer.from_str(json.dumps(tj))
        self.mult = np.rint(esc.astype(np.float64) * 2.0 ** 32).astype(np.int64)

    def embed(self, texto):
        texto = texto[:self.params["recorte_texto"]]
        ids = self.tok.encode(texto, add_special_tokens=False).ids[:self.params["max_tokens"]]
        unk = self.params["unk_id"]
        acc = np.zeros(self.dim, dtype=np.int64)
        for o in ids:
            i = o
            if i != unk:
                acc += self.pesos[i].astype(np.int64) * self.mult[i]
        ss = 0.0
        for a in acc:
            f = float(a)
            ss += f * f
        if ss == 0.0:
            return np.zeros(self.dim, dtype="<f4")
        norma = math.sqrt(ss)
        return np.array([np.float32(float(a) / norma) for a in acc], dtype="<f4")


def hash_embeddings(embs):
    h = hashlib.sha256()
    for e in embs:
        h.update(np.asarray(e, dtype="<f4").tobytes())
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", required=True)
    ap.add_argument("--modelo", required=True)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--escribir", required=True)
    a = ap.parse_args(argv)
    ref = Referencia(a.dir, a.modelo)
    frases = [r["texto"] for r in comun.leer(FRASES)][:a.n]
    gold = {"modelo": Path(a.modelo).name, "dim": ref.dim, "hash_cuerpo": ref.hash_cuerpo, "n": a.n,
            "hash_embeddings": hash_embeddings([ref.embed(t) for t in frases])}
    Path(a.escribir).write_text(json.dumps(gold, indent=1) + "\n")
    print(gold)


if __name__ == "__main__":
    main()
