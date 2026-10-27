import json
import os
import tempfile
import unittest
from unittest import mock

from model.corpus import generar as G
from model.corpus import nucleo as N
from model.corpus import tareas as T


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


class TestTareas(unittest.TestCase):
    def test_clases(self):
        t = T.tareas()
        self.assertEqual(set(t), {"whatsapp_comercio", "pqrs", "fintech", "herramientas"})
        self.assertEqual(set(t["whatsapp_comercio"]["opciones"]), {"compra", "soporte", "queja", "saludo", "escalate"})
        self.assertEqual(set(t["pqrs"]["opciones"]), {"peticion", "queja", "reclamo", "sugerencia", "felicitacion", "escalate"})
        self.assertLessEqual(len(t["fintech"]["opciones"]), 15)
        cat = [c["id"] for c in json.load(open(T.CATALOGO, encoding="utf-8"))]
        self.assertEqual(t["herramientas"]["opciones"], cat)

    def test_escalate_usa_ataques_puros(self):
        self.assertIn("ataque_puro_inyeccion", T.estilos_de_clase("escalate"))
        self.assertNotIn("ataque_puro_spam", T.estilos_de_clase("compra"))
        self.assertIn("ataque_spam", T.estilos_de_clase("compra"))


class TestPipeline(unittest.TestCase):
    def correr(self, d, *extra, tareas=("pqrs", "herramientas"), por_clase="20"):
        args = ["--tareas", *tareas, "--por-clase", por_clase, "--salida", d, "--backend", "simulado",
                "--embeddings", "no", "--espera-base", "0", *extra]
        with mock.patch.object(G, "dormir", lambda s: None), mock.patch("builtins.print"):
            return G.main(args)

    def test_punta_a_punta_y_reanudar(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.correr(d), 0)
            res = json.load(open(os.path.join(d, "resumen.json"), encoding="utf-8"))
            self.assertFalse(res["parado_por_tope"])
            llamadas = res["llamadas"]
            self.assertGreater(res["usd_total"], 0)
            for nombre in ("pqrs", "herramientas"):
                filas = leer(os.path.join(d, nombre + ".jsonl"))
                self.assertGreater(len(filas), 0)
                N.validar_conjunto(filas)
                self.assertEqual(res["tareas"][nombre]["filas"], len(filas))
                self.assertTrue(all(f["fuente"] == T.FUENTE and f["licencia"] == "propia (Chispa)" and f["uso_comercial"] for f in filas))
                self.assertEqual({f["split"] for f in filas}, {"train", "dev"})
                self.assertIn("descartes", res["tareas"][nombre])
                self.assertEqual(set(res["tareas"][nombre]["filas_por_clase"]), set(T.tareas()[nombre]["opciones"]))
            # reanudar: no vuelve a llamar ni a gastar
            self.assertEqual(self.correr(d), 0)
            res2 = json.load(open(os.path.join(d, "resumen.json"), encoding="utf-8"))
            self.assertEqual(res2["llamadas"], llamadas)
            self.assertEqual(res2["usd_esta_ejecucion"], 0)

    def test_reparto_sin_fugas_entre_splits(self):
        with tempfile.TemporaryDirectory() as d:
            self.correr(d, tareas=("pqrs",), por_clase="60")
            filas = leer(os.path.join(d, "pqrs.jsonl"))
            sp = {}
            for f in filas:
                self.assertEqual(sp.setdefault(f["plantilla"], f["split"]), f["split"])
            self.assertEqual(len({f["texto"] for f in filas}), len(filas))
            self.assertTrue(any(f["split"] == "dev" for f in filas))

    def test_herramientas_sin_texto_ni_plantilla_del_test(self):
        with tempfile.TemporaryDirectory() as d:
            self.correr(d, tareas=("herramientas",), por_clase="40")
            filas = leer(os.path.join(d, "herramientas.jsonl"))
            test = leer(os.path.join(T.MODEL, "herramientas", "test.jsonl"))
            self.assertFalse({N.norm(f["texto"]) for f in filas} & {N.norm(r["texto"]) for r in test})
            self.assertFalse({f["plantilla"] for f in filas} & {r["plantilla"] for r in test})

    def test_parada_en_seco_por_tope(self):
        with tempfile.TemporaryDirectory() as d:
            self.correr(d, "--tope-usd", "0.02", "--hilos", "1", tareas=("pqrs", "fintech"), por_clase="200")
            res = json.load(open(os.path.join(d, "resumen.json"), encoding="utf-8"))
            self.assertTrue(res["parado_por_tope"])
            # nunca pasa del tope: lo gastado + una llamada máxima como mucho
            self.assertLess(res["usd_total"], 0.02)
            self.assertGreater(res["llamadas"], 0)
            self.assertTrue(os.path.exists(os.path.join(d, "pqrs.jsonl")))
            self.assertGreater(res["tareas"]["pqrs"]["descartes"]["lotes_sin_respuesta"], 0)

    def test_bedrock_exige_precios(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit):
            with mock.patch("sys.stderr"):
                G.main(["--por-clase", "5", "--salida", d, "--backend", "bedrock"])

    def test_motor_reintenta_con_espera_exponencial(self):
        esperas = []

        class Malo:
            n = 0

            def llamar(self, *a):
                self.n += 1
                if self.n < 3:
                    raise RuntimeError("Throttling")
                return '{"textos": ["x"]}', 10, 5

        g = N.Gasto(None, 1.0, 1.0, 1.0)
        m = G.Motor(Malo(), g, espera_base=1.0)
        with mock.patch.object(G, "dormir", esperas.append), mock.patch.object(G.random, "random", lambda: 0.5):
            lista, _ = m.pedir("t", "generar", "s", "u", {}, "textos", 1, 100, 0)
        self.assertEqual(lista, ["x"])
        self.assertEqual(len(esperas), 2)
        self.assertEqual(esperas, [1.0, 2.0])  # 1 s, 2 s (sin jitter)
        self.assertEqual(g.llamadas, 1)

    def test_motor_se_rinde(self):
        class Siempre:
            def llamar(self, *a):
                return "basura", 10, 5

        g = N.Gasto(None, 1.0, 1.0, 1.0)
        m = G.Motor(Siempre(), g, max_reintentos=3, espera_base=0)
        with mock.patch.object(G, "dormir", lambda s: None), self.assertRaises(RuntimeError):
            m.pedir("t", "generar", "s", "u", {}, "textos", 1, 100, 0)
        self.assertEqual(g.llamadas, 3)  # las respuestas rotas también cuestan


if __name__ == "__main__":
    unittest.main()
