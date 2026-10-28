#!/usr/bin/env python3
"""Exporta un Model2Vec (potion) al formato binario `.chispa-l1`. Ver README.md.

Uso: exportar.py <directorio-del-modelo> <salida.chispa-l1> [--vocab <json>]

--vocab recorta el modelo a las piezas de `ids_originales` (json como model/bench/vocab-podado-*.json o el que
genera vocab_recortado.py). Los ids se renumeran en orden; `[PAD]`/`[UNK]` se conservan siempre. La tabla hash y el
filtro de prefijos se dimensionan para el vocabulario recortado. Los parámetros del tokenizador (mediana, min_score)
se mantienen los del modelo completo.
Sin dependencias fuera de numpy y safetensors. Determinista: mismo modelo, mismo fichero.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np
from safetensors import safe_open

MAGIC = b"CHL1\0\0\0\0"
VERSION = 1
HEADER_LEN = 256
ESCALA_BITS = 32          # multiplicador entero de fila = round(escala * 2^32)
TABLA_BITS = 20           # 2^20 ranuras en la tabla hash de piezas
SECCIONES = ["params", "charsmap", "piezas", "offsets", "scores", "hash", "pesos", "escalas", "prefijos"]
PREFIJO_BITS = 26         # filtro de prefijos: 2^26 bits (8 MiB), un solo hash (los 26 bits altos de FNV-1a)

PUNTUACION = list("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def fnv1a(b: bytes) -> int:
    h = 0xCBF29CE484222325
    for c in b:
        h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return h


def validar_normalizador(n: dict) -> bytes:
    """Comprueba que el normalizador es exactamente el que implementa el runtime y devuelve el charsmap."""
    import base64
    assert n["type"] == "Sequence", n["type"]
    ns = n["normalizers"]
    pre = ns[0]
    assert pre["type"] == "Sequence" and pre["normalizers"][0]["type"] == "Precompiled"
    assert pre["normalizers"][1] == {"type": "Replace", "pattern": {"Regex": " {2,}"}, "content": " "}
    cm = base64.b64decode(pre["normalizers"][0]["precompiled_charsmap"])
    esperado = [{"type": "Replace", "pattern": {"String": p}, "content": f" {p} "} for p in PUNTUACION]
    esperado += [{"type": "Replace", "pattern": {"Regex": "\\s+"}, "content": " "},
                 {"type": "Strip", "strip_left": True, "strip_right": True}]
    assert ns[1:] == esperado, "el normalizador no es el que implementa el runtime"
    return cm


def recortar_ids(pedidos: list, n: int, obligatorios: set) -> np.ndarray:
    """Ids a conservar: los pedidos más los obligatorios (añadidos y unk), sin repetir, en orden ascendente."""
    ids = {int(i) for i in pedidos} | {int(i) for i in obligatorios}
    assert all(0 <= i < n for i in ids), "id fuera del vocabulario del modelo"
    return np.array(sorted(ids), dtype=np.int64)


def main(dir_modelo: str, salida: str, vocab_json: str | None = None) -> None:
    d = Path(dir_modelo)
    tok = json.loads((d / "tokenizer.json").read_text())
    cfg = json.loads((d / "config.json").read_text())
    assert tok["model"]["type"] == "Unigram" and not tok["model"]["byte_fallback"]
    pt = tok["pre_tokenizer"]
    assert pt == {"type": "Metaspace", "replacement": "▁", "prepend_scheme": "always", "split": False}
    assert tok["truncation"] is None and tok["post_processor"]["type"] == "TemplateProcessing"
    charsmap = validar_normalizador(tok["normalizer"])

    vocab = tok["model"]["vocab"]
    n = len(vocab)
    piezas = [p.encode() for p, _ in vocab]
    assert len(set(piezas)) == n, "piezas duplicadas"
    scores = np.array([s for _, s in vocab], dtype="<f8")
    unk = tok["model"]["unk_id"]
    anadidos = {t["content"]: t["id"] for t in tok["added_tokens"]}
    assert all(not t["normalized"] and not t["lstrip"] and not t["rstrip"] and t["special"]
               for t in tok["added_tokens"])

    with safe_open(d / "model.safetensors", "np") as f:
        emb = f.get_tensor("embeddings")
    assert emb.dtype == np.float32 and emb.shape[0] == n, (emb.dtype, emb.shape, n)
    dim = emb.shape[1]
    assert dim == cfg["hidden_dim"] and cfg.get("normalize", True)

    tabla_bits, prefijo_bits = TABLA_BITS, PREFIJO_BITS
    mediana = int(np.median([len(p) for p, _ in vocab]))      # como model2vec; siempre la del modelo completo
    min_score = float(scores.min())
    if vocab_json:
        ids = recortar_ids(json.loads(Path(vocab_json).read_text())["ids_originales"], n, set(anadidos.values()) | {unk})
        remap = {int(o): i for i, o in enumerate(ids)}
        vocab = [vocab[i] for i in ids]
        piezas, scores, emb = [piezas[i] for i in ids], scores[ids], emb[ids]
        unk, anadidos = remap[unk], {k: remap[v] for k, v in anadidos.items()}
        n = len(ids)
        tabla_bits = max(10, (2 * n - 1).bit_length())           # carga de la tabla entre 0,25 y 0,5
        prefijo_bits = tabla_bits + 6

    # int8 por fila: escala = max|fila|/127 (float32), q = rint(x/escala)
    maxabs = np.abs(emb).max(axis=1)
    escalas = (maxabs / np.float32(127)).astype("<f4")
    seguro = np.where(escalas > 0, escalas, np.float32(1))
    pesos = np.clip(np.rint(emb / seguro[:, None]), -127, 127).astype(np.int8)
    pesos[escalas == 0] = 0

    # mediana de longitud de pieza (en caracteres), como model2vec: recorte de texto = 512 * mediana
    max_piezas_car = max(len(p) for p, _ in vocab)
    params = {
        "tokenizador": "unigram+metaspace+precompiled",
        "modelo_origen": d.parent.parent.name if d.parent.name == "snapshots" else d.name,
        "max_tokens": 512, "mediana_pieza": mediana, "recorte_texto": 512 * mediana,
        "max_pieza_car": max_piezas_car, "unk_id": unk, "unk_penalizacion": 10.0,
        "min_score": min_score, "metaspace": "▁", "prepend": "always",
        "anadidos": anadidos, "puntuacion": "".join(PUNTUACION), "normalize": True,
        "escala_bits": ESCALA_BITS, "dim": dim,
    }
    params_b = json.dumps(params, sort_keys=True, ensure_ascii=False).encode()

    offs = np.zeros(n + 1, dtype="<u4")
    offs[1:] = np.cumsum([len(p) for p in piezas])
    blob = b"".join(piezas)
    tam = 1 << tabla_bits
    tabla = np.zeros(tam, dtype="<u4")
    for i, p in enumerate(piezas):
        s = fnv1a(p) & (tam - 1)
        while tabla[s]:
            s = (s + 1) & (tam - 1)
        tabla[s] = i + 1

    # filtro de prefijos: bit puesto para cada prefijo (en caracteres) de cada pieza; deja cortar la búsqueda
    # en Viterbi en cuanto el texto ya no es prefijo de ninguna pieza (puede tener falsos positivos, no negativos)
    filtro = np.zeros(1 << (prefijo_bits - 3), dtype=np.uint8)
    for p in piezas:
        h = 0xCBF29CE484222325
        for k, c in enumerate(p):
            h = ((h ^ c) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
            if k + 1 == len(p) or (p[k + 1] & 0xC0) != 0x80:
                b = h >> (64 - prefijo_bits)
                filtro[b >> 3] |= 1 << (b & 7)

    cuerpo = {"params": params_b, "charsmap": charsmap, "piezas": blob, "offsets": offs.tobytes(),
              "scores": scores.tobytes(), "hash": tabla.tobytes(), "pesos": pesos.tobytes(),
              "escalas": escalas.tobytes(), "prefijos": filtro.tobytes()}
    tabla_sec, pos, partes = [], HEADER_LEN, []
    for k in SECCIONES:
        b = cuerpo[k]
        pad = (-pos) % 16
        partes.append(b"\0" * pad + b)
        pos += pad
        tabla_sec.append((pos, len(b)))
        pos += len(b)
    resto = b"".join(partes)
    h = hashlib.sha256()
    h.update(resto)
    # cabecera: magic, version, dim, vocab, flags, max_pieza_car, tabla_bits, prefijo_bits, secciones, sha256
    cab = MAGIC + struct.pack("<7I", VERSION, dim, n, 0, max_piezas_car, tabla_bits, prefijo_bits)
    for o, l in tabla_sec:
        cab += struct.pack("<QQ", o, l)
    cab += h.digest()
    cab += b"\0" * (HEADER_LEN - len(cab))
    Path(salida).write_bytes(cab + resto)
    print(f"{salida}: {HEADER_LEN + len(resto)} bytes, sha256 cuerpo {h.hexdigest()}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 4 and a[2] == "--vocab":
        main(a[0], a[1], a[3])
    elif len(a) == 2:
        main(*a)
    else:
        sys.exit(__doc__)
