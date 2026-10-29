import json
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from chispa import Multi, Resultado, formato
from chispa.cliente import ChispaError
from chispa.datos import cargar_ejemplos, cargar_esquema, etiquetas_multi, validar_multi
from chispa.multi import ajustar_sigmoide, mejor_theta, sufijo_esquema
from chispa.train import entrenar

ESQ = {"id": "temas", "pregunta": "¿Qué temas toca el mensaje?", "tipo": "multi",
       "opciones": {"cobro": "habla de factura o cobro", "envio": "habla de envio o paquete", "cortesia": "hola gracias"}}


def embeber_falso(textos):
    """L1 falso de dim 4: «factura» → eje 0, «envio» → eje 1, «hola» → eje 2."""
    E, ok = np.zeros((len(textos), 4), np.float32), np.ones(len(textos), bool)
    for i, t in enumerate(textos):
        E[i] = [("factura" in t) * 1.0, ("envio" in t) * 1.0, ("hola" in t) * 1.0, 0]
        ok[i] = bool(E[i].any())
        E[i] /= np.linalg.norm(E[i]) or 1
    return E, ok


FILAS = ([("factura cobro", "cobro")] * 6 + [("envio paquete", "envio")] * 6 + [("hola gracias", "cortesia")] * 5 +
         [("factura envio", "cobro|envio")] * 5 + [("hola factura", "cobro|cortesia")] * 4 + [("nada que ver", "")] * 3)


class TestEjemplosMulti(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        (self.d / "l1.bin").write_bytes(b"l1-falso")
        with open(self.d / "ej.csv", "w", encoding="utf-8") as f:
            f.write("texto,etiqueta\n")
            for t, e in FILAS:
                f.write(f'{t},{e}\n')

    def test_etiquetas_separadas_por_barra(self):
        self.assertEqual(etiquetas_multi("a|b"), ("a", "b"))
        self.assertEqual(etiquetas_multi(" a | a |b "), ("a", "b"))
        self.assertEqual(etiquetas_multi(""), ())
        self.assertEqual(etiquetas_multi(["x", "y"]), ("x", "y"))

    def test_csv_multi_y_celda_vacia(self):
        ex = cargar_ejemplos(self.d / "ej.csv", multi=True)
        self.assertEqual(len(ex), len(FILAS))
        self.assertIn(("factura envio", ("cobro", "envio")), ex)
        self.assertIn(("nada que ver", ()), ex)
        with self.assertRaises(ChispaError):  # sin multi la celda vacía sigue siendo un error
            cargar_ejemplos(self.d / "ej.csv")

    def test_validar_multi(self):
        q, _ = cargar_esquema(self.d / "e.json")
        self.assertEqual(q.kind, "multi")
        cuenta = validar_multi(cargar_ejemplos(self.d / "ej.csv", multi=True), q)
        self.assertEqual(cuenta["cobro"], 15)
        with self.assertRaises(ChispaError):
            validar_multi([("x", ("inventada",))], q)

    def test_esquema_multi_con_barra_en_un_id(self):
        malo = dict(ESQ, opciones=["a|b", "c"])
        (self.d / "m.json").write_text(json.dumps(malo))
        with self.assertRaises(ChispaError):
            cargar_esquema(self.d / "m.json")


class TestTrainMulti(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        (self.d / "l1.bin").write_bytes(b"l1-falso")
        with open(self.d / "ej.csv", "w", encoding="utf-8") as f:
            f.write("texto,etiqueta\n")
            for t, e in FILAS:
                f.write(f'{t},{e}\n')

    def correr(self, salida="m.chispa", ejemplos="ej.csv", **kw):
        kw.setdefault("log", lambda m: None)
        kw.setdefault("l1", self.d / "l1.bin")
        kw.setdefault("embeber", embeber_falso)
        return entrenar(self.d / ejemplos if ejemplos else None, self.d / "e.json", self.d / salida, usar_go=False, **kw)

    def test_few_shot_calibra_multi_y_escribe_soporte_sin_l0(self):
        inf = self.correr()
        self.assertEqual(inf["modo"], "few-shot")
        self.assertNotIn("L0", inf["secciones"])
        self.assertIn("L0", inf["omitidas"])
        self.assertIn("SOPL1", inf["secciones"])
        self.assertEqual(inf["soporte"]["k"], {"cobro": 15, "cortesia": 9, "envio": 11})
        secs = formato.leer((self.d / "m.chispa").read_bytes())
        calib = json.loads(secs[formato.CALIB])
        sfx = sufijo_esquema(cargar_esquema(self.d / "e.json")[0])
        m = calib["tipos"]["multi" + sfx]
        self.assertGreater(m["a"], 0)                      # más coseno, más probable
        self.assertTrue(0 < m["T"] and 0 <= m["theta"] <= 1)
        for o in ("cobro", "envio", "cortesia"):           # todas tienen positivos y negativos de sobra
            self.assertTrue(0.05 <= calib["tipos"]["multi" + sfx + "#" + o]["theta"] <= 0.95)
        self.assertNotIn("l1_lambda_calib", calib)         # multi no se calibró con encogimiento

    def test_la_sigmoide_ajustada_separa_positivos_de_negativos(self):
        inf = self.correr()
        a, b = inf["calib_multi"]["a"], inf["calib_multi"]["b"]
        p = lambda s: 1 / (1 + np.exp(-(a * s + b)))
        self.assertGreater(p(1.0), 0.9)
        self.assertLess(p(0.0), 0.1)

    def test_zero_shot_sin_ejemplos(self):
        inf = self.correr(ejemplos=None)
        self.assertEqual(inf["modo"], "zero-shot")
        calib = json.loads(formato.leer((self.d / "m.chispa").read_bytes())[formato.CALIB])
        self.assertEqual(calib["tipos"], {})               # el servidor usa la de noul como aproximación

    def test_sin_variacion_no_se_calibra(self):
        (self.d / "todo.csv").write_text("texto,etiqueta\nfactura,\nenvio,\n", encoding="utf-8")
        inf = self.correr(ejemplos="todo.csv")
        self.assertIn("CALIB multi", inf["omitidas"])
        calib = json.loads(formato.leer((self.d / "m.chispa").read_bytes())[formato.CALIB])
        self.assertEqual([k for k in calib["tipos"] if k.startswith("multi")], [])

    def test_etiqueta_desconocida_falla(self):
        (self.d / "mal.csv").write_text("texto,etiqueta\nfactura,inventada\n", encoding="utf-8")
        with self.assertRaises(ChispaError):
            self.correr(ejemplos="mal.csv")

    def test_calib_indexada_por_esquema(self):
        """R10-8: las claves de CALIB llevan el esquema; otro esquema con una opción homónima no las comparte."""
        self.correr()
        q, _ = cargar_esquema(self.d / "e.json")
        otro = Multi("otro", "¿Urgente?", ["cobro", "si"])
        self.assertNotEqual(sufijo_esquema(q), sufijo_esquema(otro))
        tipos = json.loads(formato.leer((self.d / "m.chispa").read_bytes())[formato.CALIB])["tipos"]
        self.assertNotIn("multi", tipos)
        self.assertNotIn("multi#cobro", tipos)
        self.assertTrue(all(k.split("#")[0] == "multi" + sufijo_esquema(q) for k in tipos), list(tipos))

    def test_avisa_de_sopl1_ignorado(self):
        """R10-12: el informe dice que el servidor ignora SOPL1 por defecto (sin l1_lambda_calib)."""
        inf = self.correr()
        self.assertTrue(any("IGNORA" in a and "SOPL1" in a for a in inf["avisos"]), inf["avisos"])

    def test_avisa_de_que_l2_no_opina_sin_multi_l2(self):
        """R10-5: con L2 y sin maxsim_l2 el informe explica que no hay multi_l2 y que L2 no opinará en multi."""
        (self.d / "l2.chispa").write_bytes(formato.escribir({formato.L2: b"l2", formato.ESQUEMAS: b"esq"}))
        inf = self.correr(l2=self.d / "l2.chispa")
        self.assertTrue(any("L2 NO opinará" in a for a in inf["avisos"]), inf["avisos"])
        self.assertIn("CALIB multi_l2", inf["omitidas"])

    def test_conjunta_no_es_para_multi(self):
        with self.assertRaises(ChispaError):
            self.correr(conjunta=True)

    def test_sin_soporte(self):
        inf = self.correr(sin_soporte=True)
        self.assertNotIn("SOPL1", inf["secciones"])


class TestAjuste(unittest.TestCase):
    def test_newton_recupera_la_sigmoide(self):
        rng = np.random.default_rng(0)
        s = rng.uniform(-1, 1, 4000)
        y = rng.random(4000) < 1 / (1 + np.exp(-(5 * s - 1)))
        a, b = ajustar_sigmoide(s, y)
        self.assertAlmostEqual(a, 5, delta=0.7)
        self.assertAlmostEqual(b, -1, delta=0.3)

    def test_theta_maximiza_f1(self):
        p = np.array([0.9, 0.8, 0.4, 0.3, 0.2, 0.1])
        y = np.array([1, 1, 1, 0, 0, 0])
        self.assertAlmostEqual(mejor_theta(p, y), 0.4)


class TestTiposMulti(unittest.TestCase):
    def test_constructor_valida(self):
        q = Multi("t", "¿Temas?", ["a", ("b", "desc")])
        self.assertEqual(q.kind, "multi")
        self.assertEqual(q.a_json()["options"], [{"id": "a"}, {"id": "b", "description": "desc"}])
        with self.assertRaises(ValueError):
            Multi("t", "¿?", ["a"])
        with self.assertRaises(ValueError):
            Multi("t", "¿?", ["a", "a"])

    def test_resultado_answers(self):
        r = Resultado.de_json({"id": "t", "kind": "multi", "answer": "a", "answers": ["a", "b"], "probs": {"a": .9, "b": .8, "c": .1},
                               "layer": "L1", "escalate": False, "ms": 1})
        self.assertEqual(r.answers, ["a", "b"])
        v = Resultado.de_json({"id": "t", "kind": "multi", "answer": "", "answers": [], "probs": {}, "layer": "L1", "escalate": False, "ms": 1})
        self.assertEqual(v.answers, [])
        c = Resultado.de_json({"id": "c", "kind": "choice", "answer": "a", "probs": {"a": 1.0}, "layer": "L0", "escalate": False, "ms": 1})
        self.assertIsNone(c.answers)


if __name__ == "__main__":
    unittest.main()


class TestCalibPorCapa(unittest.TestCase):
    """R9-5: la CALIB de L2 se ajusta con el MaxSim de L2 (otra escala), no con los cosenos de L1."""

    def test_multi_l2_se_ajusta_con_maxsim_y_multi_con_cosenos(self):
        from chispa.multi import calibrar_multi, sufijo_esquema
        import types
        ops = [types.SimpleNamespace(id=i, description="") for i in "ab"]
        q = types.SimpleNamespace(id="t", question="q", options=ops)
        ex = [("x%d" % i, ("a",) if i % 2 else ("b",)) for i in range(40)]
        rng = np.random.default_rng(0)
        def emb(textos):
            E = rng.normal(size=(len(textos), 4)); return E / np.linalg.norm(E, axis=1, keepdims=True), np.ones(len(textos), bool)
        Y = np.array([[o.id in es for o in ops] for _, es in ex], float)
        S = 20 * Y + 10 * (1 - Y)  # MaxSim en otra escala (10..20), no en [-1, 1]
        tipos, inf = calibrar_multi(q, ex, emb, lambda textos: (S, np.ones(len(textos), bool)))
        sfx = sufijo_esquema(q)
        self.assertNotIn("multi", tipos)  # R10-8: las claves llevan el esquema
        tipos = {k.replace(sfx, ""): v for k, v in tipos.items()}
        self.assertIn("multi_l2", tipos)
        self.assertGreater(abs(tipos["multi_l2"]["b"] - tipos["multi"]["b"]), 5)  # b distinto: otra escala
        p = 1 / (1 + np.exp(-(tipos["multi_l2"]["a"] * S + tipos["multi_l2"]["b"])))
        self.assertTrue(((p > 0.5) == (Y > 0)).mean() > 0.95)  # separa en la escala de L2
        q1 = 1 / (1 + np.exp(-(tipos["multi"]["a"] * S + tipos["multi"]["b"])))
        self.assertFalse(((q1 > 0.5) == (Y > 0)).mean() > 0.95)  # la de L1 aplicada a MaxSim no separa
        t2, _ = calibrar_multi(q, ex, emb)
        self.assertFalse([k for k in t2 if k.startswith("multi_l2")])  # sin maxsim_l2 no se inventa
