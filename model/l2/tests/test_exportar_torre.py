import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import onnx
import torch

from model.l2 import exportar as E
from model.l2.modelo import ModeloL2, texto_opcion
from model.l2.tests.test_t24_exportar import CodificadorDiminuto, encoder_diminuto

FIXTURE = Path(__file__).parent / "fixtures_torre" / "torre.json"


class TorreOnnx(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(3)
        cls.modelo, cls.enc = ModeloL2().eval(), CodificadorDiminuto()
        cls.dir = tempfile.TemporaryDirectory()
        cls.d = Path(cls.dir.name)
        cls.int8 = cls.d / "torre-int8.onnx"
        E.exportar_torre(encoder_diminuto(), cls.modelo.torre, cls.int8, cls.d)
        cls.sess = E.sesion(cls.int8)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_nombres_y_forma(self):
        g = onnx.load(str(self.int8), load_external_data=False).graph
        self.assertEqual([i.name for i in g.input], ["input_ids", "attention_mask"])
        self.assertEqual([o.name for o in g.output], ["h"])
        self.assertEqual(onnx.load(str(self.int8), load_external_data=False).opset_import[0].version, 17)
        h = E.correr_torre(self.sess, [[1, 5, 9, 2], [1, 7, 2]])
        self.assertEqual(h.shape, (2, 256))
        np.testing.assert_allclose(np.linalg.norm(h, axis=1), 1.0, atol=1e-5)

    def test_gelu_exacta_y_torre_en_fp32(self):
        g = onnx.load(str(self.int8), load_external_data=False).graph
        ops = {n.op_type for n in g.node}
        self.assertIn("Erf", ops)
        self.assertNotIn("Tanh", ops)
        cuant = [n.name for n in g.node if n.name.startswith(E.PREFIJO_TORRE) and n.op_type in ("MatMulInteger", "DynamicQuantizeLinear")]
        self.assertEqual(cuant, [])
        self.assertTrue([n for n in g.node if n.name.startswith("/encoder/") and n.op_type == "MatMulInteger"])

    def test_relleno_apenas_cambia_h(self):
        # la escala dinámica de las activaciones int8 es por tensor: h depende un poco de qué más va en el lote (~1e-4)
        solo = E.correr_torre(self.sess, [[1, 5, 9, 2]])
        junto = E.correr_torre(self.sess, [[1, 5, 9, 2], [1, 7, 8, 9, 10, 11, 12, 2]])
        np.testing.assert_allclose(solo[0], junto[0], atol=1e-3)

    def test_paridad_con_pytorch(self):
        textos = ["passage: ¿Qué c? · op%d · desc op%d" % (i, i) for i in range(8)]
        c = E.cosenos(E.correr_torre(self.sess, E.ids_torre(self.enc, textos)), E.h_torch(self.modelo, self.enc, textos))
        self.assertGreater(float(c.min()), 0.98)

    def test_vocabulario_podado_comparte_tabla(self):
        vocab = {"ids_originales": list(range(0, 400)), "original": 1000, "unk": 3}
        podado = self.d / "podado.onnx"
        E.exportar_torre(encoder_diminuto(), self.modelo.torre, podado, self.d / "p", vocab)
        h = E.correr_torre(E.sesion(podado), [[1, 5, 900, 2]])  # 900 no está: pasa a <unk>
        h2 = E.correr_torre(E.sesion(podado), [[1, 5, 3, 2]])
        np.testing.assert_allclose(h, h2, atol=1e-5)
        self.assertLess(podado.stat().st_size, self.int8.stat().st_size)

    def test_textos_del_contrato(self):
        fila = {"pregunta": "¿P?", "descripciones": {"a": "da"}}
        self.assertEqual(texto_opcion(fila, "a"), "passage: ¿P? · a · da")
        self.assertEqual(texto_opcion(fila, "b"), "passage: ¿P? · b · ")

    def test_truncado_a_128(self):
        class Tok:
            def __call__(self, textos, truncation, max_length):
                self.max_length = max_length
                return {"input_ids": [[0] * 5 for _ in textos]}
        enc = type("E", (), {"tok": Tok()})()
        E.ids_torre(enc, ["x"])
        self.assertEqual(enc.tok.max_length, 128)

    def test_cli_exige_ckpt(self):
        with self.assertRaises(SystemExit):
            E.main(["--torre-onnx", "x.onnx"])


class FixtureGo(unittest.TestCase):
    def setUp(self):
        self.fx = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_tamano_y_forma(self):
        self.assertLessEqual(FIXTURE.stat().st_size, 200_000)
        fx = self.fx
        self.assertEqual(len(fx["textos"]), 20)
        self.assertEqual(len(fx["input_ids"]), 20)
        self.assertEqual(len(fx["h_fp32"]), 20)
        self.assertEqual(len(fx["h_onnx"][0]), fx["dim"])
        for t, ids in zip(fx["textos"], fx["input_ids"]):
            self.assertTrue(t.startswith("passage: "))
            self.assertLessEqual(len(ids), fx["max_tok"])
            self.assertEqual((ids[0], ids[-1]), (0, 2))  # <s> … </s>

    def test_h_normalizadas_y_cercanas(self):
        a, b = np.array(self.fx["h_fp32"]), np.array(self.fx["h_onnx"])
        np.testing.assert_allclose(np.linalg.norm(a, axis=1), 1.0, atol=1e-4)
        self.assertGreater(float(E.cosenos(a, b).min()), 0.99)

    def test_incluye_un_texto_truncado(self):
        self.assertIn(128, [len(i) for i in self.fx["input_ids"]])


if __name__ == "__main__":
    unittest.main()
