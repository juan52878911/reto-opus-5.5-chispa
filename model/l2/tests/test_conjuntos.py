import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import torch

from model.l2 import conjunta as C
from model.l2 import datos as D
from model.l2 import evaluar as EV
from model.l2.modelo import ModeloL2, SoporteEval
from model.l2.tests.falso import CodificadorFalso, fila


def conjunto(corto, n, ops, split="train"):
    """Filas de `corto` con tarea compartida «intencion» y opciones propias."""
    out = []
    for i in range(n):
        r = fila(i, "choice", len(ops), "intencion")
        r.update(id="%s:%s:%d" % (corto, split, i), split=split, opciones=[corto + o for o in ops],
                 descripciones={corto + o: "d" for o in ops}, etiqueta=corto + ops[i % len(ops)])
        out.append(r)
    return out


class Conjuntos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        for corto in ("massive", "clinc150"):
            filas = conjunto(corto, 40, "abc") + conjunto(corto, 6, "abc", "test")
            (self.dir / (corto + ".jsonl")).write_text("\n".join(json.dumps(r) for r in filas))

    def test_conjunto_por_prefijo(self):
        self.assertEqual(D.conjunto({"id": "deepset:train:1", "tarea": "x"}), "inyecciones")
        self.assertEqual(D.conjunto({"id": "herr:test:1", "tarea": "herramientas"}), "herramientas")
        self.assertEqual(D.conjunto({"id": "otro:train:1", "tarea": "odio"}), "odio")

    def test_train_por_conjunto_no_mezcla(self):
        with mock.patch.object(EV, "RAIZ", self.dir):
            tr = EV.train_por_conjunto(self.dir)
        self.assertEqual(sorted(tr), ["clinc150", "massive"])
        for c, rs in tr.items():
            self.assertTrue(rs and all(r["id"].startswith(c + ":") for r in rs))
        sop = SoporteEval(tr, k=5)
        for c, rs in sop.filas.items():
            self.assertTrue(rs and all(r["id"].startswith(c + ":") for r in rs))

    def test_claves_igual_que_conjuntos_test(self):
        with mock.patch.object(EV, "RAIZ", self.dir):
            self.assertEqual(sorted(EV.train_por_conjunto(self.dir)), sorted(EV.conjuntos_test(self.dir)))

    def test_conjunta_usa_la_misma_agrupacion(self):
        with mock.patch.object(EV, "RAIZ", self.dir):
            t = C.cargar_tareas(str(self.dir))
        self.assertEqual(sorted(t), ["clinc150", "massive"])
        for c, (train, test) in t.items():
            self.assertTrue(all(r["id"].startswith(c + ":") for r in train + test))

    def test_predecir_con_soporte_separa_conjuntos_en_un_lote_mixto(self):
        torch.manual_seed(0)
        m, enc = ModeloL2(), CodificadorFalso()
        with mock.patch.object(EV, "RAIZ", self.dir):
            tr = EV.train_por_conjunto(self.dir)
        sop = SoporteEval(tr, k=5)
        mixto = [r for par in zip(conjunto("massive", 6, "abc", "dev"), conjunto("clinc150", 6, "abc", "dev")) for r in par]
        vistos = []
        orig = m.forward

        def espia(fs, enc, entrenar=True, protos=None):
            vistos.append(({D.conjunto(r) for r in fs}, protos))
            return orig(fs, enc, entrenar=entrenar, protos=protos)
        m.forward = espia
        preds = EV.predecir(m, enc, mixto, lote=64, soporte=sop)
        self.assertEqual([p["id"] for p in preds], [r["id"] for r in mixto])
        self.assertEqual(len(vistos), 2)
        for cs, protos in vistos:
            self.assertEqual(len(cs), 1)
            c = next(iter(cs))
            self.assertEqual(set(protos["intencion"][0]), {c + o for o in "abc"})

    def test_episodios_no_mezclan_conjuntos(self):
        filas = conjunto("massive", 60, "abc") + conjunto("clinc150", 60, "abc")
        ep = D.Episodios(filas, None, lote=8, k_min=2, k_max=4, frac_zeroshot=0.0, semilla=1)
        self.assertEqual(ep.tareas, ["clinc150", "massive"])
        for p in range(20):
            e = ep.paso(p)
            self.assertEqual(e["tarea"], "intencion")
            c = e["conjunto"]
            self.assertTrue(all(r["id"].startswith(c + ":") for r in e["soporte"] + e["filas"]))


if __name__ == "__main__":
    unittest.main()
