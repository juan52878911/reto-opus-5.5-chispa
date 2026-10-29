import tempfile
import unittest
from pathlib import Path

import numpy as np

from model.l2 import exportar as E
from model.l2.modelo import ModeloL2
from model.l2.tests.test_t24_exportar import VOCAB, CodificadorDiminuto, encoder_diminuto

TEXTOS = ["passage: " + t for t in ("¿Qué quiere hacer el usuario? · alarma · consultar las alarmas programadas",
                                    "Elige la intención que mejor describe lo que se le pide al asistente de la casa",
                                    "poner música relajante en el salón", "apaga todas las luces", "cuál es el tiempo mañana en Sevilla")]


def coseno(a, b):
    return (a * b).sum(1) / np.linalg.norm(a, axis=1) / np.linalg.norm(b, axis=1)


class PodaAmpliada(unittest.TestCase):
    """Con pesos aleatorios: fp32 con la poda ampliada frente a fp32 con el vocabulario completo, en textos sin <unk>, da coseno 1."""

    @classmethod
    def setUpClass(cls):
        cls.enc, cls.modelo = CodificadorDiminuto(), ModeloL2().eval()
        cls.dir = tempfile.TemporaryDirectory()
        cls.d = Path(cls.dir.name)
        b = cls.enc.tok(TEXTOS)
        cls.ids = [[int(i) for i, m in zip(x, mk) if m] for x, mk in zip(b["input_ids"], b["attention_mask"])]
        cls.base = {"modelo": "diminuto", "original": VOCAB, "unk": 3, "ids_originales": [0, 1, 2, 3, 4, 5]}
        txt = cls.d / "textos.txt"
        txt.write_text("\n".join(t[len("passage: "):] for t in TEXTOS), encoding="utf-8")
        cls.amplio, _ = E.ampliar_vocab(cls.enc, cls.base, [str(txt)])

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def h(self, nombre, vocab):
        ruta = self.d / (nombre + ".onnx")
        E.exportar_torre(encoder_diminuto(), self.modelo.torre, ruta, self.d / nombre, vocab, cuant="ninguna")
        return E.correr_torre(E.sesion(ruta), self.ids)

    def test_sin_unk_el_coseno_es_uno(self):
        keep = set(self.amplio["ids_originales"])
        self.assertEqual([i for x in self.ids for i in x if i not in keep], [])
        self.assertLess(len(keep), VOCAB)   # la poda recorta de verdad
        c = coseno(self.h("completo", None), self.h("ampliado", self.amplio))
        self.assertGreaterEqual(float(c.min()), 0.9999)

    def test_remap_y_tabla_podada(self):
        enc, remap = E.podar(encoder_diminuto(), self.amplio)
        ids = self.amplio["ids_originales"]
        self.assertEqual(enc.get_input_embeddings().weight.shape[0], len(ids))
        self.assertEqual(remap[ids].tolist(), list(range(len(ids))))
        fuera = [i for i in range(VOCAB) if i not in set(ids)]
        self.assertTrue((remap[fuera] == ids.index(3)).all())

    def test_la_caida_es_de_los_unk(self):
        # con la poda base (sin ampliar) los textos tienen <unk> y el coseno baja: lo que mide la poda es la cobertura del vocabulario
        c = coseno(self.h("completo", None), self.h("base", self.base))
        self.assertLess(float(c.min()), 0.9999)
