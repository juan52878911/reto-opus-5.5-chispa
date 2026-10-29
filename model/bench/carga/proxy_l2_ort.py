"""Proxy de L2 sin servidor: el ONNX int8 de e5 (+ranuras) con ONNX Runtime de Python, mensajes reales de massive.

Solo existe porque `chispa-server -tags ort` no compila en la VM (falta el módulo Go onnxruntime_go y no hay red).
Mide el codificador (lo que domina L2), no el servidor: sin HTTP, sin JSON, sin torres ni cascada.
Uso: proxy_l2_ort.py ONNX MENSAJES SEGUNDOS CONC...     → una línea JSON por concurrencia
"""
import json
import statistics
import sys
import threading
import time

import numpy as np
import onnxruntime as ort
from transformers import AutoTokenizer

onnx, msgs, seg = sys.argv[1], sys.argv[2], float(sys.argv[3])
tk = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-small", local_files_only=True)
textos = [l.strip() for l in open(msgs, encoding="utf-8") if l.strip()][:1000]
# e5 lleva «query: » delante (model/l2/modelo.py)
ids = [np.array([tk("query: " + t, truncation=True, max_length=128)["input_ids"]], dtype=np.int64) for t in textos]
so = ort.SessionOptions()
so.intra_op_num_threads = 1
sess = ort.InferenceSession(onnx, so, providers=["CPUExecutionProvider"])
for x in ids[:20]:
    sess.run(None, {"input_ids": x, "attention_mask": np.ones_like(x)})
print(json.dumps({"ort": ort.__version__, "tokens_medios": round(statistics.mean(x.shape[1] for x in ids), 1)}))
for c in map(int, sys.argv[4:]):
    lat, fin = [], time.time() + seg

    def trabajo(k):
        mine, i = [], k * 37
        while time.time() < fin:
            x = ids[i % len(ids)]
            i += 1
            t = time.perf_counter()
            sess.run(None, {"input_ids": x, "attention_mask": np.ones_like(x)})
            mine.append(time.perf_counter() - t)
        lat.extend(mine)

    ths = [threading.Thread(target=trabajo, args=(k,)) for k in range(c)]
    t0 = time.time()
    [t.start() for t in ths]
    [t.join() for t in ths]
    el = time.time() - t0
    lat.sort()
    print(json.dumps({"conc": c, "decisiones_s": round(len(lat) / el, 1), "p50_ms": round(lat[len(lat) // 2] * 1e3, 2),
                      "p99_ms": round(lat[int(.99 * (len(lat) - 1))] * 1e3, 2)}))
