#!/usr/bin/env python3
"""Referencia en Python para los tests del runtime L1 (model2vec + tokenizers).

  referencia.py ids <modelo> <salida.jsonl> [--fuzz N]   texto + ids de tokenizers
  referencia.py emb <modelo> <chispa-l1> <salida.jsonl>   embeddings fp32 e int8 (misma cuantización); frases = testdata/ids_sondeo.jsonl
"""
import glob
import json
import math
import random
import struct
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]


def frases_sondeo():
    vistos, out = set(), []
    for f in sorted(glob.glob(str(RAIZ / "model/sondeo/*.jsonl"))):
        for linea in open(f, encoding="utf-8"):
            t = json.loads(linea)["texto"]
            if t not in vistos:
                vistos.add(t)
                out.append(t)
    return out


def casos_borde():
    return ["", " ", "hola", "Hola, ¿qué tal?", "[UNK]", "hola[UNK]qué", "[PAD] x [PAD]", "[UNK][UNK]", "▁hola",
            "▁▁a", "é", "ña", "ｈｏｌａ　ＭＵＮＤＯ", "ﬁnal ﬂor", "①②③", "a b c\tx\ny", "\r\n", "a\r\nb",
            "𐀀𐀁𐀂", "😀😀 hola 👍🏽", "한국어 텍스트", "x" * 5000, "palabra " * 800, "\u0000a\u0000", "a�b",
            "¡¡hola!!", "a.b-c_d/e", "1,234.56 $", "Ａ", "ǅ", "​", "́", "ñ", "ñ".encode().decode(),
            "각", "　a", "a b", "[unk]", "[ UNK ]"]


def fuzz(n, seed=7):
    rnd = random.Random(seed)
    cps = [c for c in range(0x20, 0x30000) if not 0xD800 <= c < 0xE000]
    marcas = [c for c in range(0x300, 0x370)] + [0x200D, 0x200C, 0xFE0F, 0x1F3FD, 0x0A4D, 0x093E]
    out = []
    for c in cps[:: max(1, len(cps) // n)]:
        out.append(chr(c))
        out.append("a" + chr(c) + "b")
    for _ in range(n):
        s = "".join(chr(rnd.choice(cps)) if rnd.random() < .6 else rnd.choice("aeiou nñ,.¿?") for _ in range(rnd.randint(1, 12)))
        out.append(s)
        base = chr(rnd.choice(cps[:3000]))
        out.append(base + "".join(chr(rnd.choice(marcas)) for _ in range(rnd.randint(1, 3))))
    return out


def cargar_modelo(ruta):
    from model2vec import StaticModel
    return StaticModel.from_pretrained(ruta)


def ids_de(m, texto):
    cut = m.max_length * m.median_token_length
    return m.tokenizer.encode(texto[:cut], add_special_tokens=False).ids


def cmd_ids(ruta, salida, nfuzz=0):
    m = cargar_modelo(ruta)
    textos = casos_borde() + frases_sondeo() + (fuzz(nfuzz) if nfuzz else [])
    with open(salida, "w", encoding="utf-8") as f:
        for t in textos:
            f.write(json.dumps({"texto": t, "ids": ids_de(m, t)}, ensure_ascii=False) + "\n")
    print(len(textos), "frases")


def int8_ref(ids_sin_unk, q, esc):
    """Mismo cálculo que el runtime Go, en enteros de Python y float64 sin FMA (bucle secuencial)."""
    dim = q.shape[1]
    acc = [0] * dim
    for i in ids_sin_unk:
        M = round(float(esc[i]) * (1 << 32))
        fila = q[i].tolist()
        for j in range(dim):
            acc[j] += fila[j] * M
    ss = 0.0
    for a in acc:
        f = float(a)
        ss += f * f
    if ss == 0.0:
        return np.zeros(dim, dtype=np.float32)
    norma = math.sqrt(ss)
    return np.array([float(a) / norma for a in acc], dtype=np.float32)


def cmd_emb(ruta, chispa, salida):
    import hashlib
    sys.path.insert(0, str(Path(__file__).parent))
    m = cargar_modelo(ruta)
    textos = [json.loads(l)["texto"] for l in open(Path(__file__).parent / "testdata/ids_sondeo.jsonl", encoding="utf-8")]
    fp32 = m.encode(textos)
    # pesos/escala del .chispa-l1 (misma cuantización que usa el runtime)
    b = Path(chispa).read_bytes()
    dim, vocab = struct.unpack_from("<II", b, 12)
    sec = [struct.unpack_from("<QQ", b, 36 + 16 * i) for i in range(8)]
    q = np.frombuffer(b, dtype=np.int8, count=sec[6][1], offset=sec[6][0]).reshape(vocab, dim)
    esc = np.frombuffer(b, dtype="<f4", count=vocab, offset=sec[7][0])
    unk = m.unk_token_id
    cos, filas = [], []
    for t, e in zip(textos, fp32):
        ids = [i for i in ids_de(m, t) if i != unk]
        e8 = int8_ref(ids, q, esc) if ids else np.zeros(dim, dtype=np.float32)
        den = float(np.linalg.norm(e8) * np.linalg.norm(e))
        if den:
            cos.append(float(e8 @ e) / den)
        filas.append(e8)
    cos = np.array(cos)
    h = hashlib.sha256()
    for e8 in filas[:200]:
        h.update(e8.astype("<f4").tobytes())
    res = {"n": len(textos), "n_cos": len(cos), "cos_medio": float(cos.mean()), "cos_min": float(cos.min()),
           "peor": [t for t, e8, e in zip(textos, filas, fp32) if np.linalg.norm(e8) * np.linalg.norm(e)][int(cos.argmin())], "hash200": h.hexdigest()}
    print(json.dumps(res, ensure_ascii=False))
    with open(salida, "w") as f:
        for t, e8 in zip(textos, filas):
            f.write(json.dumps({"texto": t, "emb": e8.astype("<f4").tobytes().hex()}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["ids"] and len(a) >= 3:
        cmd_ids(a[1], a[2], int(a[4]) if a[3:4] == ["--fuzz"] else 0)
    elif a[:1] == ["emb"] and len(a) == 4:
        cmd_emb(*a[1:])
    else:
        sys.exit(__doc__)
