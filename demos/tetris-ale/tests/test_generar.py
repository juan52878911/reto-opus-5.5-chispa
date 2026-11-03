import json
import os
import tempfile
import unittest

from tetris_ale import generar as G


class TestGenerar(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.info = G.generar(self.d.name, 400, semilla=3, max_piezas=15)
        leer = lambda f: [json.loads(l) for l in open(os.path.join(self.d.name, f), encoding="utf-8")]
        self.filas, self.blandas = leer("filas.jsonl"), leer("blandas.jsonl")

    def tearDown(self):
        self.d.cleanup()

    def test_cuenta_y_splits(self):
        self.assertEqual((len(self.filas), len(self.blandas)), (400, 400))
        self.assertEqual(sum(self.info["por_split"].values()), 400)
        self.assertGreater(self.info["por_split"]["dev"], 0)
        self.assertEqual(len({f["id"] for f in self.filas}), 400)
        # sin fugas: una misma partida (plantilla) no cae en dos splits
        sp = {}
        for f in self.filas:
            sp.setdefault(f["plantilla"], set()).add(f["split"])
        self.assertTrue(all(len(v) == 1 for v in sp.values()))

    def test_forma_de_la_fila(self):
        for f in self.filas:
            self.assertEqual((f["tipo"], f["pregunta"]), ("choice", G.PREGUNTA))
            self.assertIn(f["etiqueta"], f["opciones"])
            self.assertEqual(set(f["descripciones"]), set(f["opciones"]))
            self.assertTrue(f["texto"].startswith("Pieza "))
            self.assertTrue(all("huecos" in d for d in f["descripciones"].values()))
            for k in ("tarea", "idioma", "split", "fuente", "licencia", "uso_comercial"):
                self.assertIn(k, f)

    def test_blanda_es_softmax_y_la_etiqueta_es_la_mejor(self):
        for f, b in zip(self.filas, self.blandas):
            self.assertEqual(f["id"], b["id"])
            self.assertEqual(set(b["blanda"]), set(f["opciones"]))
            self.assertAlmostEqual(sum(b["blanda"].values()), 1.0, places=4)
            self.assertEqual(max(b["blanda"], key=b["blanda"].get) in (f["etiqueta"],), True) if len(
                set(b["blanda"].values())) == len(b["blanda"]) else None

    def test_softmax(self):
        p = G.softmax([0.0, 1.0], 1.0)
        self.assertAlmostEqual(p[1] / p[0], 2.718281828, places=5)
        self.assertGreater(G.softmax([0.0, 1.0], 0.1)[1], p[1])  # T baja = más afilada

    def test_etiquetas_repartidas_y_determinismo(self):
        self.assertGreaterEqual(len({f["etiqueta"] for f in self.filas}), 6)
        a = [x for x in G.filas(60, semilla=9, max_piezas=15)]
        b = [x for x in G.filas(60, semilla=9, max_piezas=15)]
        self.assertEqual(a, b)

    def test_el_ruido_cubre_estados_peores(self):
        alt = lambda r: int(r["texto"].split("altura ")[1].split(",")[0])
        sin = max(alt(f) for f, _ in G.filas(300, semilla=1, ruido=0.0, max_piezas=100))
        con = max(alt(f) for f, _ in G.filas(300, semilla=1, ruido=1.0, max_piezas=100))
        self.assertGreater(con, sin)


if __name__ == "__main__":
    unittest.main()
