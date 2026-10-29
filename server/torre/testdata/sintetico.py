#!/usr/bin/env python3
"""ONNX sintético de la torre de esquemas de L2 (model/l2/contrato-torre.md): misma forma que el real, pesos aleatorios.

  sintetico.py [salida.onnx] [referencia.json]

Entradas input_ids y attention_mask int64 (B,T); salida h float32 (B,256) normalizada; opset 17; vocabulario de e5 (250002)
con embeddings de 4 dimensiones para que pese < 5 MB. Red: embedding → media ponderada por la máscara → L2 → Linear(4→512)
→ GELU exacta (erf) → Linear(512→256) → L2. Semilla fija: la salida es determinista. También escribe la referencia
(ids → h calculada con onnxruntime de Python) que compara el test de Go con -tags ort.
"""
import json
import sys
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto as TP, helper as H, numpy_helper as N

VOCAB, EMB, OCULTA, DIM, OPSET = 250002, 4, 512, 256, 17
EPS = 1e-12


def construir():
    rng = np.random.default_rng(20261028)
    pesos = {
        "emb": rng.normal(0, 1, (VOCAB, EMB)).astype(np.float32),
        "w1": (rng.normal(0, 1, (EMB, OCULTA)) / np.sqrt(EMB)).astype(np.float32),
        "b1": rng.normal(0, 0.1, OCULTA).astype(np.float32),
        "w2": (rng.normal(0, 1, (OCULTA, DIM)) / np.sqrt(OCULTA)).astype(np.float32),
        "b2": rng.normal(0, 0.1, DIM).astype(np.float32),
    }
    ini = [N.from_array(v, k) for k, v in pesos.items()]
    ini += [N.from_array(np.array(x, np.float32), n) for n, x in
            [("uno", 1.0), ("eps", EPS), ("medio", 0.5), ("raiz2", np.sqrt(2.0))]]
    for nombre, v in [("eje", -1), ("eje_u", -1), ("eje_t", 1), ("eje_1", 1)]:
        ini.append(N.from_array(np.array([v], np.int64), nombre))
    n = []
    n.append(H.make_node("Gather", ["emb", "input_ids"], ["e"]))                      # (B,T,EMB)
    n.append(H.make_node("Cast", ["attention_mask"], ["m"], to=TP.FLOAT))             # (B,T)
    n.append(H.make_node("Unsqueeze", ["m", "eje"], ["m3"]))                          # (B,T,1)
    n.append(H.make_node("Mul", ["e", "m3"], ["em"]))
    n.append(H.make_node("ReduceSum", ["em", "eje_t"], ["s"], keepdims=0))            # (B,EMB) sobre T
    n.append(H.make_node("ReduceSum", ["m", "eje_1"], ["c"], keepdims=1))             # (B,1)
    n.append(H.make_node("Max", ["c", "uno"], ["cm"]))
    n.append(H.make_node("Div", ["s", "cm"], ["media"]))
    n += l2("media", "v")
    n.append(H.make_node("MatMul", ["v", "w1"], ["x1"]))
    n.append(H.make_node("Add", ["x1", "b1"], ["x2"]))
    n += gelu("x2", "g")
    n.append(H.make_node("MatMul", ["g", "w2"], ["x3"]))
    n.append(H.make_node("Add", ["x3", "b2"], ["x4"]))
    n += l2("x4", "h")
    g = H.make_graph(
        n, "torre_sintetica",
        [H.make_tensor_value_info("input_ids", TP.INT64, ["B", "T"]),
         H.make_tensor_value_info("attention_mask", TP.INT64, ["B", "T"])],
        [H.make_tensor_value_info("h", TP.FLOAT, ["B", DIM])], ini)
    m = H.make_model(g, opset_imports=[H.make_opsetid("", OPSET)], producer_name="chispa-torre-sintetica")
    m.ir_version = 8
    onnx.checker.check_model(m)
    return m


def l2(x, y):
    """y = x / max(‖x‖₂, eps) sobre el último eje."""
    p = [H.make_node("Mul", [x, x], [y + "_2"]), H.make_node("ReduceSum", [y + "_2", "eje_u"], [y + "_s"], keepdims=1),
         H.make_node("Sqrt", [y + "_s"], [y + "_n"]), H.make_node("Max", [y + "_n", "eps"], [y + "_m"]),
         H.make_node("Div", [x, y + "_m"], [y])]
    return p


def gelu(x, y):
    """GELU exacta: 0,5·x·(1 + erf(x/√2))."""
    return [H.make_node("Div", [x, "raiz2"], [y + "_a"]), H.make_node("Erf", [y + "_a"], [y + "_b"]),
            H.make_node("Add", [y + "_b", "uno"], [y + "_c"]), H.make_node("Mul", [x, y + "_c"], [y + "_d"]),
            H.make_node("Mul", [y + "_d", "medio"], [y])]


def main(sal_onnx, sal_ref):
    m = construir()
    onnx.save(m, sal_onnx)
    import onnxruntime as ort
    s = ort.InferenceSession(sal_onnx, providers=["CPUExecutionProvider"])
    casos = [[0, 5, 2], [0, 40000, 123456, 250001, 7, 2], [0, 100, 200, 300, 400, 500, 600, 2]]
    ref = []
    for ids in casos:
        h = s.run(["h"], {"input_ids": np.array([ids], np.int64), "attention_mask": np.ones((1, len(ids)), np.int64)})[0][0]
        assert h.shape == (DIM,) and abs(float(np.linalg.norm(h)) - 1) < 1e-5
        ref.append({"ids": ids, "h": [float(x) for x in h]})
    Path(sal_ref).write_text(json.dumps(ref))
    print(sal_onnx, Path(sal_onnx).stat().st_size, "bytes")


if __name__ == "__main__":
    d = Path(__file__).resolve().parent
    main(sys.argv[1] if len(sys.argv) > 1 else str(d / "sintetico.onnx"),
         sys.argv[2] if len(sys.argv) > 2 else str(d / "sintetico_ref.json"))
