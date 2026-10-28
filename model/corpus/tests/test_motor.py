import sys
import types
import unittest
from unittest import mock

import torch  # noqa: F401  (antes de parchear sys.modules: torch no admite reimportarse)

from model.corpus import backends as B


class TokFalso:
    pad_token, eos_token, chat_template = None, "</s>", None


class ModFalso:
    def to(self, _):
        return self

    def eval(self):
        return self


def transformers_falso():
    m = types.ModuleType("transformers")
    m.AutoTokenizer = types.SimpleNamespace(from_pretrained=lambda _: TokFalso())
    m.AutoModelForCausalLM = types.SimpleNamespace(from_pretrained=lambda *a, **k: ModFalso())
    return m


class RespaldoVllm(unittest.TestCase):
    def crear(self, motor, llm):
        vllm = types.ModuleType("vllm")
        vllm.LLM = llm
        with mock.patch.dict(sys.modules, {"vllm": vllm, "transformers": transformers_falso()}), \
                mock.patch.object(B.Local, "_liberar_gpu") as liberar, mock.patch.object(B.Local, "_trabajar"), \
                mock.patch("builtins.print") as imprimir:
            return B.Local("modelo-falso", motor), liberar, imprimir

    def test_llm_que_lanza_cae_a_transformers(self):
        def llm(*a, **k):
            raise RuntimeError("sin memoria de GPU")
        b, liberar, imprimir = self.crear("auto", llm)
        self.assertEqual(b.motor, "transformers")
        self.assertIsNotNone(b.mod)
        liberar.assert_called_once()
        self.assertIn("sin memoria de GPU", imprimir.call_args[0][0])  # queda en el log

    def test_vllm_que_arranca_se_usa(self):
        b, liberar, _ = self.crear("auto", lambda *a, **k: object())
        self.assertEqual(b.motor, "vllm")
        liberar.assert_not_called()

    def test_motor_vllm_explicito_no_cae(self):
        def llm(*a, **k):
            raise RuntimeError("flashinfer sin nvcc")
        with self.assertRaises(RuntimeError):
            self.crear("vllm", llm)

    def test_transformers_no_toca_vllm(self):
        def llm(*a, **k):
            raise AssertionError("no debía crearse")
        b, _, _ = self.crear("transformers", llm)
        self.assertEqual(b.motor, "transformers")

    def test_liberar_gpu_vacia_la_cache(self):
        torch = types.ModuleType("torch")
        torch.cuda = mock.Mock()
        torch.cuda.is_available.return_value = True
        with mock.patch.dict(sys.modules, {"torch": torch}):
            B.Local._liberar_gpu()
        torch.cuda.empty_cache.assert_called_once()


class ModeloSegunMemoria(unittest.TestCase):
    def test_candidatos(self):
        self.assertEqual(B.candidatos_por_memoria(24), B.MODELOS_4B)    # A10G
        self.assertEqual(B.candidatos_por_memoria(None), B.MODELOS_4B)  # sin dato: prudente
        self.assertEqual(B.candidatos_por_memoria(40), B.MODELOS_DEFECTO)
        self.assertEqual(B.candidatos_por_memoria(80), B.MODELOS_DEFECTO)

    def elegir(self, gb, existentes):
        visto = []

        def info(m):
            visto.append(m)
            if m not in existentes:
                raise KeyError(m)
        hub = types.ModuleType("huggingface_hub")
        hub.HfApi = lambda: types.SimpleNamespace(model_info=info)
        with mock.patch.dict(sys.modules, {"huggingface_hub": hub}):
            return B.elegir_modelo(gb=gb), visto

    def test_a10g_elige_4b_sin_mirar_el_9b(self):
        m, visto = self.elegir(24, {"Qwen/Qwen3.5-9B-Instruct", "Qwen/Qwen3.5-4B"})
        self.assertEqual(m, "Qwen/Qwen3.5-4B")
        self.assertFalse([v for v in visto if "9B" in v or "8B" in v])

    def test_gpu_grande_elige_9b(self):
        m, _ = self.elegir(48, {"Qwen/Qwen3.5-9B-Instruct", "Qwen/Qwen3.5-4B"})
        self.assertEqual(m, "Qwen/Qwen3.5-9B-Instruct")

    def test_memoria_detectada(self):
        with mock.patch.object(B, "memoria_gpu_gb", return_value=24.0):
            self.assertEqual(B.candidatos_por_memoria(B.memoria_gpu_gb()), B.MODELOS_4B)


if __name__ == "__main__":
    unittest.main()
