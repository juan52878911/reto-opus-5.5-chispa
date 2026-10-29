#!/usr/bin/env python3
"""ONNX sintético de consulta de L2 (forma de l2_ort.go): pesos aleatorios, determinista.

  l2_sintetico.py [--max-len N] [--vocab V] [salida.onnx]

Con --max-len N escribe en metadata_props la clave chispa.consulta.max_len = N (el truncado de la consulta que lee el runtime);
`l2_sintetico_ml256.onnx` es `--max-len 256 --vocab 1000` (unos 21 KB).

Entradas input_ids y attention_mask int64 (1,T); salida S float32 (1,T,256), una ranura por token. Red: embedding de 4
dimensiones (vocabulario de e5, 250002) → Linear(4→256) → tanh. Opset 17; pesa < 5 MB.
"""
import argparse
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto as TP, helper as H, numpy_helper as N

EMB, DIM = 4, 256
ap = argparse.ArgumentParser()
ap.add_argument("--max-len", type=int)
ap.add_argument("--vocab", type=int, default=250002)
ap.add_argument("salida", nargs="?")
args = ap.parse_args()
VOCAB = args.vocab

rng = np.random.default_rng(20261029)
ini = [N.from_array(rng.normal(0, 1, (VOCAB, EMB)).astype(np.float32), "emb"),
       N.from_array((rng.normal(0, 1, (EMB, DIM)) / np.sqrt(EMB)).astype(np.float32), "w"),
       N.from_array(rng.normal(0, 0.1, DIM).astype(np.float32), "b")]
n = [H.make_node("Gather", ["emb", "input_ids"], ["e"]), H.make_node("MatMul", ["e", "w"], ["x"]),
     H.make_node("Add", ["x", "b"], ["y"]), H.make_node("Tanh", ["y"], ["S"])]
g = H.make_graph(n, "l2_sintetico",
                 [H.make_tensor_value_info("input_ids", TP.INT64, [1, "T"]),
                  H.make_tensor_value_info("attention_mask", TP.INT64, [1, "T"])],
                 [H.make_tensor_value_info("S", TP.FLOAT, [1, "T", DIM])], ini)
m = H.make_model(g, opset_imports=[H.make_opsetid("", 17)], producer_name="chispa-l2-sintetico")
m.ir_version = 8
if args.max_len is not None:
    p = m.metadata_props.add()
    p.key, p.value = "chispa.consulta.max_len", str(args.max_len)
onnx.checker.check_model(m)
sal = args.salida or str(Path(__file__).resolve().parent / "l2_sintetico.onnx")
onnx.save(m, sal)
print(sal, Path(sal).stat().st_size, "bytes")
