"""Pruebas del listón humano con fixtures inventados (nada de datos reales)."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from model.datos import validar
from model.liston import acuerdo_humano as ah
from model.liston import fuentes

TARJETA = "---\nlicense: %s\n---\n# inventada\n"


def escribir_csv(ruta, filas):
    with open(ruta, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


class TestMayoria(unittest.TestCase):
    def test_mayoria(self):
        e, b = fuentes.mayoria(["true", "true", "false"], fuentes.BINARIAS)
        self.assertEqual(e, "true")
        self.assertAlmostEqual(b["true"], 2 / 3)

    def test_empate_gana_menor_indice(self):
        self.assertEqual(fuentes.mayoria(["true", "false"], fuentes.BINARIAS)[0], "false")
        ops = ["a", "b", "c"]
        self.assertEqual(fuentes.mayoria(["c", "b", "b", "c"], ops)[0], "b")
        self.assertEqual(fuentes.mayoria(["c", "b", "a"], ops)[0], "a")

    def test_blanda_suma_uno_e_incluye_ceros(self):
        e, b = fuentes.mayoria(["a", "b", "b", "b", "a"], ["a", "b", "c"])
        self.assertAlmostEqual(sum(b.values()), 1.0)
        self.assertEqual(b["c"], 0.0)
        self.assertEqual(list(b), ["a", "b", "c"])

    def test_voto_ajeno_o_vacio(self):
        with self.assertRaises(ValueError):
            fuentes.mayoria(["x"], fuentes.BINARIAS)
        with self.assertRaises(ValueError):
            fuentes.mayoria([], fuentes.BINARIAS)


class TestAcuerdo(unittest.TestCase):
    # 4 unidades, dos anotadores: (a,a) (a,a) (b,b) (a,b)
    DATOS = [["a", "a"], ["a", "a"], ["b", "b"], ["a", "b"]]

    def test_cohen(self):
        self.assertAlmostEqual(ah.cohen(self.DATOS), 0.5)

    def test_fleiss(self):
        k, n, m = ah.fleiss(self.DATOS)
        self.assertAlmostEqual(k, 0.21875 / 0.46875)
        self.assertEqual((n, m), (4, 2))

    def test_alfa(self):
        self.assertAlmostEqual(ah.alfa_krippendorff(self.DATOS), 8 / 15)

    def test_extremos(self):
        perfecto = [["a", "a", "a"], ["b", "b", "b"], ["a", "a", "a"]]
        self.assertAlmostEqual(ah.alfa_krippendorff(perfecto), 1.0)
        self.assertAlmostEqual(ah.fleiss(perfecto)[0], 1.0)
        self.assertAlmostEqual(ah.techo(perfecto), 1.0)
        # Desacuerdo sistemático de dos: α negativo
        self.assertLess(ah.alfa_krippendorff([["a", "b"]] * 3), 0)

    def test_alfa_admite_numero_variable_y_ignora_unitarias(self):
        con = ah.alfa_krippendorff(self.DATOS + [["a"]])
        self.assertAlmostEqual(con, 8 / 15)

    def test_sin_varianza(self):
        self.assertIsNone(ah.alfa_krippendorff([["a", "a"], ["a", "a"]]))

    def test_techo_pareado_y_reparto_de_empates(self):
        # Con dos anotadores el techo es la coincidencia: 3 de 4 unidades coinciden -> (2+2+2+0)/8
        self.assertAlmostEqual(ah.techo(self.DATOS), 6 / 8)
        # Tres: [a,a,b]: a acierta contra (a,b) empatado -> 1/2, el otro a también, b contra (a,a) -> 0
        self.assertAlmostEqual(ah.techo([["a", "a", "b"]]), (0.5 + 0.5 + 0) / 3)

    def test_fleiss_usa_el_numero_modal_de_anotadores(self):
        k, n, m = ah.fleiss([["a", "a", "b"], ["a", "a", "a"], ["b", "b", "b"], ["a", "b"]])
        self.assertEqual((n, m), (3, 3))

    def test_cohen_solo_con_dos_votos_por_unidad(self):
        self.assertIsNone(ah.cohen([["a", "b", "a"]]))

    def test_tabla_y_marcas_del_readme(self):
        res = {"x": {"tarea": "t", "resumen": ah.resumen(self.DATOS), "info": {}}}
        t = ah.tabla(res)
        self.assertIn("| x | t | 4 | 2.00 | 0.533 |", t)
        with tempfile.TemporaryDirectory() as d:
            r = Path(d) / "README.md"
            r.write_text("a\n%s\nviejo\n%s\nb" % ah.MARCA, encoding="utf-8")
            ah.escribir_readme(t, r)
            s = r.read_text(encoding="utf-8")
        self.assertIn(t, s)
        self.assertNotIn("viejo", s)
        self.assertTrue(s.startswith("a\n") and s.endswith("\nb"))


class TestFuentes(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def validas(self, filas):
        self.assertEqual(validar.errores_conjunto(filas), [])
        for f in filas:
            self.assertEqual(f["split"], "test")
            self.assertAlmostEqual(sum(f["blanda"].values()), 1.0)
            self.assertIsInstance(f["anotadores"], int)

    def test_multipico_solo_espanol(self):
        (self.d / "README.md").write_text(TARJETA % "cc-by-4.0")
        base = dict(post="Hola", reply="Qué bien", language="es", language_variety="co")
        filas = []
        for ann, lab in enumerate([1, 1, 0, 1]):
            filas.append(dict(base, label=lab, annotator_id=ann, reply_id="r1", post_id="p1", **{"Country of residence": "Colombia"}))
        for ann, lab in enumerate([0, 0, 1]):
            filas.append(dict(base, label=lab, annotator_id=ann, reply_id="r2", post_id="p2", language_variety="ar", **{"Country of residence": "Spain"}))
        filas.append(dict(base, label=1, annotator_id=9, reply_id="r3", post_id="p3", language="en", **{"Country of residence": "Spain"}))
        escribir_csv(self.d / "multipico_anonimized.csv", filas)
        out = fuentes.convertir_multipico(self.d)
        self.validas(out)
        self.assertEqual(len(out), 2)
        a, b = out
        self.assertEqual((a["tarea"], a["etiqueta"], a["anotadores"], a["variedad"], a["idioma"]), ("ironia", "true", 4, "co", "es-CO"))
        self.assertEqual(a["paises_anotadores"], ["Colombia"] * 4)
        self.assertEqual((b["etiqueta"], b["variedad"]), ("false", "ar"))
        self.assertIn("Mensaje: Hola", a["texto"])

    def test_alia_solo_con_tres_anotadores(self):
        (self.d / "README.md").write_text(TARJETA % "cc-by-4.0")
        regs = [dict(id="r1", text="uno", annotator_1="1", annotator_2="1", annotator_3="0"),
                dict(id="r2", text="dos", annotator_1="0", annotator_2="0", annotator_3="0"),
                dict(id="r3", text="tres", annotator_1="1", annotator_2="", annotator_3="0")]
        with open(self.d / "x-human-sample.jsonl", "w", encoding="utf-8") as fh:
            fh.write("\n".join(json.dumps(r) for r in regs))
        out = fuentes.convertir_alia(self.d)
        self.validas(out)
        self.assertEqual([f["etiqueta"] for f in out], ["true", "false"])
        self.assertEqual({f["anotadores"] for f in out}, {3})
        self.assertAlmostEqual(out[0]["blanda"]["true"], 2 / 3)

    def test_toxicidad_dos_codificadores_con_empate(self):
        (self.d / "README.md").write_text(TARJETA % "cc-by-4.0")
        escribir_csv(self.d / "goldstd_protests.csv", [
            dict(id_obs=1, coder_1=1, coder_2=1, text="a", country="Argentina"),
            dict(id_obs=2, coder_1=1, coder_2=0, text="b", country="Chile"),
            dict(id_obs=3, coder_1=0, coder_2=0, text="c", country="Chile")])
        out = fuentes.convertir_toxicidad("protests", self.d)
        self.validas(out)
        self.assertEqual([f["etiqueta"] for f in out], ["true", "false", "false"])
        self.assertEqual(out[1]["blanda"], {"false": 0.5, "true": 0.5})
        self.assertEqual(out[0]["idioma"], "es-AR")
        unidades = fuentes.registros_toxicidad("protests", self.d)
        self.assertAlmostEqual(ah.cohen([u["votos"] for u in unidades]), 0.4, places=6)

    def test_goemotions_une_por_id_y_marca_ingles(self):
        raw, es = self.d / "raw_repo", self.d / "es_repo"
        (raw / "raw").mkdir(parents=True)
        (es / "data").mkdir(parents=True)
        (raw / "README.md").write_text(TARJETA % "apache-2.0")
        (es / "README.md").write_text(TARJETA % "apache-2.0")
        import pyarrow as pa
        import pyarrow.parquet as pq
        cols = fuentes.EMOCIONES

        def r(i, rater, emos):
            return dict(id=i, text="orig " + i, rater_id=rater, **{c: int(c in emos) for c in cols})
        filas = [r("a", 1, ["joy"]), r("a", 2, ["joy", "love"]), r("a", 3, ["sadness"]),   # joy, joy, love? -> love por índice menor que joy? no: joy < love
                 r("b", 1, ["anger"]), r("b", 2, ["anger"]),                                # solo 2 anotadores: fuera
                 r("c", 1, ["neutral"]), r("c", 2, ["neutral"]), r("c", 3, ["neutral"]),   # sin traducción: fuera
                 r("d", 1, []), r("d", 2, ["fear"]), r("d", 3, ["fear"]), r("d", 4, ["fear"])]
        pq.write_table(pa.Table.from_pylist(filas), raw / "raw" / "train-0.parquet")
        pq.write_table(pa.Table.from_pylist([dict(id="a", text_es="hola"), dict(id="b", text_es="b"), dict(id="d", text_es="miedo")]),
                       es / "data" / "test-0.parquet")
        out, info = fuentes.convertir_goemotions(raw, es)
        self.validas(out)
        self.assertEqual([f["texto"] for f in out], ["hola", "miedo"])
        self.assertEqual(out[0]["etiqueta"], "joy")
        self.assertEqual(out[0]["anotadores"], 3)
        self.assertEqual({f["idioma"] for f in out}, {"en"})
        self.assertEqual(out[1]["anotadores"], 3)  # el anotador sin emoción no cuenta
        self.assertEqual(info["sin_traduccion"], 1)
        self.assertEqual(info["con_menos_de_3_anotadores"], 1)

    def test_licencia_no_comercial_o_dudosa(self):
        (self.d / "README.md").write_text(TARJETA % "cc-by-nc-4.0")
        regs = [dict(id="r1", text="uno", annotator_1="1", annotator_2="1", annotator_3="0")]
        (self.d / "x-human-sample.jsonl").write_text(json.dumps(regs[0]))
        out = fuentes.convertir_alia(self.d)
        self.assertFalse(out[0]["uso_comercial"])
        self.assertEqual(out[0]["split"], "test")
        self.validas(out)

    def test_voto_emocion_menor_indice(self):
        self.assertEqual(fuentes.voto_emocion({"love": 1, "joy": 1}), "joy")
        self.assertIsNone(fuentes.voto_emocion({}))


if __name__ == "__main__":
    unittest.main()
