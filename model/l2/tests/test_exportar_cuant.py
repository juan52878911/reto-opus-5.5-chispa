import tempfile
import unittest
from pathlib import Path

import numpy as np
import onnx
import torch

from model.l2 import exportar as E
from model.l2.modelo import ModeloL2
from model.l2.tests.test_t24_exportar import CodificadorDiminuto, encoder_diminuto, filas_prueba


def cuantizados(ruta, prefijo):
    m = onnx.load(str(ruta), load_external_data=False)
    return [n.name for n in m.graph.node if n.name.startswith(prefijo) and n.op_type in ("MatMulInteger", "DynamicQuantizeLinear")]


class Cuantizacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(1)
        cls.dir = tempfile.TemporaryDirectory()
        cls.d = Path(cls.dir.name)
        E.exportar_onnx(E.Envoltura(encoder_diminuto(), ModeloL2().ranuras), cls.d / "fp32.onnx", 1000)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def cuant(self, modo, pc):
        sal = self.d / ("%s-%s.onnx" % (modo, pc))
        E.cuantizar(self.d / "fp32.onnx", sal, modo, pc)
        return sal

    def test_todo_cuantiza_las_ranuras(self):
        self.assertTrue(cuantizados(self.cuant("todo", False), E.PREFIJO_RANURAS))

    def test_codificador_deja_las_ranuras_en_fp32(self):
        for pc in (False, True):
            sal = self.cuant("codificador", pc)
            self.assertEqual(cuantizados(sal, E.PREFIJO_RANURAS), [])
            self.assertTrue(cuantizados(sal, "/encoder/"))
            self.assertLess(sal.stat().st_size, (self.d / "fp32.onnx").stat().st_size)

    def test_ninguna_copia_el_fp32(self):
        self.assertEqual(self.cuant("ninguna", False).read_bytes(), (self.d / "fp32.onnx").read_bytes())

    def test_modo_desconocido(self):
        with self.assertRaises(ValueError):
            E.cuantizar(self.d / "fp32.onnx", self.d / "x.onnx", "mitad")

    def test_fraccion_de_tokens_podados(self):
        enc, filas = CodificadorDiminuto(), filas_prueba()
        todo = {"original": 1000, "ids_originales": list(range(1000)), "unk": 3}
        self.assertEqual(E.fraccion_unk(enc, filas, todo), 0.0)
        nada = {"original": 1000, "ids_originales": [3], "unk": 3}
        self.assertGreater(E.fraccion_unk(enc, filas, nada), 0.5)

    def test_umbral_de_paridad(self):
        inf = {"cuant": "todo", "paridad": {"acuerdo_top1": 0.80, "dif_media": 0.004, "dif_max": 0.34}}
        with self.assertRaisesRegex(RuntimeError, "acuerdo top-1 0.800 < 0.950"):
            E.comprobar_paridad(inf, E.MIN_TOP1)
        E.comprobar_paridad(inf, 0.7)
        E.comprobar_paridad({}, E.MIN_TOP1)  # sin paridad medida no hay qué comprobar


if __name__ == "__main__":
    unittest.main()


IDS_CALIB = [[0, 5 + i, 9, 2] if i % 2 else [0, 7, 8 + i, 9, 10, 2] for i in range(24)]


def ops(ruta):
    return onnx.load(str(ruta), load_external_data=False).graph.node


class FfnEstaticoYFp16(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(1)
        cls.dir = tempfile.TemporaryDirectory()
        cls.d = Path(cls.dir.name)
        E.exportar_onnx(E.Envoltura(encoder_diminuto(), ModeloL2().ranuras), cls.d / "fp32.onnx", 1000)
        cls.ffn = cls.d / "ffn.onnx"
        E.cuantizar(cls.d / "fp32.onnx", cls.ffn, "ffn-estatico", True, ids_calib=IDS_CALIB)
        cls.f16 = cls.d / "fp16.onnx"
        E.cuantizar(cls.d / "fp32.onnx", cls.f16, "fp16")

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_nodos_que_entran(self):
        nombres = E.nodos_ffn(self.d / "fp32.onnx")
        self.assertTrue(all("/intermediate/dense/" in n or "/output/dense/" in n or n.endswith("word_embeddings/Gather") for n in nombres))
        self.assertFalse([n for n in nombres if "/attention/" in n])
        self.assertEqual(len([n for n in nombres if n.endswith("MatMul")]) % 2, 0)
        self.assertEqual(len(E.nodos_ffn(self.d / "fp32.onnx", embeddings=False)), len(nombres) - 1)

    def test_solo_las_ffn_estan_cuantizadas(self):
        nodos = ops(self.ffn)
        q = [n for n in nodos if n.op_type == "QuantizeLinear"]
        self.assertTrue(q)
        # los MatMul que quedan (atención y ranuras) siguen siendo float: ninguno consume un DequantizeLinear de pesos de la atención
        sal_dq = {n.output[0] for n in nodos if n.op_type == "DequantizeLinear"}
        for n in nodos:
            if n.op_type == "MatMul" and "/attention/" in n.name:
                self.assertFalse(sal_dq & set(n.input), n.name)
        self.assertEqual([n.name for n in nodos if n.name.startswith(E.PREFIJO_RANURAS) and n.op_type in ("QuantizeLinear", "DequantizeLinear")], [])
        self.assertLess(self.ffn.stat().st_size, (self.d / "fp32.onnx").stat().st_size)

    def test_ffn_sin_calibracion_falla(self):
        with self.assertRaises(ValueError):
            E.cuantizar(self.d / "fp32.onnx", self.d / "x.onnx", "ffn-estatico")

    def test_fp16_pesos_a_la_mitad_y_salida_fp32(self):
        fp32 = (self.d / "fp32.onnx").stat().st_size
        self.assertLess(self.f16.stat().st_size, 0.6 * fp32)
        g = onnx.load(str(self.f16), load_external_data=False).graph
        self.assertEqual(g.output[0].type.tensor_type.elem_type, onnx.TensorProto.FLOAT)
        self.assertEqual({i.name: i.type.tensor_type.elem_type for i in g.input}, {"input_ids": onnx.TensorProto.INT64, "attention_mask": onnx.TensorProto.INT64})

    def test_paridad_numerica(self):
        ids = np.array([[0, 5, 9, 2, 1], [0, 7, 2, 1, 1]])
        m = np.array([[1, 1, 1, 1, 0], [1, 1, 1, 0, 0]])
        ref = E.correr(E.sesion(self.d / "fp32.onnx"), ids, m)
        for r in (self.ffn, self.f16):
            got = E.correr(E.sesion(r), ids, m)
            self.assertEqual(got.dtype, np.float32)
            self.assertTrue(np.isfinite(got).all())
            self.assertLess(float(np.abs(got - ref).max()), 0.2, r.name)

    def test_vocab_ampliar_acepta_un_directorio(self):
        import json
        d = self.d / "corpus"
        d.mkdir()
        (d / "a.jsonl").write_text(json.dumps({"texto": "hola mundo"}) + "\n")
        (d / "b.txt").write_text("adiós\n\n")
        self.assertEqual(E.textos_de(d), ["hola mundo", "adiós"])
