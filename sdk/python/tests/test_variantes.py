import copy
import random
import unittest

from chispa import variantes as V

CASO = {
    "texto": "Hola, quiero pagar con mi tarjeta pero el banco no acepta el pago.",
    "pregunta": "¿Cuál es la intención del cliente?",
    "kind": "choice",
    "opciones": [
        {"id": "pago", "description": "problema con un pago"},
        {"id": "saldo", "description": "consulta de saldo"},
        {"id": "otro", "description": "otra cosa"},
    ],
    "etiqueta": "pago",
}


def descr(c, id_):
    return next(o["description"] for o in c["opciones"] if o["id"] == id_)


class TestVariantes(unittest.TestCase):
    def test_no_modifica_el_original(self):
        c = copy.deepcopy(CASO)
        V.generar(c, V.TIPOS, 1)
        self.assertEqual(c, CASO)

    def test_determinista_y_semilla(self):
        self.assertEqual(V.generar(CASO, V.TIPOS, 7), V.generar(CASO, V.TIPOS, 7))
        self.assertNotEqual(V.generar(CASO, ["renombrar"], 1), V.generar(CASO, ["renombrar"], 2))
        # quitar tipos no cambia las demás variantes
        self.assertEqual(V.generar(CASO, V.TIPOS, 3)[1], V.generar(CASO, ["renombrar"], 3)[0])

    def test_conserva_significado_de_la_etiqueta(self):
        for sem in range(20):
            for v in V.generar(CASO, V.TIPOS, sem):
                self.assertEqual(v["mapa"]["pago"], v["etiqueta"], v["variante"])
                self.assertEqual(descr(v, v["etiqueta"]), "problema con un pago", v["variante"])
                self.assertEqual(sorted(o["description"] for o in v["opciones"]),
                                 sorted(o["description"] for o in CASO["opciones"]))
                self.assertEqual(len(set(o["id"] for o in v["opciones"])), 3)

    def test_permutar_cambia_orden_no_ids(self):
        ordenes = {tuple(o["id"] for o in V.permutar(CASO, random.Random(s))["opciones"])
                   for s in range(20)}
        self.assertGreater(len(ordenes), 1)
        self.assertTrue(all(sorted(o) == ["otro", "pago", "saldo"] for o in ordenes))

    def test_renombrar_ids_nuevos(self):
        v = V.generar(CASO, ["renombrar"], 0)[0]
        self.assertFalse({o["id"] for o in v["opciones"]} & {"pago", "saldo", "otro"})
        self.assertEqual(set(v["mapa"]), {"pago", "saldo", "otro"})

    def test_parafrasear_conserva_pregunta(self):
        v = V.generar(CASO, ["parafrasear"], 0)[0]
        self.assertNotEqual(v["pregunta"], CASO["pregunta"])
        self.assertIn("ntención del cliente?", v["pregunta"])
        self.assertEqual(v["texto"], CASO["texto"])

    def test_texto(self):
        e = V.generar(CASO, ["erratas"], 0)[0]["texto"]
        self.assertNotEqual(e, CASO["texto"])
        self.assertLessEqual(abs(len(e) - len(CASO["texto"])), 12)
        m = V.generar(CASO, ["mayusculas"], 0)[0]["texto"]
        self.assertEqual(m.lower(), CASO["texto"].lower())
        z = V.generar(CASO, ["mezcla"], 0)[0]["texto"]
        self.assertNotEqual(z, CASO["texto"])
        l = V.generar(CASO, ["largo"], 0)[0]["texto"]
        self.assertIn(CASO["texto"], l)
        self.assertGreater(len(l), 3 * len(CASO["texto"]))

    def test_score_sin_opciones(self):
        c = {"texto": "muy bueno", "pregunta": "¿Qué tan positivo es?", "kind": "score", "opciones": [], "etiqueta": 0.9}
        for v in V.generar(c, V.TIPOS, 0):
            self.assertEqual(v["etiqueta"], 0.9)

    def test_renombrar_multi_traduce_lista(self):
        c = dict(CASO, kind="multi", etiqueta=["pago", "saldo"])
        v = V.renombrar(c, random.Random(0))
        self.assertEqual(v["etiqueta"], [v["mapa"]["pago"], v["mapa"]["saldo"]])
        self.assertTrue(all(e.startswith("x") for e in v["etiqueta"]))

    def test_renombrar_identidad_en_noul_y_score(self):
        noul = {"texto": "t", "pregunta": "¿Es spam?", "kind": "noul", "etiqueta": "true",
                "opciones": [{"id": "true", "description": "sí"}, {"id": "false", "description": "no"}]}
        score = {"texto": "t", "pregunta": "¿Cuánto?", "kind": "score", "etiqueta": "2",
                 "opciones": [{"id": "1", "description": "poco"}, {"id": "2", "description": "mucho"}]}
        for c in (noul, score):
            for v in V.generar(c, V.TIPOS, 0):
                if v["variante"] == "renombrar":
                    self.assertEqual([o["id"] for o in v["opciones"]], [o["id"] for o in c["opciones"]])
                    self.assertEqual(v["etiqueta"], c["etiqueta"])

    def test_permutar_en_noul_conserva_etiqueta_por_id(self):
        noul = {"texto": "t", "pregunta": "¿Es spam?", "kind": "noul", "etiqueta": "true",
                "opciones": [{"id": "true", "description": "sí"}, {"id": "false", "description": "no"}]}
        ordenes = {tuple(o["id"] for o in V.permutar(noul, random.Random(s))["opciones"]) for s in range(20)}
        self.assertEqual(ordenes, {("true", "false"), ("false", "true")})
        self.assertTrue(all(V.permutar(noul, random.Random(s))["etiqueta"] == "true" for s in range(5)))

    def test_permutar_en_score_es_segura_y_documenta_el_invariante(self):
        score = {"texto": "t", "pregunta": "¿Qué tan urgente?", "kind": "score", "etiqueta": "2",
                 "opciones": [{"id": str(i), "description": f"nivel {i}"} for i in (1, 2, 3)]}
        self.assertIn("permutar", V.SEGURAS)
        ordenes = set()
        for s_ in range(20):
            v = V.permutar(score, random.Random(s_))
            ordenes.add(tuple(o["id"] for o in v["opciones"]))
            self.assertEqual(sorted(o["id"] for o in v["opciones"]), ["1", "2", "3"])
            self.assertEqual(v["etiqueta"], "2")
            self.assertEqual(v["mapa"], {"1": "1", "2": "2", "3": "3"})
        self.assertGreater(len(ordenes), 1)
        self.assertIn("ordena las opciones por id", V.permutar.__doc__)
        self.assertIn("ordena las opciones por id", V.__doc__)

    def test_largo_sin_negaciones_y_glosario_sin_ambiguas(self):
        for r in V.RELLENO:
            self.assertNotRegex(r.lower(), r"\b(no|sin|ni|nada)\b")
        self.assertFalse({"su", "tiempo", "cuenta", "pago"} & set(V.GLOSARIO))

    def test_riesgo_marcado(self):
        for v in V.generar(CASO, V.TIPOS, 0):
            self.assertEqual(v["riesgo"] is None, v["variante"] in V.SEGURAS, v["variante"])

    def test_parafrasear_en_ingles(self):
        c = dict(CASO, pregunta="What is the intent of the customer?")
        for s in range(10):
            p = V.generar(c, ["parafrasear"], s)[0]["pregunta"]
            self.assertIn("intent of the customer?", p)
            self.assertNotRegex(p, r"Dime|Necesito|Por favor|Sobre el|Con base")

    def test_tipo_desconocido(self):
        with self.assertRaises(ValueError):
            V.generar(CASO, ["nada"], 0)

    def test_estabilidad_a_mano(self):
        vs = [{"mapa": {"a": "x1", "b": "x2"}}, {"mapa": {"a": "a", "b": "b"}},
              {"mapa": {"a": "a", "b": "b"}}, {"mapa": {"a": "x9", "b": "x8"}}]
        orig = {"id": "a", "confianza": 0.8}
        rs = [{"id": "x1", "confianza": 0.7},   # estable, Δ 0.1
              {"id": "b", "confianza": 0.8},    # cambia, Δ 0
              {"id": "a", "confianza": 0.5},    # estable, Δ 0.3
              {"id": "x8", "confianza": 0.6}]   # cambia, Δ 0.2
        r = V.estabilidad(orig, vs, rs)
        self.assertEqual((r["n"], r["estables"]), (4, 2))
        self.assertAlmostEqual(r["pct_estable"], 50.0)
        self.assertAlmostEqual(r["delta_media"], 0.15)
        self.assertAlmostEqual(r["delta_p95"], 0.3)
        with self.assertRaises(ValueError):
            V.estabilidad(orig, vs, rs[:2])


if __name__ == "__main__":
    unittest.main()
