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

    def test_metadata_props_para_chispa_train(self):
        m = onnx.load(str(self.int8), load_external_data=False)
        props = {p.key: p.value for p in m.metadata_props}
        self.assertEqual(props["chispa.torre.dim"], "256")
        self.assertEqual(props["chispa.torre.max_len"], "128")
        self.assertEqual(props["chispa.torre.prefijo"], "passage: ")
        self.assertEqual(texto_opcion({"pregunta": "p", "descripciones": {}}, "o")[:len(props["chispa.torre.prefijo"])], props["chispa.torre.prefijo"])

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

    def test_max_len_configurable(self):
        out = self.d / "t256.onnx"
        E.exportar_torre(encoder_diminuto(), self.modelo.torre, out, self.d / "m", max_len=256)
        props = {p.key: p.value for p in onnx.load(str(out), load_external_data=False).metadata_props}
        self.assertEqual(props["chispa.torre.max_len"], "256")
        E.meta_consulta(out, 256)
        E.meta_consulta(out, 192)  # sustituye, no duplica
        props = [p for p in onnx.load(str(out), load_external_data=False).metadata_props if p.key == "chispa.consulta.max_len"]
        self.assertEqual([p.value for p in props], ["192"])

    def test_ids_torre_usa_el_max_tok_del_codificador(self):
        class Tok:
            def __call__(self, textos, truncation, max_length):
                self.max_length = max_length
                return {"input_ids": [[0] for _ in textos]}
        enc = type("E", (), {"tok": Tok(), "max_tok": 256})()
        E.ids_torre(enc, ["x"])
        self.assertEqual(enc.tok.max_length, 256)

    def test_cli_exige_ckpt(self):
        with self.assertRaises(SystemExit):
            E.main(["--torre-onnx", "x.onnx"])


FILAS_CALIB = [{"tipo": "choice", "split": "train", "pregunta": "¿Qué c%d?" % q, "opciones": ["a", "b", "c"],
                "descripciones": {"a": "da", "b": "db", "c": "dc"}} for q in range(10)]
IDS_CALIB = [[1, 5 + i, 9, 2] if i % 2 else [1, 7, 8 + i, 9, 10, 2] for i in range(24)]


class VariantesTorre(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(3)
        cls.modelo = ModeloL2().eval()
        cls.dir = tempfile.TemporaryDirectory()
        cls.d = Path(cls.dir.name)
        cls.out = {}
        for v in E.CUANT_TORRE:
            cls.out[v] = cls.d / (v + ".onnx")
            E.exportar_torre(encoder_diminuto(), cls.modelo.torre, cls.out[v], cls.d / v, cuant=v, ids_calib=IDS_CALIB)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_metadata_props_en_las_tres(self):
        for v, ruta in self.out.items():
            props = {p.key: p.value for p in onnx.load(str(ruta), load_external_data=False).metadata_props}
            self.assertEqual((props["chispa.torre.dim"], props["chispa.torre.max_len"], props["chispa.torre.prefijo"]), ("256", "128", "passage: "), v)

    def test_operadores_de_cada_variante(self):
        ops = {v: {n.op_type for n in onnx.load(str(r), load_external_data=False).graph.node} for v, r in self.out.items()}
        self.assertNotIn("MatMulInteger", ops["ninguna"])
        self.assertNotIn("QuantizeLinear", ops["ninguna"])
        self.assertIn("MatMulInteger", ops["dinamico"])
        self.assertIn("QuantizeLinear", ops["estatico"])
        self.assertIn("DequantizeLinear", ops["estatico"])
        self.assertNotIn("DynamicQuantizeLinear", ops["estatico"])

    def test_torre_en_fp32_en_el_estatico(self):
        g = onnx.load(str(self.out["estatico"]), load_external_data=False).graph
        torre = [n for n in g.node if n.name.startswith(E.PREFIJO_TORRE)]
        self.assertTrue(torre)
        self.assertEqual([n.name for n in torre if n.op_type in ("QuantizeLinear", "DequantizeLinear", "MatMulInteger")], [])

    def test_paridad_y_tamano(self):
        ids = [[1, 5, 9, 2], [1, 7, 2], [1, 6, 8, 9, 11, 2]]
        ref = E.correr_torre(E.sesion(self.out["ninguna"]), ids)
        for v in ("dinamico", "estatico"):
            c = E.cosenos(E.correr_torre(E.sesion(self.out[v]), ids), ref)
            self.assertGreater(float(c.min()), 0.95, v)
        self.assertLess(self.out["dinamico"].stat().st_size, self.out["ninguna"].stat().st_size)
        self.assertLess(self.out["estatico"].stat().st_size, self.out["ninguna"].stat().st_size)

    def test_ffn_estatico_y_fp16_de_la_torre(self):
        g = onnx.load(str(self.out["ffn-estatico"]), load_external_data=False).graph
        self.assertEqual([n.name for n in g.node if n.name.startswith(E.PREFIJO_TORRE) and n.op_type in ("QuantizeLinear", "DequantizeLinear")], [])
        self.assertIn("DequantizeLinear", {n.op_type for n in g.node})
        ids = [[1, 5, 9, 2], [1, 7, 2], [1, 6, 8, 9, 11, 2]]
        ref = E.correr_torre(E.sesion(self.out["ninguna"]), ids)
        for v in ("ffn-estatico", "fp16"):
            h = E.correr_torre(E.sesion(self.out[v]), ids)
            self.assertEqual(h.dtype, np.float32)
            self.assertGreater(float(E.cosenos(h, ref).min()), 0.95, v)
            self.assertLess(self.out[v].stat().st_size, self.out["ninguna"].stat().st_size)

    def test_ids_calib_consulta(self):
        filas = [{"texto": "hola %d" % i} for i in range(5)]
        ids = E.ids_calib_consulta(CodificadorDiminuto(), filas, 3)
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(E.ids_calib_consulta(CodificadorDiminuto(), FILAS_CALIB, 4)), 4)   # sin `texto`: los de torre

    def test_estatico_sin_calibracion_falla(self):
        with self.assertRaises(ValueError):
            E.exportar_torre(encoder_diminuto(), self.modelo.torre, self.d / "x.onnx", self.d / "x", cuant="estatico")

    def test_textos_calib_reparte_y_es_determinista(self):
        a = E.textos_calib(FILAS_CALIB, 7)
        self.assertEqual(a, E.textos_calib(FILAS_CALIB, 7))
        self.assertEqual(len(a), 7)
        self.assertEqual(len(E.textos_calib(FILAS_CALIB, 500)), 30)

    def test_cli_ffn_estatico_pide_calib(self):
        for flag in ("--cuant-torre", "--cuant"):
            with self.assertRaises(SystemExit):
                E.main(["--torre-onnx", str(self.d / "y.onnx"), "--ckpt-aleatorio", flag, "ffn-estatico"])

    def test_cli_estatico_pide_calib(self):
        with self.assertRaises(SystemExit):
            E.main(["--torre-onnx", str(self.d / "y.onnx"), "--ckpt-aleatorio", "--cuant-torre", "estatico"])

    def test_latencia_torre(self):
        r = E.latencia_torre(E.sesion(self.out["ninguna"]), IDS_CALIB[:6])
        self.assertEqual(r["n"], 6)
        self.assertLessEqual(r["p50_ms"], r["p99_ms"])


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
