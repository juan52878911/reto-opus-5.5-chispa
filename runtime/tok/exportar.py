#!/usr/bin/env python3
"""Exporta el tokenizador de e5 (XLM-R, sentencepiece unigram) a `.chispa-tok`.

Uso: exportar.py <directorio-del-modelo-e5> <salida.chispa-tok>

Mismo formato que `.chispa-l1` (ver runtime/l1) con magia CHTK y las secciones pesos/escalas vacías.
Reusa fnv1a y las constantes de runtime/l1/exportar.py. Determinista.
"""
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location("l1_exportar", Path(__file__).resolve().parent.parent / "l1" / "exportar.py")
l1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(l1)

MAGIC = b"CHTK\0\0\0\0"


def main(dir_modelo: str, salida: str) -> None:
    import base64
    tok = json.loads((Path(dir_modelo) / "tokenizer.json").read_text())
    m = tok["model"]
    assert m["type"] == "Unigram" and not m.get("byte_fallback")
    assert tok["normalizer"]["normalizers"][0]["type"] == "Precompiled"
    charsmap = base64.b64decode(tok["normalizer"]["normalizers"][0]["precompiled_charsmap"])
    vocab = m["vocab"]
    n = len(vocab)
    piezas = [p.encode() for p, _ in vocab]
    assert len(set(piezas)) == n, "piezas duplicadas"
    scores = np.array([s for _, s in vocab], dtype="<f8")
    anadidos = {t["content"]: t["id"] for t in tok["added_tokens"]}
    assert all(not t["normalized"] and t["special"] for t in tok["added_tokens"])

    tabla_bits = max(10, (2 * n - 1).bit_length())
    prefijo_bits = tabla_bits + 6
    params = {
        "tokenizador": "unigram+whitespacesplit+metaspace+precompiled", "modo": "xlmr",
        "modelo_origen": "intfloat/multilingual-e5-small", "max_tokens": 1 << 30, "recorte_texto": 1 << 30,
        "max_pieza_car": max(len(p) for p, _ in vocab), "unk_id": m["unk_id"], "unk_penalizacion": 10.0,
        "min_score": float(scores.min()), "metaspace": "▁", "prepend": "always", "anadidos": anadidos,
        "puntuacion": "", "normalize": False, "escala_bits": l1.ESCALA_BITS, "dim": 0,
    }
    offs = np.zeros(n + 1, dtype="<u4")
    offs[1:] = np.cumsum([len(p) for p in piezas])
    tam = 1 << tabla_bits
    tabla = np.zeros(tam, dtype="<u4")
    for i, p in enumerate(piezas):
        s = l1.fnv1a(p) & (tam - 1)
        while tabla[s]:
            s = (s + 1) & (tam - 1)
        tabla[s] = i + 1
    filtro = np.zeros(1 << (prefijo_bits - 3), dtype=np.uint8)
    for p in piezas:
        h = 0xCBF29CE484222325
        for k, c in enumerate(p):
            h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
            if k + 1 == len(p) or (p[k + 1] & 0xC0) != 0x80:
                b = h >> (64 - prefijo_bits)
                filtro[b >> 3] |= 1 << (b & 7)
    cuerpo = {"params": json.dumps(params, sort_keys=True, ensure_ascii=False).encode(), "charsmap": charsmap,
              "piezas": b"".join(piezas), "offsets": offs.tobytes(), "scores": scores.tobytes(),
              "hash": tabla.tobytes(), "pesos": b"", "escalas": b"", "prefijos": filtro.tobytes()}
    tabla_sec, pos, partes = [], l1.HEADER_LEN, []
    for k in l1.SECCIONES:
        b = cuerpo[k]
        pad = (-pos) % 16
        partes.append(b"\0" * pad + b)
        pos += pad
        tabla_sec.append((pos, len(b)))
        pos += len(b)
    resto = b"".join(partes)
    cab = MAGIC + struct.pack("<7I", l1.VERSION, 0, n, 0, params["max_pieza_car"], tabla_bits, prefijo_bits)
    for o, l in tabla_sec:
        cab += struct.pack("<QQ", o, l)
    cab += hashlib.sha256(resto).digest()
    cab += b"\0" * (l1.HEADER_LEN - len(cab))
    Path(salida).write_bytes(cab + resto)
    print(f"{salida}: {l1.HEADER_LEN + len(resto)} bytes")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
