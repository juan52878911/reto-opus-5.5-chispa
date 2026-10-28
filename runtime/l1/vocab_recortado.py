#!/usr/bin/env python3
"""Elige las piezas de potion-multilingual-128M que usa el español y las guarda como `ids_originales`.

Uso: vocab_recortado.py <directorio-del-modelo> <salida.json> [--max 50000]

Tokeniza con `tokenizers` un corpus en español que NO incluye el test del sondeo (MASSIVE es train/validación, XNLI y
PAWS-X es, SIB-200 spa, GoEmotions es, spam es y los `train_*.jsonl` del sondeo) y se queda con [PAD]/[UNK], todas las
piezas de un solo carácter vistas y las más frecuentes hasta `--max` y, si sobra cupo, las de mayor log-prob del unigram. Determinista (desempate por id).
"""
import collections
import glob
import gzip
import json
import os
import sys
from pathlib import Path

import pyarrow.parquet as pq
from tokenizers import Tokenizer

HF = os.path.expanduser("~/hf/hub")
SONDEO = Path(__file__).resolve().parents[2] / "model" / "sondeo"
MAX_XNLI = 100_000


def g(patron):
    r = sorted(glob.glob(f"{HF}/{patron}"))
    assert r, patron
    return r


def columnas(patron, cols, tope=None):
    for f in g(patron):
        t = pq.read_table(f, columns=cols)
        for c in cols:
            for x in t[c].to_pylist()[:tope]:
                if x:
                    yield x


def textos():
    for f in g("datasets--mteb--amazon_massive_intent/snapshots/*/train/es.json.gz") + \
            g("datasets--mteb--amazon_massive_intent/snapshots/*/validation/es.json.gz"):
        for l in gzip.open(f, "rt"):
            yield json.loads(l)["text"]
    yield from columnas("datasets--facebook--xnli/snapshots/*/es/train-*.parquet", ["premise"], MAX_XNLI)
    yield from columnas("datasets--google-research-datasets--paws-x/snapshots/*/es/train-*.parquet", ["sentence1"])
    yield from columnas("datasets--mrm8488--go_emotions-es-mt/snapshots/*/data/train-*.parquet", ["text_es"])
    for f in g("datasets--Davlan--sib200/snapshots/*/data/spa_Latn/*.tsv"):
        if not f.endswith("test.tsv"):
            for l in open(f, encoding="utf-8").read().splitlines()[1:]:
                yield l.split("\t")[-1]
    for f in sorted(SONDEO.glob("train_*.jsonl")):
        for l in open(f, encoding="utf-8"):
            yield json.loads(l)["texto"]


def main(dir_modelo, salida, maximo=50_000):
    tok = Tokenizer.from_file(str(Path(dir_modelo) / "tokenizer.json"))
    cuenta = collections.Counter()
    lote, n = [], 0
    for t in textos():
        lote.append(t)
        n += 1
        if len(lote) == 5000:
            for e in tok.encode_batch(lote, add_special_tokens=False):
                cuenta.update(e.ids)
            lote = []
    for e in tok.encode_batch(lote, add_special_tokens=False):
        cuenta.update(e.ids)
    vocab = json.loads((Path(dir_modelo) / "tokenizer.json").read_text())["model"]["vocab"]
    ids = {0, 1}
    ids |= {i for i in cuenta if len(vocab[i][0].replace("▁", "")) <= 1}
    for i, _ in sorted(cuenta.items(), key=lambda kv: (-kv[1], kv[0])):
        if len(ids) >= maximo:
            break
        ids.add(i)
    # si el corpus no llena el cupo, se completa con las piezas de mayor log-prob del unigram (las más generales)
    for i in sorted(range(len(vocab)), key=lambda i: (-vocab[i][1], i)):
        if len(ids) >= maximo:
            break
        ids.add(i)
    cubierto = sum(c for i, c in cuenta.items() if i in ids) / sum(cuenta.values())
    ids = sorted(ids)
    Path(salida).write_text(json.dumps({"modelo": "potion-multilingual-128M", "original": len(vocab),
                                        "conservados": len(ids), "frases_corpus": n, "ids_originales": ids}))
    print(f"{salida}: {len(ids)} piezas, {n} frases, {cubierto:.4%} de los tokens del corpus cubiertos")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2:
        main(*a)
    elif len(a) == 4 and a[2] == "--max":
        main(a[0], a[1], int(a[3]))
    else:
        sys.exit(__doc__)
