import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from model.corpus import backends as B
from model.corpus import generar as G
from model.corpus import nucleo as N

HF = Path.home() / "hf" / "hub" / "models--intfloat--multilingual-e5-small"
PLANTILLA = ("{% for m in messages %}<|im_start|>{{ m.role }}\n{{ m.content }}<|im_end|>\n{% endfor %}"
             "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}")


def leer_resumen(d):
    with open(os.path.join(d, "resumen.json"), encoding="utf-8") as f:
        return json.load(f)


def tokenizador_local():
    snaps = sorted((HF / "snapshots").glob("*"))
    return snaps[-1] if snaps else None


class Puros(unittest.TestCase):
    def test_limpiar_salida(self):
        self.assertEqual(B.limpiar_salida('<think>\nrazono\n</think>\n{"textos": ["a"]}'), '{"textos": ["a"]}')
        self.assertEqual(B.limpiar_salida('{"textos": []} <think>cortado'), '{"textos": []}')
        self.assertEqual(B.limpiar_salida("<think>nunca cierra"), "")

    def test_parseo_tras_limpiar(self):
        crudo = '<think>\n\n</think>\n\nAquí va:\n```json\n{"textos": ["hola parce", "buenas"]}\n```'
        lista, _ = N.parsear_lista(B.limpiar_salida(crudo), "textos")
        self.assertEqual(lista, ["hola parce", "buenas"])

    def test_licencia_de_la_tarjeta(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(B.licencia_de_modelo(d))
            with self.assertRaises(RuntimeError):
                B.exigir_apache(d)
            Path(d, "README.md").write_text("---\nlicense: mit\n---\n# m\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                B.exigir_apache(d)
            Path(d, "README.md").write_text("---\nlicense: apache-2.0\nlibrary_name: transformers\n---\n", encoding="utf-8")
            self.assertEqual(B.exigir_apache(d), "Apache-2.0")

    def test_tope_de_minutos(self):
        g = N.Gasto(None, 8, 0, 0)
        g.permitir()
        g.vence = 0.0
        with self.assertRaises(N.TopeAlcanzado):
            g.permitir()
        self.assertTrue(g.parado)


@unittest.skipUnless(tokenizador_local(), "falta un tokenizador en ~/hf")
class ModeloDiminuto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import torch
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
        cls.tmp = tempfile.TemporaryDirectory()
        cls.m = os.path.join(cls.tmp.name, "modelo")
        tok = AutoTokenizer.from_pretrained(tokenizador_local())
        tok.chat_template = PLANTILLA
        cfg = AutoConfig.for_model("qwen3", vocab_size=len(tok), hidden_size=32, intermediate_size=64, num_hidden_layers=1,
                                   num_attention_heads=2, num_key_value_heads=1, head_dim=16, max_position_embeddings=8192)
        torch.manual_seed(0)
        AutoModelForCausalLM.from_config(cfg).save_pretrained(cls.m)
        tok.save_pretrained(cls.m)
        Path(cls.m, "README.md").write_text("---\nlicense: apache-2.0\n---\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def local(self):
        class Corto(B.Local):  # pesos aleatorios: nunca cierran la respuesta, se corta pronto
            def _generar(self, prompts, max_tokens, temp):
                return super()._generar(prompts, min(max_tokens, 8), temp)
        return Corto(self.m, "transformers", max_lote=4, espera=0.2)

    def test_formato_del_prompt(self):
        b = self.local()
        p = B.dar_formato(b.tok, "SISTEMA", "USUARIO")
        self.assertEqual(p, "<|im_start|>system\nSISTEMA<|im_end|>\n<|im_start|>user\nUSUARIO<|im_end|>\n<|im_start|>assistant\n")

    def test_llamadas_agrupadas(self):
        b = self.local()
        lotes = []
        orig = b._generar
        b._generar = lambda ps, mt, t: (lotes.append((len(ps), t)), orig(ps, mt, t))[1]
        res = [None] * 4

        def una(i):
            res[i] = b.llamar("s", "pregunta %d" % i, {}, 4096, 0.0 if i % 2 else 1.0)
        hs = [threading.Thread(target=una, args=(i,)) for i in range(4)]
        [h.start() for h in hs]
        [h.join(60) for h in hs]
        for texto, tin, tout in res:
            self.assertIsInstance(texto, str)
            self.assertGreater(tin, 0)
            self.assertTrue(0 < tout <= 8)
        self.assertEqual(sorted(n for n, _ in lotes), [2, 2])  # una tanda muestreada y otra de temperatura 0

    def correr(self, d, *extra):
        with mock.patch.object(G, "Local", lambda m, mo: self.local()), mock.patch.object(G, "dormir", lambda s: None), \
                mock.patch("builtins.print"):
            return G.main(["--tareas", "pqrs", "--por-clase", "2", "--salida", d, "--modelo", self.m, "--lote", "2",
                           "--hilos", "4", "--max-reintentos", "1", "--embeddings", "no", *extra])

    def test_main_local(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.correr(d), 0)  # backend local por defecto; las respuestas aleatorias no parsean
            r = leer_resumen(d)
            self.assertEqual((r["backend"], r["licencia_modelo"], r["motor"]), ("local", "Apache-2.0", "transformers"))
            self.assertEqual(r["fuente"], "chispa T1.3 (%s, local)" % self.m)
            self.assertEqual(r["usd_total"], 0)
            self.assertGreater(r["tokens_out"], 0)
            self.assertGreater(r["lotes_fallidos"], 0)

    def test_main_local_tope_min(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.correr(d, "--tope-min", "0.0000001"), 0)
            r = leer_resumen(d)
            self.assertTrue(r["parado_por_tope"])
            self.assertEqual(r["llamadas"], 0)

    def test_licencia_ajena_aborta(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "README.md").write_text("---\nlicense: other\n---\n", encoding="utf-8")
            with mock.patch("builtins.print"), self.assertRaises(RuntimeError):
                G.main(["--tareas", "pqrs", "--por-clase", "2", "--salida", os.path.join(d, "o"), "--modelo", d])


if __name__ == "__main__":
    unittest.main()
