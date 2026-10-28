import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from chispa import formato
from chispa.train import encontrar_go, encontrar_repo, entrenar
from tests import fixture_conjunta as fx
from tests.test_train import ESQ, ejemplos

REPO = encontrar_repo()


class TestFormatoConj(unittest.TestCase):
    def test_leer_ida_y_vuelta(self):
        secs = {formato.META: b"{}", formato.CONJ: b"abc"}
        self.assertEqual(formato.leer(formato.escribir(secs)), secs)

    def test_leer_rechaza_corrupcion(self):
        b = bytearray(formato.escribir({formato.META: b"{}"}))
        b[-1] ^= 1
        with self.assertRaises(ValueError):
            formato.leer(bytes(b))

    def test_hash_esquema_como_go(self):
        # Mismo hash que chispa3.HashEsquema("¿p?", ["a", "b"]) (lo comprueba el test de paridad de Go con la clave del fixture).
        self.assertEqual(len(formato.hash_esquema("¿p?", ["a", "b"])), 32)
        self.assertNotEqual(formato.hash_esquema("q", ["a", "b"]), formato.hash_esquema("q", ["b", "a"]))

    def test_cuantizar_protos(self):
        P = np.random.RandomState(1).randn(3, 4, 8)
        P /= np.linalg.norm(P, axis=-1, keepdims=True)
        esc, q = formato.cuantizar_protos(P)
        self.assertEqual(q.dtype, np.int8)
        self.assertLess(np.abs(q * esc[..., None] - P).max(), 0.5 * esc.max() + 1e-9)
        z = formato.cuantizar_protos(np.zeros((1, 1, 4)))[1]
        self.assertFalse(z.any())

    def test_tamano_150_clases(self):
        """Una tarea de 150 clases, 16 ranuras de 256: cabe en < 1 MB (int8 + una escala por ranura)."""
        C, K, D = 150, 16, 256
        P = np.random.RandomState(0).randn(C, K, D)
        P /= np.linalg.norm(P, axis=-1, keepdims=True)
        esc, q = formato.cuantizar_protos(P)
        b = formato.conj([{"hash": b"\0" * 32, "T": 0.05, "beta": 1.0, "esc": [1, 1, 1], "w": [1, 1, 1, 0, 0, 0],
                           "clases": [f"clase_{i:03d}" for i in range(C)], "escala": esc, "proto": q}])
        self.assertLess(len(b), 1 << 20)
        self.assertGreater(len(b), C * K * D)


@unittest.skipUnless(REPO, "sin repositorio")
class TestFixtureParidad(unittest.TestCase):
    def test_el_fixture_guardado_es_el_que_genera_conjunta_py(self):
        guardado = json.loads(fx.RUTA.read_text(encoding="utf-8"))
        nuevo = json.loads(json.dumps(fx.generar()))
        self.assertEqual(guardado["conj_b64"], nuevo["conj_b64"])
        for a, b in zip(guardado["casos"], nuevo["casos"]):
            np.testing.assert_allclose(a["probs"], b["probs"], atol=1e-9)
            np.testing.assert_allclose(a["sims"], b["sims"], atol=0)


@unittest.skipUnless(encontrar_go() and REPO, "sin Go o sin repositorio")
class TestTrainConjunta(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        with open(self.d / "ej.jsonl", "w") as f:
            for t, e in ejemplos():
                f.write(json.dumps({"texto": t, "etiqueta": e}) + "\n")
        # L2 falso: el entrenador solo copia las secciones L2 y ESQUEMAS.
        (self.d / "l2.chispa").write_bytes(formato.escribir({formato.L2: b"onnx", formato.ESQUEMAS: b"esq"}))
        from model.l2.modelo import ModeloL2
        from model.l2.tests.falso import CodificadorFalso
        import torch
        torch.manual_seed(0)
        self.modelo_enc = (ModeloL2(), CodificadorFalso())

    def correr(self, salida, **kw):
        return entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / salida, l2=str(self.d / "l2.chispa"),
                        log=lambda m: None, **kw)

    def test_conjunta_escribe_conj_y_sin_ella_el_fichero_no_cambia(self):
        sin = self.correr("sin.chispa")
        self.assertNotIn("CONJ", sin["secciones"])
        con = self.correr("con.chispa", conjunta=True, ckpt="falso", modelo_l2=self.modelo_enc)
        self.assertIn("CONJ", con["secciones"])
        self.assertEqual(con["conjunta"]["clases"], 2)
        a = formato.leer((self.d / "sin.chispa").read_bytes())
        b = formato.leer((self.d / "con.chispa").read_bytes())
        self.assertEqual(sorted(b), sorted([*a, formato.CONJ]))
        for t in a:
            if t != formato.CALIB:  # CALIB lleva la validación de L0, que no cambia; se compara igualmente abajo
                self.assertEqual(a[t], b[t], t)
        self.assertEqual(a[formato.CALIB], b[formato.CALIB])
        self.assertLess(len(b[formato.CONJ]), 1 << 20)
        # La sección es la de esta pregunta: hash de pregunta y opciones ordenadas.
        self.assertIn(formato.hash_esquema(ESQ["pregunta"], sorted(ESQ["opciones"])), [b[formato.CONJ][8:40]])

    def test_conjunta_pide_checkpoint_y_l2(self):
        from chispa.cliente import ChispaError
        with self.assertRaisesRegex(ChispaError, "--ckpt"):
            self.correr("x.chispa", conjunta=True)
        with self.assertRaisesRegex(ChispaError, "L2"):
            entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / "x.chispa", conjunta=True, modelo_l2=self.modelo_enc,
                     log=lambda m: None)
        self.assertFalse((self.d / "x.chispa").exists())


if __name__ == "__main__":
    unittest.main()
