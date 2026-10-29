import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from model.evaluacion import chispa_eval as CE
from model.evaluacion import profesor as P


def fila(i, tipo="choice", etq="a", ops=("a", "b", "c"), texto="hola", tarea="t"):
    if tipo == "noul":
        ops, etq = ("false", "true"), etq if etq in ("false", "true") else "true"
    return {"id": i, "tarea": tarea, "tipo": tipo, "pregunta": "¿Qué?", "texto": texto, "opciones": list(ops),
            "descripciones": {o: "desc " + o for o in ops}, "etiqueta": etq, "split": "test"}


class Falso:
    """Entailment alto cuando la hipótesis contiene la palabra «desc <texto>» (el texto es el nombre de la opción correcta)."""
    def __init__(self):
        self.vistos = []

    def logits(self, pares):
        self.vistos += pares
        return np.array([[4.0, -4.0] if ("desc " + p) in h else [-4.0, 4.0] for p, h in pares])


class TestProfesor(unittest.TestCase):
    def test_pares_y_plantillas(self):
        f = fila("1")
        self.assertEqual([o for o, _, _ in P.pares_fila(f, "card")], ["a", "b", "c"])
        h = P.hipotesis(f, "b", "card")
        self.assertIn("¿Qué?", h)
        self.assertIn("b: desc b", h)
        self.assertIn("This text is about", h)
        self.assertIn("El texto trata de", P.hipotesis(f, "b", "es"))
        n = fila("2", "noul")
        self.assertEqual([o for o, _, _ in P.pares_fila(n, "es")], ["true"])   # una sola hipótesis
        self.assertTrue(P.hipotesis(n, "true", "es").endswith("trata de desc true"))   # la descripción, sin «true: »

    def test_choice_suma_uno_y_acierta(self):
        fs = [fila("1", etq="b", texto="b"), fila("2", etq="c", texto="c")]
        preds = P.predecir(Falso(), fs, "card")
        for p, f in zip(preds, fs):
            self.assertAlmostEqual(sum(p["probs"].values()), 1.0, places=9)
            self.assertEqual(max(p["probs"], key=p["probs"].get), f["etiqueta"])
            self.assertGreaterEqual(p["ms"], 0)
        self.assertEqual(CE.evaluar(fs, preds)["global"]["exactitud"], 1.0)

    def test_noul_entailment_frente_a_contradiccion(self):
        p = P.probs_fila(fila("1", "noul"), [[2.0, -2.0]])
        self.assertAlmostEqual(p["true"] + p["false"], 1.0)
        self.assertGreater(p["true"], 0.9)
        p = P.probs_fila(fila("1", "noul"), [[-1.0, 1.0]])
        self.assertGreater(p["false"], 0.8)

    def test_score_mediana_la_pone_el_arnes(self):
        f = fila("1", "score", etq="3", ops=("1", "2", "3", "4"))
        probs = P.probs_fila(f, [[-4, 4], [-4, 4], [4, -4], [-4, 4]])
        self.assertEqual(CE.evaluar([f], [{"id": "1", "probs": probs}])["global"]["exactitud"], 1.0)
        self.assertEqual(sorted(probs), ["1", "2", "3", "4"])

    def test_tandas_cubren_todas_las_filas(self):
        fs = [fila(str(i), etq="a", texto="a", ops=("a", "b")) for i in range(11)]
        preds = P.predecir(Falso(), fs, "es", pares_por_tanda=5)
        self.assertEqual([p["id"] for p in preds], [f["id"] for f in fs])

    def test_plantilla_elegida_en_dev(self):
        class Solo(Falso):   # solo reconoce la plantilla en español
            def logits(self, pares):
                return np.array([[4.0, -4.0] if ("El texto trata" in h and ("desc " + p) in h) else [-4.0, 4.0] for p, h in pares])
        dev = {"d": [fila("1", etq="b", texto="b"), fila("2", etq="c", texto="c")]}
        mejor, pts = P.elegir_plantilla(Solo(), dev)
        self.assertEqual(mejor, "es")
        self.assertGreater(pts["es"], pts["card"])

    def test_medir_modelo_escribe(self):
        with tempfile.TemporaryDirectory() as d:
            fs = [fila("1", etq="b", texto="b"), fila("2", etq="c", texto="c")]
            res = P.medir_modelo(Falso(), {"x": fs}, {"x": fs}, d, log=lambda *a: None)
            self.assertEqual(res["conjuntos"]["x"]["exactitud"], 1.0)
            self.assertTrue((Path(d) / "pred" / "x.jsonl").exists())
            self.assertEqual(json.loads((Path(d) / "resultados.json").read_text())["plantilla"], res["plantilla"])

    def test_recortar_estable_y_repartido(self):
        fs = [dict(fila(f"{t}{i}", tarea=t)) for t in "ab" for i in range(10)]
        r = P.recortar(fs, 6)
        self.assertEqual(len(r), 6)
        self.assertEqual({x["tarea"] for x in r}, {"a", "b"})
        self.assertEqual([x["id"] for x in r], [x["id"] for x in P.recortar(fs, 6)])


if __name__ == "__main__":
    unittest.main()


class TestInforme(unittest.TestCase):
    def res(self, j, f1):
        c = {"jevbench": {"n": 231, "exactitud": j, "macro_f1": 0.3, "ms_medio": 100.0}}
        c.update({k: {"n": 10, "exactitud": v, "macro_f1": v, "ms_medio": 50.0} for k, v in f1.items()})
        return {"plantilla": "card", "dev_macro_f1": {}, "conjuntos": c}

    def test_veredicto(self):
        from model.evaluacion import profesor_informe as I
        bien = self.res(0.6, {"massive": 0.5, "hatecheck": 0.7, "inyecciones": 0.4, "tasksource_fuera": 0.2})
        self.assertTrue(I.veredicto(bien)[0])
        self.assertFalse(I.veredicto(self.res(0.5, {"massive": 0.5, "hatecheck": 0.7}))[0])           # JevBench corto
        self.assertFalse(I.veredicto(self.res(0.6, {"massive": 0.5, "hatecheck": 0.55}))[0])           # solo 1 de 4
        txt = I.informe({"bge-m3-zeroshot-c": bien}, minutos=60)
        self.assertIn("SE CUMPLE", txt)
        self.assertIn("USD", txt)
        self.assertIn("destilable", txt)
