import json
import tempfile
import unittest
from pathlib import Path

from model.bench.torre import corpus_poda as CP

JEV = Path(__file__).resolve().parents[2] / "evaluacion" / "tests" / "fixtures" / "jevbench"


def textos(d):
    return {t for f in Path(d).glob("*.jsonl") for l in f.read_text(encoding="utf-8").splitlines() for t in CP._textos(json.loads(l))}


class CorpusPoda(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.d = Path(cls.dir.name)
        cls.res = CP.armar(cls.d, ("massive", "clinc150", "banking77"), fixtures=True, jevbench=JEV)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_ampliar_solo_train_en_espanol(self):
        for f in (self.d / "ampliar").glob("*.jsonl"):
            self.assertTrue(f.stat().st_size, f.name)
        self.assertEqual(sorted(p.stem for p in (self.d / "ampliar").glob("*.jsonl")), ["massive"])   # banking77 y clinc150 son en inglés: sin filas
        self.assertFalse((self.d / "ampliar" / "jevbench.jsonl").exists())

    def test_la_comprobacion_no_esta_en_el_corpus(self):
        comp = list((self.d / "comprobacion").glob("*.jsonl"))
        self.assertEqual(sorted(p.stem for p in comp), ["jevbench", "massive-test"])
        corpus = textos(self.d / "ampliar")
        for f in comp:
            for l in f.read_text(encoding="utf-8").splitlines():
                r = json.loads(l)
                self.assertNotIn(r.get("texto") or r.get("pregunta"), corpus)

    def test_resumen(self):
        self.assertTrue(json.loads((self.d / "resumen.json").read_text())["fuentes"]["jevbench"]["filas"] > 0)
        self.assertIn("massive-test", self.res["solapes_quitados_de_la_comprobacion"])

    def test_el_corpus_sirve_a_vocab_ampliar(self):
        from model.l2 import exportar as E
        self.assertGreater(len(E.textos_de(self.d / "ampliar")), 10)
