import json
import os
import tempfile
import unittest

import torch

from model.evaluacion import chispa_eval as CE
from model.l2 import evaluar
from model.l2.modelo import Codificador, ModeloL2
from model.l2.tests.falso import CodificadorFalso, fila

HAY_E5 = bool(__import__("glob").glob(os.path.expanduser("~/hf/hub/models--intfloat--multilingual-e5-small/snapshots/*/config.json")))


@unittest.skipUnless(HAY_E5, "sin e5 en ~/hf")
class E5Real(unittest.TestCase):
    def test_cache_de_opciones_y_de_mensajes(self):
        os.environ["HF_HUB_OFFLINE"] = "1"
        enc = Codificador(cache_mensajes=True)
        a = enc.pasaje(["passage: ¿Qué quiere? · pedir · Pedir algo", "passage: otra"])
        b = enc.pasaje(["passage: ¿Qué quiere? · pedir · Pedir algo"])
        self.assertTrue(torch.equal(a[0], b[0]))
        self.assertEqual((enc.fallos, enc.aciertos), (2, 1))
        H, m = enc.tokens(["hola, quiero pedir", "adiós"])
        H2, m2 = enc.tokens(["adiós"])  # desde la caché de mensajes
        n = int(m[1].sum())
        self.assertEqual(H.shape[-1], 384)
        self.assertTrue(torch.allclose(H[1, :n], H2[0, :n]))


class Predecir(unittest.TestCase):
    def test_formato_y_chispa_eval(self):
        m, enc = ModeloL2(), CodificadorFalso()
        filas = [fila(i, "choice", 4) for i in range(6)] + [fila(10 + i, "noul") for i in range(4)] + [fila(20 + i, "score", k=3) for i in range(3)]
        for r in filas:
            r["split"] = "test"
        preds = evaluar.predecir(m, enc, filas, lote=5)
        self.assertEqual([p["id"] for p in preds], [r["id"] for r in filas])
        for r, p in zip(filas, preds):
            self.assertEqual(list(p["probs"]), r["opciones"])
            self.assertAlmostEqual(sum(p["probs"].values()), 1.0, places=9)
            self.assertGreaterEqual(p["ms"], 0)
        res = CE.evaluar(filas, json.loads(json.dumps(preds)))  # lo acepta el arnés
        self.assertEqual(res["global"]["n"], len(filas))
        d = evaluar.tabla_delta({"massive": res})
        self.assertIn("massive", d)


if __name__ == "__main__":
    unittest.main()
