import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
HF = Path.home() / "hf" / "hub" / "models--intfloat--multilingual-e5-small"


def tokenizador_local():
    snaps = sorted((HF / "snapshots").glob("*"))
    return snaps[-1] if snaps else None


def fila(i, n_opc, etiqueta=None, comercial=True, split="test"):
    ops = ["op%d" % k for k in range(n_opc)]
    return {"id": "t:%s:%d" % (split, i), "tarea": "intencion", "tipo": "choice", "pregunta": "¿Qué quiere?",
            "texto": "mensaje de prueba número %d" % i, "opciones": ops,
            "descripciones": {o: "descripción de %s" % o for o in ops}, "etiqueta": etiqueta or ops[0],
            "idioma": "es", "split": split, "fuente": "prueba", "licencia": "propia", "uso_comercial": comercial}


class Puros(unittest.TestCase):
    def test_bloques(self):
        from model.maestro.blandas import bloques
        for n in (1, 26, 27, 32, 151, 400):
            b = bloques(n)
            self.assertEqual([j for x in b for j in x], list(range(n)))
            self.assertTrue(all(len(x) <= 26 for x in b))
        self.assertEqual(len(bloques(151)), 6)

    def test_tope_y_muestreo(self):
        from model.maestro.blandas import muestreo, repartir_tope
        self.assertEqual(repartir_tope([10, 20], 0), [10, 20])
        t = repartir_tope([100, 300], 40)
        self.assertEqual(t, [10, 30])
        m = muestreo(list(range(100)), 10)
        self.assertEqual(len(m), 10)
        self.assertEqual(m, muestreo(list(range(100)), 10))
        self.assertGreater(m[-1], 85)


@unittest.skipUnless(tokenizador_local(), "falta un tokenizador en ~/hf")
class PuntaAPunta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        tok = AutoTokenizer.from_pretrained(tokenizador_local())
        cfg = AutoConfig.for_model("qwen3", vocab_size=len(tok), hidden_size=64, intermediate_size=128,
                                   num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2, head_dim=16,
                                   max_position_embeddings=4096)
        import torch
        torch.manual_seed(0)
        AutoModelForCausalLM.from_config(cfg).save_pretrained(t / "modelo")
        tok.save_pretrained(t / "modelo")
        filas = []
        for i in range(50):
            n = (3, 26, 27, 60)[i % 4]
            filas.append(fila(i, n, etiqueta="op%d" % (i % n), comercial=i % 10 != 9, split=("train", "dev", "test")[i % 3]))
        (t / "in.jsonl").write_text("".join(json.dumps(f) + "\n" for f in filas), encoding="utf-8")
        cls.t, cls.filas = t, filas

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def correr(self, *extra):
        r = subprocess.run([sys.executable, "-m", "model.maestro.blandas", "--entrada", str(self.t / "in.jsonl"),
                            "--salida", str(self.t / "out"), "--modelo", str(self.t / "modelo"), "--lote", "4", *extra],
                           cwd=RAIZ, capture_output=True, text=True, env={**__import__("os").environ, "PYTHONPATH": str(RAIZ)})
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        return r.stdout

    def test_1_completo(self):
        out = self.correr()
        d = self.t / "out"
        com = [json.loads(l) for l in (d / "in.jsonl").read_text().splitlines()]
        med = [json.loads(l) for l in (d / "in.solo-medir.jsonl").read_text().splitlines()]
        self.assertEqual(len(com) + len(med), 50)
        self.assertTrue(all(not f["uso_comercial"] for f in med) and med)
        for f in com + med:
            self.assertEqual(sorted(f["blanda"]), sorted(f["opciones"]))
            self.assertAlmostEqual(sum(f["blanda"].values()), 1.0, places=6)
            self.assertTrue(all(v >= 0 for v in f["blanda"].values()))
        grandes = [f for f in com if len(f["opciones"]) > 26]
        self.assertTrue(grandes)
        r = json.loads((d / "resumen.json").read_text())
        self.assertEqual(r["filas_total"], 50)
        self.assertIn("ece_maestro", r)
        self.assertTrue(any("intencion|test" in k for k in r["acuerdo_top1"]))
        self.assertGreater(r["filas_por_s"], 0)
        print(out[-600:])

    def test_2_reanuda(self):
        d = self.t / "out"
        antes = (d / "in.jsonl").read_text()
        out = self.correr()
        self.assertIn("0 pendientes", out)
        self.assertEqual((d / "in.jsonl").read_text(), antes)

    def test_3_tope(self):
        d = self.t / "out"
        import shutil
        shutil.rmtree(d)
        self.correr("--max-filas", "10")
        r = json.loads((d / "resumen.json").read_text())
        self.assertEqual(r["filas_total"], 10)


if __name__ == "__main__":
    unittest.main()
