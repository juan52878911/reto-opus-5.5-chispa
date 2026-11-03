"""W15: el perfil fp16 deja en fp32 la normalización y la atención (en arm64 con fp16 nativo e5 desborda). Usa el e5 real de ~/hf
(pesos reales del codificador, torre aleatoria) y una poda de 57 000 ids, la del perfil movil (≈ 88 MB)."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import onnx
import torch
from onnx import TensorProto as TP

from model.l2 import exportar as E

E5 = "intfloat/multilingual-e5-small"
VOCAB_N = 57000
PALABRAS = "casa perro gato mesa libro cielo rio monte calle pan agua luz tren mar flor sol luna viento puerta ventana".split()


def cargar():
    from transformers import AutoModel, AutoTokenizer
    kw = dict(local_files_only=True)
    return AutoModel.from_pretrained(E5, attn_implementation="eager", **kw).eval(), AutoTokenizer.from_pretrained(E5, **kw)


def tipos_entrada(g):
    """{op_type: dtypes de la primera entrada} de los nodos de cómputo (sin los Cast)."""
    ty = {i.name: i.type.tensor_type.elem_type for i in g.input}
    ty.update({i.name: i.data_type for i in g.initializer})
    for n in g.node:
        if n.op_type == "Cast":
            ty[n.output[0]] = next(a.i for a in n.attribute if a.name == "to")
        elif n.op_type == "Constant":
            ty[n.output[0]] = n.attribute[0].t.data_type
    res = {}
    for n in g.node:
        if n.op_type != "Cast" and n.input and n.input[0] in ty:
            res.setdefault(n.op_type, set()).add(ty[n.input[0]])
            if n.op_type not in ("Shape", "Equal", "Where", "ConstantOfShape", "And", "GreaterOrEqual", "Range"):
                ty.update({o: ty[n.input[0]] for o in n.output})  # el resto conserva el tipo de su primera entrada
    return res


class Fp16Arm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            enc, cls.tok = cargar()
        except Exception as e:  # sin e5 en ~/hf
            raise unittest.SkipTest("sin e5 en ~/hf: %s" % e)
        cls.dir = tempfile.TemporaryDirectory()
        cls.d = Path(cls.dir.name)
        modelo = E.modelo_aleatorio()
        vocab = {"original": enc.get_input_embeddings().weight.shape[0], "ids_originales": list(range(VOCAB_N)), "unk": 3}
        cls.fp16 = cls.d / "torre-fp16.onnx"
        E.exportar_torre(enc, modelo.torre, cls.fp16, cls.d, vocab=vocab, cuant="fp16")
        cls.fp32 = cls.d / "torre-fp32.onnx"
        cls.puro = cls.d / "torre-fp16-puro.onnx"  # sin bloqueo: lo que ejecutaría un fp16 nativo
        E.a_fp16(cls.fp32, cls.puro, bloquear=())

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def ids(self, textos):
        return self.tok(["passage: " + t for t in textos], truncation=True, max_length=128)["input_ids"]

    def textos(self, n):
        rng = np.random.RandomState(0)
        return [" ".join(rng.choice(PALABRAS, rng.randint(3, 40))) for _ in range(n)]

    def test_ops_sensibles_en_fp32_y_pesos_en_fp16(self):
        g = onnx.load(str(self.fp16)).graph
        ty = tipos_entrada(g)
        for op in ("LayerNormalization", "Softmax", "Erf", "Div", "ReduceSum", "ReduceL2"):
            self.assertEqual(ty[op], {TP.FLOAT}, op)
        for op in set(E.OPS_FP32) & set(ty):
            self.assertEqual(ty[op], {TP.FLOAT}, op)
        self.assertEqual(ty["MatMul"], {TP.FLOAT16})
        self.assertEqual(ty["Gather"] & {TP.FLOAT16}, {TP.FLOAT16})  # la tabla de embeddings
        self.assertEqual([i.type.tensor_type.elem_type for i in g.input], [TP.INT64, TP.INT64])
        self.assertEqual([o.type.tensor_type.elem_type for o in g.output], [TP.FLOAT])
        pesos = [i for i in g.initializer if i.data_type == TP.FLOAT and np.prod(i.dims) > 100000]
        self.assertEqual(pesos, [])

    def test_puro_sin_bloqueo_si_esta_en_fp16(self):
        ty = tipos_entrada(onnx.load(str(self.puro)).graph)
        self.assertEqual(ty["LayerNormalization"], {TP.FLOAT16})
        self.assertEqual(ty["Softmax"], {TP.FLOAT16})

    def test_activaciones_grandes_dan_salida_finita(self):
        largo = self.ids([" ".join(PALABRAS) * 40, "tren " * 300, "x" * 2000])
        for ruta in (self.fp16, self.puro):  # el puro es la simulación: en ORT x86 también debe ser finito
            h = E.correr_torre(E.sesion(ruta), largo)
            self.assertTrue(np.isfinite(h).all(), ruta.name)
            np.testing.assert_allclose(np.linalg.norm(h, axis=1), 1.0, atol=1e-3)

    def test_coseno_con_fp32_en_50_textos(self):
        ids = self.ids(self.textos(50))
        ref, got = E.correr_torre(E.sesion(self.fp32), ids), E.correr_torre(E.sesion(self.fp16), ids)
        cos = (ref * got).sum(1) / (np.linalg.norm(ref, axis=1) * np.linalg.norm(got, axis=1))
        self.assertGreaterEqual(float(cos.min()), 0.999)

    def test_tamano(self):
        self.assertAlmostEqual(self.fp16.stat().st_size / 1e6, 88, delta=4)
        self.assertLess(self.fp16.stat().st_size, 0.6 * self.fp32.stat().st_size)


if __name__ == "__main__":
    unittest.main()
