import gzip
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from model.cascada import capas as C
from model.cascada import fixtures as F
from model.cascada.tests.falso import PotionFalso


class Capas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.datos = Path(cls.tmp.name) / "datos"
        F.crear_datos(cls.datos)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def cargar(self, t):
        return C.cargar_tarea(t, self.datos)

    def test_texto_opcion_como_l1_go(self):
        r = {"pregunta": "¿P?", "descripciones": {"a": "desc"}}
        self.assertEqual(C.texto_opcion(r, "a"), "¿P? · a · desc")
        self.assertEqual(C.texto_opcion(r, "b"), "¿P? · b")

    def test_l1_zs_choice_suma_uno_y_sigue_a_las_palabras(self):
        _, _, test = self.cargar("tarea_a")
        p = C.l1_zs(PotionFalso(), test)
        self.assertEqual(set(p), {r["id"] for r in test})
        for r in test[:5]:
            self.assertAlmostEqual(sum(p[r["id"]]["probs"].values()), 1.0)
            self.assertEqual(list(p[r["id"]]["probs"]), r["opciones"])

    def test_l1_zs_noul_usa_solo_el_coseno_de_true(self):
        _, _, test = self.cargar("tarea_b")
        p = C.l1_zs(PotionFalso(), test)
        for r in test[:5]:
            pr = p[r["id"]]["probs"]
            self.assertAlmostEqual(pr["true"] + pr["false"], 1.0)
            self.assertTrue(1 / (1 + np.exp(2)) <= pr["true"] <= 1 / (1 + np.exp(-2)))   # σ(4·cos−2) con cos ∈ [0, 1]

    def test_l1_zs_score_sin_opinion(self):
        r = {"id": "s", "tipo": "score", "opciones": ["1", "2", "3"], "pregunta": "?", "texto": "x", "descripciones": {}}
        p = C.l1_zs(PotionFalso(), [r])["s"]
        self.assertTrue(p["sin_opinion"])
        self.assertAlmostEqual(sum(p["probs"].values()), 1.0)

    def test_proto_acierta_y_clase_sin_train_usa_el_texto(self):
        train, _, test = self.cargar("tarea_c")
        self.assertNotIn("azul", {r["etiqueta"] for r in train})
        m = PotionFalso()
        protos = C.prototipos(m, train)
        for v in protos.values():
            self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0, places=5)
        p = C.l1_proto(m, train, test)
        for r in test:
            self.assertIn("azul", p[r["id"]]["probs"])
        ok = np.mean([max(p[r["id"]]["probs"], key=p[r["id"]]["probs"].get) == r["etiqueta"] for r in test if r["etiqueta"] != "azul"])
        self.assertGreater(ok, 0.9)

    def test_l0_reusa_si_hay_probs_y_recalcula_si_no(self):
        train, _, test = self.cargar("tarea_a")
        with tempfile.TemporaryDirectory() as d:
            p, origen = C.l0("tarea_a", train, test, d)
            self.assertEqual(origen, "recalculadas")
            ruta = Path(d) / "tarea_a__l0_tfidf_lr.jsonl.gz"
            with gzip.open(ruta, "wt") as f:
                f.writelines(json.dumps({"id": r["id"], "probs": {o: 0.25 for o in r["opciones"]}, "ms": 1.0}) + "\n" for r in test)
            p2, origen = C.l0("tarea_a", train, test, d)
            self.assertEqual(origen, "reusadas")
            self.assertEqual(p2[test[0]["id"]]["probs"][test[0]["opciones"][0]], 0.25)
            with gzip.open(ruta, "wt") as f:   # sin probs: se recalcula
                f.writelines(json.dumps({"id": r["id"], "ms": 1.0}) + "\n" for r in test)
            self.assertEqual(C.l0("tarea_a", train, test, d)[1], "recalculadas")

    def test_leer_l2(self):
        with tempfile.TemporaryDirectory() as d:
            F.crear_l2(d, self.datos)
            self.assertEqual(len(C.leer_l2(d, "tarea_a", True)), 60)
            self.assertEqual(len(C.leer_l2(d, "tarea_a", False)), 60)
            self.assertEqual(C.leer_l2(d, "no_existe", True), {})


if __name__ == "__main__":
    unittest.main()
