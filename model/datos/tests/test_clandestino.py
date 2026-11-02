import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from model.datos import clandestino, convertir, validar

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "clandestino"
MUESTRA = FIX / "clandestino_muestra.json"
Q = {1: "Question 1: In your opinion, will this text be harmful to anyone?", 3: "Question 3: In your opinion, does this text contain sexual content??",
     4: "Question 4: In your opinion, does this text refer to the given targeted groups?", 7: "Question 7: Does this sentence contain PII?",
     8: "Question 8: In your opinion, does this text contain fake information?"}


def anot(q1="1", q3="No", q4="21. No aplicable", q7="No", q8="No"):
    return {"Annotator": "A", Q[1]: q1, "Question 1.a: dialectos": "", Q[3]: q3, Q[4]: q4, "Question 4.a: otros": "", Q[7]: q7, Q[8]: q8}


def fila(key, anots, ia="False"):
    return {"Key": key, "Sentence": "texto inventado " + key, "IsAIGenerated": ia, "Index": 1, "Switch": "False", "Annotators": anots}


def escribe(d, filas, nombre="c.json"):
    p = Path(d) / nombre
    p.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n", encoding="utf-8")
    return p


def etiqueta(filas, key, tarea):
    r = [f["etiqueta"] for f in filas if f["plantilla"] == key and f["tarea"] == tarea]
    return r[0] if r else None


class Muestra(unittest.TestCase):
    def setUp(self):
        self.filas, self.info = clandestino.convertir(MUESTRA, min_grupo=1)

    def test_descarta_ia_y_pii(self):
        self.assertEqual((self.info["leidas"], self.info["descartadas_ia"], self.info["descartadas_pii"]), (19, 1, 2))
        claves = {f["plantilla"] for f in self.filas}
        self.assertEqual(len(claves), 16)
        self.assertFalse(claves & {"Sent_IA", "Sent_2", "Sent_3"})

    def test_mediana_y_redondeo(self):
        # Sent_8 (10 votos, 1 y 2 -> 1,5): 2; Sent_1: 2; Sent_15 (9 votos): 4; Sent_33 (12 votos, 1 y 2 -> 1,5): 2; Sent_30 (2 y 2): 2
        got = {k: etiqueta(self.filas, k, "clandestino_gravedad") for k in ("Sent_8", "Sent_1", "Sent_15", "Sent_33", "Sent_30")}
        self.assertEqual(got, {"Sent_8": "2", "Sent_1": "2", "Sent_15": "4", "Sent_33": "2", "Sent_30": "2"})

    def test_umbral_noul(self):
        # Sent_8: 1,5 -> false; Sent_14: 3 -> true; Sent_15: 4 -> true; Sent_1: 2 -> false
        got = {k: etiqueta(self.filas, k, "clandestino_danino") for k in ("Sent_8", "Sent_14", "Sent_15", "Sent_1")}
        self.assertEqual(got, {"Sent_8": "false", "Sent_14": "true", "Sent_15": "true", "Sent_1": "false"})

    def test_q3_q8_sin_mayoria_se_omiten(self):
        self.assertIsNone(etiqueta(self.filas, "Sent_1", "clandestino_sexual"))     # 4 Yes, 5 No, 2 Maybe de 11
        self.assertIsNone(etiqueta(self.filas, "Sent_15", "clandestino_falsa"))     # 4 Yes de 9
        self.assertEqual(etiqueta(self.filas, "Sent_5", "clandestino_sexual"), "true")     # 10 Yes de 11
        self.assertEqual(etiqueta(self.filas, "Sent_8", "clandestino_sexual"), "false")    # 10 No de 10
        self.assertEqual(etiqueta(self.filas, "Sent_8", "clandestino_falsa"), "false")     # 8 No de 10, Maybe no cuenta
        self.assertEqual(self.info["omitidas"]["clandestino_sexual"] + self.info["omitidas"]["clandestino_falsa"], 5)

    def test_grupos_de_multi(self):
        self.assertIn("Mujeres", self.info["grupos"])
        self.assertNotIn("No aplicable", self.info["grupos"])
        self.assertFalse([g for g in self.info["grupos"] if g[0].isdigit()])
        g = [f for f in self.filas if f["tarea"] == "clandestino_grupo_mujeres"]
        self.assertEqual(len(g), 16)
        self.assertEqual({f["etiqueta"] for f in g}, {"false", "true"})
        self.assertEqual(g[0]["pregunta"], "¿El mensaje se refiere al grupo «Mujeres»?")

    def test_ids_1_a_k_y_filas_validas(self):
        sc = [f for f in self.filas if f["tipo"] == "score"]
        self.assertEqual({tuple(f["opciones"]) for f in sc}, {("1", "2", "3", "4", "5")})
        self.assertEqual(set(sc[0]["descripciones"]), {"1", "2", "3", "4", "5"})
        self.assertTrue({f["etiqueta"] for f in sc} <= {"1", "2", "3", "4", "5"})
        self.assertEqual({tuple(f["opciones"]) for f in self.filas if f["tipo"] == "noul"}, {("false", "true")})
        self.assertEqual(validar.errores_conjunto(self.filas), [])
        self.assertTrue(all(f["licencia"] == "MIT" and f["uso_comercial"] is True and f["idioma"] == "es" for f in self.filas))
        self.assertTrue(all(f["pregunta"].startswith("¿") for f in self.filas))

    def test_una_plantilla_un_split(self):
        por = {}
        for f in self.filas:
            por.setdefault(f["plantilla"], set()).add(f["split"])
        self.assertTrue(all(len(s) == 1 for s in por.values()))

    def test_determinista(self):
        otra, _ = clandestino.convertir(MUESTRA, min_grupo=1)
        self.assertEqual(self.filas, otra)

    def test_directorio_y_convertir_fixtures(self):
        filas, _ = clandestino.convertir(FIX)
        self.assertTrue(filas)
        with tempfile.TemporaryDirectory() as d:
            res = convertir.convertir_fuentes(d, ("clandestino",), usar_fixtures=True)
            self.assertEqual(res["clandestino"]["estado"], "convertida")


class Sinteticas(unittest.TestCase):
    def conv(self, filas, **kw):
        with tempfile.TemporaryDirectory() as d:
            return clandestino.convertir(escribe(d, filas), **kw)

    def test_pii_de_un_solo_anotador_descarta(self):
        a = [anot() for _ in range(5)]
        a[2] = anot(q7="Yes")
        filas, info = self.conv([fila("K1", a), fila("K2", [anot(q7="Maybe")] * 5)])
        self.assertEqual((info["descartadas_pii"], {f["plantilla"] for f in filas}), (1, {"K2"}))

    def test_redondeo_de_la_mitad_hacia_arriba(self):
        filas, _ = self.conv([fila("K1", [anot("2"), anot("3")]), fila("K2", [anot("4"), anot("5")]), fila("K3", [anot("1"), anot("2")])])
        self.assertEqual([etiqueta(filas, k, "clandestino_gravedad") for k in ("K1", "K2", "K3")], ["3", "5", "2"])
        self.assertEqual(etiqueta(filas, "K1", "clandestino_danino"), "false")   # 2,5 < 3

    def test_mayoria_estricta_de_yes(self):
        mitad = [anot(q3="Yes")] * 2 + [anot(q3="No")] * 2
        filas, _ = self.conv([fila("K1", mitad), fila("K2", [anot(q8="Yes")] * 3 + [anot(q8="Maybe")] * 2)])
        self.assertIsNone(etiqueta(filas, "K1", "clandestino_sexual"))   # 2 de 4 no es mayoría estricta
        self.assertEqual(etiqueta(filas, "K2", "clandestino_falsa"), "true")   # 3 de 5

    def test_grupos_por_mayoria_sin_no_aplicable(self):
        a = [anot(q4="8. Mujeres;20. Otro")] * 3 + [anot(q4="8. Mujeres ; 7. LGBT+")] + [anot(q4="21. No aplicable")]
        filas, info = self.conv([fila("K1", a)], min_grupo=1)
        self.assertEqual(info["grupos"], ["Mujeres", "Otro"])
        self.assertEqual(etiqueta(filas, "K1", "clandestino_grupo_mujeres"), "true")
        self.assertEqual(etiqueta(filas, "K1", "clandestino_grupo_otro"), "true")
        filas, info = self.conv([fila("K1", [anot(q4="21. No aplicable")] * 5)], min_grupo=1)
        self.assertEqual(info["grupos"], [])

    def test_prefijo_y_clave_faltante(self):
        a = anot()
        del a[Q[7]]
        a["Question 7: texto distinto"] = "No"   # el texto completo no importa
        filas, _ = self.conv([fila("K1", [a])])
        self.assertTrue(filas)
        b = anot()
        del b[Q[8]]
        with self.assertRaises(ValueError) as cm:
            self.conv([fila("K1", [b])])
        self.assertIn("Question 8:", str(cm.exception))
        self.assertIn("Annotator", str(cm.exception))
        with self.assertRaises(ValueError) as cm:
            self.conv([{"Key": "K1", "Sentence": "x"}])
        self.assertIn("IsAIGenerated", str(cm.exception))
        self.assertIn("Sentence", str(cm.exception))

    def test_contar(self):
        r = clandestino.contar(MUESTRA)
        self.assertEqual((r["filas_leidas"], r["descartadas_ia"], r["descartadas_pii"]), (19, 1, 2))
        self.assertEqual(sum(r["distribucion_score"].values()), 16)
        self.assertEqual(sum(sum(c.values()) for c in r["filas_por_tipo_y_split"].values()), r["filas_validas"])
        json.dumps(r)


if __name__ == "__main__":
    unittest.main()
