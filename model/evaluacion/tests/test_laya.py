import json
import tempfile
import unittest
from pathlib import Path

from model.evaluacion import laya as L

B = L.B   # laya.py pone sdk/python en el path si hace falta

FIX = Path(__file__).parent / "fixtures" / "laya_tarjeta"


def fila(tipo, ops, desc=None, et=None, texto="hola", pregunta="¿Qué?"):
    return B._a_fila({"id": "t:test:1", "tipo": tipo, "pregunta": pregunta, "texto": texto, "opciones": ops, "descripciones": desc or {}, "etiqueta": et or ops[0]})


class Router:
    def __init__(self, resp):
        self.resp, self.llamadas = resp, []

    def predict(self, state, questions, model="multilingual", max_len=None):
        self.llamadas.append((state, questions, model, max_len))
        return {"answers": {L.PREGUNTA: self.resp}, "routing": {"model": model}}


class TestAdaptador(unittest.TestCase):
    def test_choice(self):
        f = fila("choice", ["a", "b", "c"], {"a": "la a", "b": "la b"})
        q, ids = L.pregunta_laya(f)
        self.assertEqual(q, {"type": "choice", "instructions": "¿Qué?", "criteria": {"a": "la a", "b": "la b", "c": "c"}})
        self.assertEqual(ids, ["a", "b", "c"])

    def test_noul(self):
        f = fila("noul", ["false", "true"], et="true")
        q, ids = L.pregunta_laya(f)
        self.assertEqual(q, {"type": "noul", "instructions": "¿Qué?"})
        self.assertEqual(L.leer_respuesta(f, {"noul": 0.5}, ids), ("true", {"false": 0.5, "true": 0.5}))
        self.assertEqual(L.leer_respuesta(f, {"noul": 0.49}, ids)[0], "false")
        self.assertAlmostEqual(L.leer_respuesta(f, {"noul": 0.9}, ids)[1]["true"], 0.9)

    def test_score_desordenado(self):
        f = fila("score", ["10", "2", "1"], {"1": "poco", "2": "algo", "10": "mucho"}, et="2")
        q, ids = L.pregunta_laya(f)
        self.assertEqual(ids, ["1", "2", "10"])   # por int, no por texto
        self.assertEqual(q["criteria"], ["poco", "algo", "mucho"])
        self.assertEqual(L.leer_respuesta(f, {"score": 3}, ids)[0], "10")   # el nivel 3 es el tercero ascendente
        self.assertEqual(L.leer_respuesta(f, {"choice": "algo"}, ids)[0], "2")
        self.assertEqual(L.leer_respuesta(f, {"score": 1, "distribution": [0.1, 0.6, 0.3]}, ids), ("1", {"1": 0.1, "2": 0.6, "10": 0.3}))

    def test_mapeo_de_ids(self):
        f = fila("choice", ["x", "y"], {"x": "equis", "y": "ye"})
        _, ids = L.pregunta_laya(f)
        self.assertEqual(L.leer_respuesta(f, {"choice": "y"}, ids), ("y", {"y": 1.0}))   # solo el id: confianza 1,0
        self.assertEqual(L.leer_respuesta(f, {"choice": "y", "confidence": 0.7}, ids)[1], {"y": 0.7})
        self.assertEqual(L.leer_respuesta(f, {"choice": "ye"}, ids)[0], "y")   # por descripción
        self.assertEqual(L.leer_respuesta(f, {"choice": "x", "probs": {"x": 0.8, "y": 0.2}}, ids)[1], {"x": 0.8, "y": 0.2})
        self.assertEqual(L.leer_respuesta(f, {"probs": {"x": 0.3, "y": 0.7}}, ids)[0], "y")
        with self.assertRaises(ValueError):
            L.leer_respuesta(f, {"choice": "z"}, ids)

    def test_decidir_y_metricas_de_la_bateria(self):
        r = Router({"choice": "a", "probs": {"a": 0.9, "b": 0.1}})
        f = fila("choice", ["a", "b"])
        x = L.decidir(r, f, "typed-decisions", vistas={}, max_len=2048)
        self.assertEqual(r.llamadas[0][2:], ("typed-decisions", 2048))
        m = B.agregar([x])
        self.assertEqual((m["exactitud"], m["f1_macro"], m["errores"]), (1.0, 1.0, 0.0))
        self.assertIsNotNone(m["p50_ms"])
        mal = L.decidir(Router({"choice": "zzz"}), f, "multilingual")
        self.assertTrue(mal["error"])

    def test_falso_devuelve_la_primera_opcion(self):
        for f, esperado in ((fila("choice", ["q", "r"]), "q"), (fila("noul", ["false", "true"]), "false"), (fila("score", ["3", "1", "2"]), "1")):
            self.assertEqual(L.decidir(L.RouterFalso(), f, "multilingual")["answer"], esperado)

    def test_reducir_determinista(self):
        xs = list(range(10))
        self.assertEqual(L.reducir(xs, 4), [0, 2, 5, 7])
        self.assertEqual(L.reducir(xs, 4), L.reducir(xs, 4))
        self.assertEqual(L.reducir(xs, None), xs)
        self.assertEqual(L.reducir(xs, 50), xs)

    def test_tope_por_velocidad(self):
        t, m = L.elegir_tope(0.01, [100, 100], 2, 0)
        self.assertIsNone(t)
        t, m = L.elegir_tope(1.0, [3000, 3000], 2, 100)   # no cabe entero: se recorta
        self.assertTrue(t and m <= L.MAX_MIN)
        t, _ = L.elegir_tope(60.0, [3000], 2, 0)   # ni con 50 filas
        self.assertIs(t, False)

    def test_tarjeta(self):
        t = L.leer_tarjeta((FIX / "README.md").read_text())
        self.assertEqual((t["license"], t["datasets"]), ("apache-2.0", ["ejemplo/datos-inventados"]))
        self.assertEqual([s["seccion"] for s in t["datos"]], ["Training data"])
        with tempfile.TemporaryDirectory() as d:
            L.main(["licencia", "--salida", d, "--tarjetas", str(FIX)])
            r = json.loads((Path(d) / "laya-licencia.json").read_text())
        self.assertEqual(r["checkpoints"]["english"]["license"], "apache-2.0")
        self.assertEqual(r["checkpoints"]["multilingual"]["license"], "cc-by-4.0")


if __name__ == "__main__":
    unittest.main()
