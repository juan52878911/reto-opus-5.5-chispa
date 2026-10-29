import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from model.l1 import cabeza, comun, destilar, dorado

MODELO = Path(os.environ.get("CHISPA_L1_PROPIO", "/tmp/l1propio/d256/propio-256.chispa-l1"))


def exportador():
    spec = importlib.util.spec_from_file_location("exportar", comun.RAIZ / "runtime/l1/exportar.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class TokenizadorEstatico(unittest.TestCase):
    def test_lo_acepta_el_exportador(self):
        try:
            snap = comun.snapshot("intfloat/multilingual-e5-small")
        except IndexError:
            self.skipTest("falta el snapshot de HF en ~/hf: este test NO se ha ejecutado")
        tok = json.loads((Path(snap) / "tokenizer.json").read_text())
        t = comun.tokenizador_estatico(tok)
        self.assertTrue(exportador().validar_normalizador(t["normalizer"]))
        self.assertEqual(t["model"]["vocab"], tok["model"]["vocab"])


class Destilacion(unittest.TestCase):
    def test_pesos_sif(self):
        w = destilar.pesos_sif(np.array([-1.0, -5.0, -2.0, -9.0]))
        self.assertTrue((w > 0).all() and (w < 1).all())
        self.assertLess(w[0], w[2])            # más frecuente, menos peso
        self.assertLess(w[2], w[1])
        self.assertLess(w[1], w[3])

    def test_pca(self):
        rng = np.random.RandomState(0)
        x = rng.randn(200, 3) @ rng.randn(3, 10)
        r, comp, media = destilar.pca(x, 3)
        self.assertEqual(r.shape, (200, 3))
        self.assertTrue(np.allclose(r @ comp + media, x, atol=1e-8))      # rango 3: no se pierde nada


class Cabeza(unittest.TestCase):
    def datos(self):
        rng = np.random.RandomState(0)
        c = rng.randn(4, 16)
        y = np.repeat(np.arange(4), 20)
        x = c[y] + 0.7 * rng.randn(80, 16)
        return x / np.linalg.norm(x, axis=1, keepdims=True), y

    def test_aprende_del_maestro(self):
        x, y = self.datos()
        maestro = np.full((80, 4), 0.1)
        maestro[np.arange(80), y] = 0.7
        m = cabeza.entrenar(x, y, maestro, 4)
        p = cabeza.softmax(cabeza.logits(cabeza.descuantizar(cabeza.cuantizar(m)), x))
        self.assertGreater((p.argmax(1) == y).mean(), 0.9)
        self.assertAlmostEqual(p[np.arange(80), y].mean(), 0.7, delta=0.15)     # copia la confianza del maestro

    def test_cuantizar_vuelta(self):
        x, y = self.datos()
        m = cabeza.entrenar(x, y, np.eye(4)[y] * 0.9 + 0.025, 4, pasos=50)
        q = cabeza.cuantizar(m)
        self.assertEqual(q["P_q"].dtype, np.int8)
        d = cabeza.descuantizar(q)
        self.assertLess(np.abs(d["P"] - m["P"]).max(), np.abs(m["P"]).max() / 127)

    def test_maestro_jsonl(self):
        sop = [(0, {"id": "a", "texto": "x"}), (1, {"id": "b", "texto": "y"})]
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "m.jsonl"
            ruta.write_text('{"id": "a", "probs": {"u": 3, "v": 1}}\n{"id": "b", "probs": {"u": 0, "v": 2}}\n')
            p = cabeza.maestro_jsonl(str(ruta), sop, ["u", "v"])
            self.assertTrue(np.allclose(p, [[0.75, 0.25], [0, 1]]))
            ruta.write_text('{"id": "a", "probs": {"u": 1}}\n')
            with self.assertRaises(SystemExit):
                cabeza.maestro_jsonl(str(ruta), sop, ["u", "v"])


@unittest.skipUnless(MODELO.exists(), "falta el L1 propio exportado (python -m model.l1.destilar): este test NO se ha ejecutado")
class Dorado(unittest.TestCase):
    """El runtime Go da, bit a bit, lo que la referencia entera de Python (la que fija el hash dorado de go/)."""

    def test_go_igual_a_la_referencia(self):
        ref = dorado.Referencia(MODELO.parent, MODELO)
        frases = [r["texto"] for r in comun.leer(dorado.FRASES)][:300]
        x = comun.embeber(MODELO, frases, ref.dim)
        for t, e in zip(frases, x):
            self.assertEqual(ref.embed(t).tobytes(), e.tobytes(), t)

    def test_hash_dorado_guardado(self):
        ref = dorado.Referencia(MODELO.parent, MODELO)
        gold = json.loads((comun.AQUI / ("go/testdata/dorado-%d.json" % ref.dim)).read_text())
        self.assertEqual(gold["hash_cuerpo"], ref.hash_cuerpo)
        frases = [r["texto"] for r in comun.leer(dorado.FRASES)][:gold["n"]]
        self.assertEqual(gold["hash_embeddings"], dorado.hash_embeddings([ref.embed(t) for t in frases]))


if __name__ == "__main__":
    unittest.main()
