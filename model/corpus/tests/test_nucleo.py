import json
import os
import tempfile
import unittest

import numpy as np

from model.corpus import nucleo as N


class TestParseo(unittest.TestCase):
    def test_limpio_y_lista_directa(self):
        self.assertEqual(N.parsear_lista('{"textos": ["a", "b"]}', "textos"), (["a", "b"], False))
        self.assertEqual(N.parsear_lista('["a", "b"]', "textos"), (["a", "b"], False))

    def test_cercas_y_texto_alrededor(self):
        r = 'Claro:\n```json\n{"textos": ["hola, parce", "buenas"]}\n```\nEspero que sirva.'
        self.assertEqual(N.parsear_lista(r, "textos"), (["hola, parce", "buenas"], False))

    def test_json_cortado_rescata_las_cadenas_completas(self):
        r = '{"textos": ["uno", "dos \\"con comillas\\"", "tres cor'
        lista, rep = N.parsear_lista(r, "textos")
        self.assertEqual(lista, ["uno", 'dos "con comillas"'])
        self.assertTrue(rep)

    def test_roto_en_medio(self):
        lista, rep = N.parsear_lista('{"textos": ["a", "b" "c", ]}', "textos")
        self.assertEqual(lista, ["a", "b", "c"])
        self.assertTrue(rep)

    def test_basura_o_vacio_lanza(self):
        for r in ("Lo siento, no puedo.", "", '{"textos": []}', '{"otra": ["x"]}', "{"):
            with self.assertRaises(N.ErrorFormato, msg=r):
                N.parsear_lista(r, "textos")


class TestTope(unittest.TestCase):
    def test_para_al_llegar_al_tope_y_cuenta_costo(self):
        g = N.Gasto(None, 1.0, 2.0, 10.0)  # USD por millón
        self.assertAlmostEqual(g.registrar("t", "generar", 500_000, 50_000), 1.5)
        with self.assertRaises(N.TopeAlcanzado):
            g.permitir()
        self.assertTrue(g.parado)

    def test_margen_para_antes(self):
        g = N.Gasto(None, 1.0, 1.0, 1.0)
        for _ in range(5):
            g.registrar("t", "generar", 80_000, 20_000)  # 5 × 0,1
        g.permitir(0.4)
        with self.assertRaises(N.TopeAlcanzado):
            g.permitir(0.6)

    def test_libro_reanuda_la_cuenta(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "gasto.jsonl")
            g = N.Gasto(ruta, 5.0, 1.0, 5.0)
            g.registrar("a", "generar", 1000, 200)
            g2 = N.Gasto(ruta, 5.0, 1.0, 5.0)
            self.assertAlmostEqual(g2.usd, g.usd)
            self.assertEqual(g2.llamadas, 1)


class TestDedup(unittest.TestCase):
    def f(self, texto, etiqueta="a"):
        return {"texto": texto, "etiqueta": etiqueta}

    def test_exacto_normalizado(self):
        filas, d = N.deduplicar([self.f("Quiero mi saldo"), self.f("quiero  mi SALDO!"), self.f("otra cosa distinta")])
        self.assertEqual(len(filas), 2)
        self.assertEqual(d["exacto"], 1)

    def test_casi_igual_por_gramas(self):
        a = "necesito bloquear mi tarjeta porque la perdí ayer en el centro"
        filas, d = N.deduplicar([self.f(a), self.f(a + " ya"), self.f("quiero pagar mi factura de energía")])
        self.assertEqual(len(filas), 2)
        self.assertEqual(d["jaccard"], 1)

    def test_coseno_con_embedder_falso(self):
        def embeber(textos):
            return np.array([[1.0, 0.0] if "saldo" in t else [0.0, 1.0] for t in textos])
        filas, d = N.deduplicar([self.f("cuánto saldo tengo"), self.f("dime mi saldo actual por favor"), self.f("hola")],
                                embeber=embeber)
        self.assertEqual([x["texto"] for x in filas], ["cuánto saldo tengo", "hola"])
        self.assertEqual(d["coseno"], 1)

    def test_conflicto_de_etiqueta_tira_las_dos(self):
        filas, d = N.deduplicar([self.f("hola buenas tardes", "saludo"), self.f("Hola buenas tardes", "queja"), self.f("zzz distinto", "x")])
        self.assertEqual([x["texto"] for x in filas], ["zzz distinto"])
        self.assertEqual(d["conflicto_etiqueta"], 2)

    def test_fuga_del_test(self):
        ref = [{"texto": "Crea una microVM nueva con la rama de la fase 1.", "etiqueta": "k"}]
        filas, d = N.deduplicar([self.f("crea una microvm nueva con la rama de la fase 1"), self.f("lista los correos")], ref)
        self.assertEqual([x["texto"] for x in filas], ["lista los correos"])
        self.assertEqual(d["fuga_test"], 1)


class TestReparto(unittest.TestCase):
    def test_una_plantilla_un_split_y_diez_por_ciento(self):
        pl = {"p%d" % i: 20 for i in range(50)}
        r = N.repartir(pl, 0.10, 3)
        self.assertEqual(set(r), set(pl))
        dev = sum(n for p, n in pl.items() if r[p] == "dev")
        self.assertTrue(80 <= dev <= 120, dev)
        self.assertEqual(r, N.repartir(pl, 0.10, 3))
        self.assertNotEqual(r, N.repartir(pl, 0.10, 4))

    def test_pocas_plantillas_dejan_alguna_en_dev(self):
        self.assertIn("dev", N.repartir({"a": 20, "b": 20}, 0.10, 1).values())


class TestEsquema(unittest.TestCase):
    def fila(self, **kw):
        f = {"id": "x:train:0", "tarea": "pqrs", "tipo": "choice", "pregunta": "¿?", "texto": "hola", "opciones": ["a", "escalate"],
             "descripciones": {"a": "A", "escalate": "E"}, "etiqueta": "a", "idioma": "es-CO", "split": "train",
             "fuente": "f", "licencia": "l", "uso_comercial": True, "plantilla": "p"}
        f.update(kw)
        return f

    def test_valida(self):
        N.validar_fila(self.fila())

    def test_rechaza(self):
        for kw in ({"etiqueta": "z"}, {"split": "val"}, {"tipo": "noul"}, {"texto": " "}, {"uso_comercial": "si"},
                   {"descripciones": {"a": "A"}}, {"uso_comercial": False}, {"extra": 1}):
            with self.assertRaises(ValueError, msg=str(kw)):
                N.validar_fila(self.fila(**kw))

    def test_conjunto_ids_y_plantillas(self):
        with self.assertRaises(ValueError):
            N.validar_conjunto([self.fila(), self.fila()])
        with self.assertRaises(ValueError):
            N.validar_conjunto([self.fila(), self.fila(id="x:dev:0", split="dev")])


if __name__ == "__main__":
    unittest.main()
