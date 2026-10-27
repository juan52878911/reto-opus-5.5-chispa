import json
import os
import re
import unittest

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SONDEO = os.path.join(os.path.dirname(AQUI), "sondeo")

OBLIG = {"id": str, "tarea": str, "tipo": str, "pregunta": str, "texto": str, "opciones": list,
         "descripciones": dict, "etiqueta": str, "idioma": str, "split": str, "fuente": str,
         "licencia": str, "uso_comercial": bool}


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


class TestHerramientas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = json.load(open(os.path.join(AQUI, "catalogo.json"), encoding="utf-8"))
        cls.test = leer(os.path.join(AQUI, "test.jsonl"))
        cls.train = leer(os.path.join(AQUI, "train.jsonl"))
        cls.ids = [c["id"] for c in cls.cat]

    def test_catalogo(self):
        self.assertGreaterEqual(len(self.cat), 30)
        self.assertEqual(len(set(self.ids)), len(self.ids))
        self.assertIn("escalate", self.ids)
        for c in self.cat:
            self.assertIn(c["tipo"], {"herramienta", "mcp", "agente"})
            self.assertTrue(c["descripcion"].strip())
        self.assertEqual(len({c["descripcion"] for c in self.cat}), len(self.cat))
        self.assertEqual({c["tipo"] for c in self.cat}, {"herramienta", "mcp", "agente"})

    def test_filas_validas(self):
        for r in self.test + self.train:
            for k, t in OBLIG.items():
                self.assertIsInstance(r.get(k), t, (r["id"], k))
            self.assertEqual(r["tarea"], "herramientas")
            self.assertEqual(r["tipo"], "choice")
            self.assertEqual(r["opciones"], self.ids)
            self.assertEqual(set(r["descripciones"]), set(self.ids))
            self.assertIn(r["etiqueta"], r["opciones"])
            self.assertIn(r["idioma"], {"es", "es-CO"})
            self.assertTrue(r["plantilla"])
            self.assertEqual(r["licencia"], "propia (Chispa)")
            self.assertIs(r["uso_comercial"], True)
            self.assertEqual(r["fuente"], "chispa T1.4")
            self.assertTrue(r["id"].startswith(f"herr:{r['split']}:"))

    def test_tamanos_y_splits(self):
        self.assertGreaterEqual(len(self.test), 300)
        self.assertTrue(all(r["split"] == "test" for r in self.test))
        self.assertTrue(all(r["split"] == "train" for r in self.train))
        for fs in (self.test, self.train):
            self.assertEqual(len({r["id"] for r in fs}), len(fs))
        cuenta = {i: 0 for i in self.ids}
        for r in self.train:
            cuenta[r["etiqueta"]] += 1
        self.assertEqual(set(cuenta.values()), {32})
        self.assertTrue(set(r["etiqueta"] for r in self.test) == set(self.ids))

    def test_escalate_y_colombiano(self):
        esc = sum(r["etiqueta"] == "escalate" for r in self.test)
        self.assertGreaterEqual(esc / len(self.test), 0.15)
        co = sum(r["idioma"] == "es-CO" for r in self.test)
        self.assertGreaterEqual(co / len(self.test), 0.2)

    def test_sin_solape_con_sondeo(self):
        previos = set()
        for f in os.listdir(SONDEO):
            if f.endswith(".jsonl"):
                previos |= {norm(r["texto"]) for r in leer(os.path.join(SONDEO, f))}
        for r in self.test + self.train:
            self.assertNotIn(norm(r["texto"]), previos, r["texto"])

    def test_sin_solape_train_test(self):
        self.assertFalse({norm(r["texto"]) for r in self.train} & {norm(r["texto"]) for r in self.test})
        self.assertFalse({r["plantilla"] for r in self.train} & {r["plantilla"] for r in self.test})

    def test_sin_textos_repetidos(self):
        for fs in (self.test, self.train):
            t = [norm(r["texto"]) for r in fs]
            self.assertEqual(len(t), len(set(t)))

    def test_generado_al_dia(self):
        import sys
        sys.path.insert(0, AQUI)
        import construir
        cat = construir.catalogo()
        self.assertEqual(cat, self.cat)
        self.assertEqual(construir.test(cat), self.test)
        self.assertEqual(construir.train(cat), self.train)


if __name__ == "__main__":
    unittest.main()
