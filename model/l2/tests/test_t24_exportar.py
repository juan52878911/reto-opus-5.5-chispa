import json
import os
import subprocess
import tempfile
import unittest
from collections import OrderedDict
from pathlib import Path

import numpy as np
import torch
from transformers import BatchEncoding, BertConfig, BertModel

from model.l2 import calibrar as C
from model.l2 import exportar as E
from model.l2.modelo import Codificador, ModeloL2
from model.l2.tests.falso import fila

VOCAB = 1000


class TokDiminuto:
    """Palabras → ids por hash; 0 es relleno, 1 inicio."""

    def __call__(self, textos, padding=True, truncation=True, max_length=32, return_tensors="pt"):
        ids = [[1] + [2 + sum(map(ord, w)) % (VOCAB - 2) for w in t.split()][:max_length - 1] for t in textos]
        n = max(map(len, ids))
        return BatchEncoding({"input_ids": torch.tensor([i + [0] * (n - len(i)) for i in ids]),
                              "attention_mask": torch.tensor([[1] * len(i) + [0] * (n - len(i)) for i in ids])})


def encoder_diminuto():
    torch.manual_seed(0)
    cfg = BertConfig(vocab_size=VOCAB, hidden_size=384, num_hidden_layers=1, num_attention_heads=4, intermediate_size=64,
                     max_position_embeddings=64, pad_token_id=0, attn_implementation="eager")
    return BertModel(cfg, add_pooling_layer=False).eval()


class CodificadorDiminuto(Codificador):
    def __init__(self):
        self.enc, self.tok, self.device, self.max_tok = encoder_diminuto(), TokDiminuto(), "cpu", 32
        self.cache, self.cache_max, self.aciertos, self.fallos, self.msgs = OrderedDict(), 1000, 0, 0, None


def filas_prueba():
    fs = []
    for i in range(6):
        fs += [fila(i, "choice", 4, tarea="c"), fila(i, "noul", tarea="n"), fila(i, "score", k=5, tarea="s")]
    for r in fs:
        r["split"] = "dev"
    return fs


def calib_prueba(modelo, enc, filas):
    inf = C.calibrar(modelo, enc, filas)
    inf["chispa"] = C.a_calib_chispa(inf)
    return inf


class Exportacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(1)
        cls.modelo, cls.enc = ModeloL2().eval(), CodificadorDiminuto()
        cls.filas = filas_prueba()
        cls.calib = calib_prueba(cls.modelo, cls.enc, cls.filas)
        cls.dir = tempfile.TemporaryDirectory()
        d = Path(cls.dir.name)
        cls.vocab = {"original": VOCAB, "ids_originales": list(range(0, VOCAB, 2)) + [1, 3], "unk": 3}
        cls.vocab["ids_originales"] = sorted(set(cls.vocab["ids_originales"]))
        cls.chispa = d / "l2.chispa"
        cls.inf = E.construir(cls.modelo, cls.enc, cls.enc.enc, {}, cls.calib, cls.filas, cls.chispa, d / "w", None,
                              cls.filas, latencias=(16, 32))

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_paridad_en_modelo_diminuto(self):
        p = self.inf["paridad"]
        self.assertEqual(p["n"], len(self.filas))
        self.assertLessEqual(p["dif_media"], 0.01)
        # modelo al azar: probabilidades casi planas, el top-1 cambia con empates de 1e-3
        self.assertGreaterEqual(p["acuerdo_top1"], 0.8)

    def test_onnx_fp32_igual_que_torch(self):
        import onnxruntime as ort
        enc = self.enc
        b = enc.tok(["query: hola mundo cruel", "query: hola"], return_tensors="pt")
        with torch.no_grad():
            H = enc.enc(**b).last_hidden_state
            S = self.modelo.ranuras(H, b["attention_mask"].bool())
        sess = ort.InferenceSession(str(Path(self.dir.name) / "w" / "l2-fp32.onnx"), providers=["CPUExecutionProvider"])
        got = E.correr(sess, b["input_ids"].numpy(), b["attention_mask"].numpy())
        self.assertEqual(got.shape, (2, 16, 256))
        self.assertLess(float(np.abs(got - S.numpy()).max()), 1e-4)

    def test_latencia_y_tamano(self):
        self.assertEqual(set(self.inf["latencia_1_hilo"]), {"16", "32"})
        self.assertGreater(self.inf["l2_mb"], 0)
        self.assertLess(self.inf["l2_mb"], self.inf["fp32_mb"])
        self.assertEqual(self.inf["torres"], 4 + 2)  # 4 opciones de la pregunta choice + noul + score (únicas)

    def test_poda_conserva_lo_conservado(self):
        enc2, remap = E.podar(self.enc.enc, self.vocab)
        ids = self.vocab["ids_originales"]
        self.assertEqual(enc2.get_input_embeddings().weight.shape[0], len(ids))
        self.assertEqual(int(remap[0]), 0)
        self.assertEqual(int(remap[7]), ids.index(3))  # id fuera → <unk>
        env = E.Envoltura(enc2, self.modelo.ranuras, remap).eval()
        orig = E.Envoltura(self.enc.enc, self.modelo.ranuras).eval()
        x = torch.tensor([[1, 2, 4, 10, 0]])
        m = torch.tensor([[1, 1, 1, 1, 0]])
        with torch.no_grad():
            self.assertTrue(torch.allclose(env(x, m), orig(x, m), atol=1e-6))
        with self.assertRaises(ValueError):
            E.podar(self.enc.enc, {**self.vocab, "original": 5})

    def test_choques_de_torre(self):
        mal = [dict(self.filas[0]), dict(self.filas[0])]
        mal[1]["descripciones"] = {o: "otra " + o for o in mal[1]["opciones"]}
        with self.assertRaises(ValueError):
            E.entradas_torres(self.modelo, self.enc, mal)

    def test_ida_y_vuelta_con_go(self):
        d = Path(self.dir.name)
        torres = E.entradas_torres(self.modelo, self.enc, self.filas)
        # las torres cuantizadas se parecen a las de punto flotante
        for p, o, q, esc in torres[:3]:
            self.assertLessEqual(int(np.abs(q).max()), 127)
            self.assertAlmostEqual(float(np.linalg.norm(q.astype(np.float32) * esc)), 1.0, delta=0.05)
        esp = d / "esperado.json"
        esp.write_text(json.dumps({
            "tau": self.calib["chispa"]["tau_escalate"], "dim": 256, "l2_bytes": (d / "w" / "l2-int8.onnx").stat().st_size,
            "tipos": list(self.calib["chispa"]["tipos"]), "torres": E.esquemas_json(torres, 256)["entradas"]}))
        env = {**os.environ, "CHISPA_FICHERO": str(self.chispa), "CHISPA_ESPERADO": str(esp), "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
        p = subprocess.run([E.go_bin(), "test", "-count=1", "-run", "TestFicheroDePython", "-v", "."], cwd=E.GO_DIR, env=env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("SKIP", p.stdout)

    def test_empaquetar_apaga_el_go_work(self):
        """Con un go.work en la raíz (paquete del SDK) `-mod=mod` fallaba: la llamada a Go debe llevar GOWORK=off."""
        from unittest import mock
        visto = {}

        def falso(cmd, **kw):
            visto.update(kw["env"])
            return subprocess.CompletedProcess(cmd, 0, "", "")
        with mock.patch.dict(os.environ, {"GOWORK": "/x/go.work"}), mock.patch.object(E.subprocess, "run", falso):
            E.empaquetar({}, "a.onnx", {}, {}, "s.chispa")
        self.assertEqual(visto["GOWORK"], "off")
        self.assertEqual(visto["GOFLAGS"], "-mod=mod")


if __name__ == "__main__":
    unittest.main()
