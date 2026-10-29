"""ONNX de torre diminuto con el contrato (para probar `--torre` sin el sintético de 4,5 MB) y generador del .chispa de Go.

  PYTHONPATH=sdk/python python sdk/python/tests/fixture_torre.py server/torre/testdata/torre_train.chispa
"""
import json
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto as TP, helper as H, numpy_helper as N


def onnx_torre(dim=8, entrada="input_ids", salida="h", opset=17, meta=None, tipo_ids=TP.INT64, norm=True) -> bytes:
    rng = np.random.default_rng(1)
    ini = [N.from_array(rng.normal(0, 1, (3000, 4)).astype(np.float32), "emb"),
           N.from_array(rng.normal(0, 1, (4, dim)).astype(np.float32), "w"),
           N.from_array(np.array([-1], np.int64), "eje")]
    nodos = [H.make_node("Gather", ["emb", entrada], ["e"]),
             H.make_node("Cast", ["attention_mask"], ["m"], to=TP.FLOAT),
             H.make_node("Unsqueeze", ["m", "eje"], ["m3"]),
             H.make_node("Mul", ["e", "m3"], ["em"]),
             H.make_node("ReduceMean", ["em"], ["media"], axes=[1], keepdims=0),
             H.make_node("MatMul", ["media", "w"], ["x"]),
             H.make_node("LpNormalization", ["x"], [salida], axis=1, p=2) if norm else H.make_node("Identity", ["x"], [salida])]
    g = H.make_graph(nodos, "torre", [H.make_tensor_value_info(entrada, tipo_ids, ["B", "T"]),
                                      H.make_tensor_value_info("attention_mask", TP.INT64, ["B", "T"])],
                     [H.make_tensor_value_info(salida, TP.FLOAT, ["B", dim])], ini)
    m = H.make_model(g, opset_imports=[H.make_opsetid("", opset)])
    m.ir_version = 8
    for k, v in (meta or {}).items():
        p = m.metadata_props.add()
        p.key, p.value = k, str(v)
    return m.SerializeToString()


if __name__ == "__main__":
    from chispa.train import entrenar
    ESQ = {"id": "urg", "pregunta": "¿Qué tan urgente es?", "tipo": "choice",
           "opciones": {"alta": "Requiere atención inmediata", "baja": "Puede esperar"}}
    from chispa import formato
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "e.json").write_text(json.dumps(ESQ))
        (d / "t.onnx").write_bytes(onnx_torre(dim=256))
        (d / "l2.chispa").write_bytes(formato.escribir({formato.L2: b"onnx-l2", formato.ESQUEMAS: struct.pack("<II", 256, 0)}))
        entrenar(None, d / "e.json", sys.argv[1], l2=str(d / "l2.chispa"), torre=d / "t.onnx", log=print)
