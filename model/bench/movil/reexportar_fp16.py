"""Rehace un `.chispa` fp16 con la exportación segura para ARM (W15) sin checkpoint: cada ONNX fp16 (TORR y, si lo es, L2) se
sube a fp32 (exacto: los valores ya eran fp16) y se vuelve a bajar con `a_fp16`, que deja normalización y atención en fp32.

    python -m model.bench.movil.reexportar_fp16 viejo.chispa nuevo.chispa [--informe informe.json]

Comprueba, por cada ONNX, el coseno mínimo entre el fp32 subido y el nuevo en 100 secuencias de ids al azar (≥ 0,999)."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
from chispa import formato  # noqa: E402
from model.l2.exportar import OPS_FP32, a_fp16  # noqa: E402

F32, F16 = 1, 10


def _tensor_a_f32(t):
    from onnx import numpy_helper
    if t.data_type == F16:
        t.CopyFrom(numpy_helper.from_array(numpy_helper.to_array(t).astype(np.float32), t.name))


def a_fp32(m):
    """Inversa de `convert_float_to_float16` sobre el grafo (y subgrafos): pesos, constantes, Cast y tipos fp16 → fp32."""
    def tipos(vs):
        for v in vs:
            if v.type.tensor_type.elem_type == F16:
                v.type.tensor_type.elem_type = F32

    def grafo(g):
        for t in g.initializer:
            _tensor_a_f32(t)
        tipos(g.input)
        tipos(g.output)
        del g.value_info[:]
        for n in g.node:
            for a in n.attribute:
                if n.op_type == "Cast" and a.name == "to" and a.i == F16:
                    a.i = F32
                if a.type == a.TENSOR:
                    _tensor_a_f32(a.t)
                if a.type == a.GRAPH:
                    grafo(a.g)
                for sg in a.graphs:
                    grafo(sg)
    grafo(m.graph)
    return m


def tipos_bloqueados(m):
    """{op: nº de nodos} de los ops de OPS_FP32 cuya entrada principal es fp16 (debería quedar vacío tras `a_fp16`)."""
    import onnx
    inf = onnx.shape_inference.infer_shapes(m)
    tipo = {v.name: v.type.tensor_type.elem_type for v in list(inf.graph.value_info) + list(inf.graph.input) + list(inf.graph.output)}
    tipo.update({t.name: t.data_type for t in inf.graph.initializer})
    malos = {}
    for n in inf.graph.node:
        if n.op_type in OPS_FP32 and n.input and tipo.get(n.input[0]) == F16:
            malos[n.op_type] = malos.get(n.op_type, 0) + 1
    return malos


def _entradas(sess, n, rng, largo=24, vocab=3000):
    out = []
    for _ in range(n):
        d = {}
        for i in sess.get_inputs():
            forma = [1 if not isinstance(s, int) else s for s in i.shape]
            if len(forma) == 2:
                forma[1] = largo if not isinstance(i.shape[1], int) else i.shape[1]
            if "int" in i.type:
                v = rng.integers(5, vocab, size=forma) if "ids" in i.name else np.ones(forma)
                d[i.name] = v.astype(np.int64 if "int64" in i.type else np.int32)
            else:
                d[i.name] = rng.standard_normal(forma).astype(np.float32)
        out.append(d)
    return out


def coseno_min(ref: bytes, nuevo: bytes, n=100, semilla=1) -> float:
    import onnxruntime as ort
    a = ort.InferenceSession(ref, providers=["CPUExecutionProvider"])
    b = ort.InferenceSession(nuevo, providers=["CPUExecutionProvider"])
    peor = 1.0
    for d in _entradas(a, n, np.random.default_rng(semilla)):
        x = a.run(None, d)[0].astype(np.float64).ravel()
        y = b.run(None, d)[0].astype(np.float64).ravel()
        if not np.isfinite(y).all():
            return float("nan")
        peor = min(peor, float(x @ y / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-12)))
    return peor


def reexportar(onnx_bytes: bytes, nombre: str, informe: dict) -> bytes:
    import onnx
    m32 = a_fp32(onnx.load_from_string(onnx_bytes))
    with tempfile.TemporaryDirectory() as d:
        p32, p16 = Path(d) / "f32.onnx", Path(d) / "f16.onnx"
        onnx.save(m32, str(p32))
        a_fp16(p32, p16)
        nuevo, ref = p16.read_bytes(), p32.read_bytes()
    informe[nombre] = {"bytes_viejo": len(onnx_bytes), "bytes_nuevo": len(nuevo),
                       "bloqueados_en_fp16_viejo": tipos_bloqueados(onnx.load_from_string(onnx_bytes)),
                       "bloqueados_en_fp16_nuevo": tipos_bloqueados(onnx.load_from_string(nuevo)),
                       "coseno_min_fp32_vs_nuevo": coseno_min(ref, nuevo),
                       "coseno_min_fp32_vs_viejo": coseno_min(ref, onnx_bytes)}
    return nuevo


def es_onnx(b: bytes) -> bool:
    import onnx
    try:
        m = onnx.load_from_string(b)
        return len(m.graph.node) > 0
    except Exception:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("viejo")
    ap.add_argument("nuevo")
    ap.add_argument("--informe")
    a = ap.parse_args(argv)
    secs = formato.leer(Path(a.viejo).read_bytes())
    informe = {}
    t = formato.leer_torr(secs[formato.TORR])
    onnx_nuevo = reexportar(t["onnx"], "TORR", informe)
    secs[formato.TORR] = formato.torr(onnx_nuevo, t["dim"], t["max_len"], t["prefijo"], t["texto_torre"])
    if formato.L2 in secs and es_onnx(secs[formato.L2]):
        secs[formato.L2] = reexportar(secs[formato.L2], "L2", informe)
    else:
        informe["L2"] = "no es un ONNX: se copia tal cual"
    Path(a.nuevo).write_bytes(formato.escribir(secs))
    ok = all(isinstance(v, str) or (v["coseno_min_fp32_vs_nuevo"] >= 0.999 and not v["bloqueados_en_fp16_nuevo"]) for v in informe.values())
    informe["ok"] = ok
    texto = json.dumps(informe, ensure_ascii=False, indent=1)
    print(texto)
    if a.informe:
        Path(a.informe).write_text(texto + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
