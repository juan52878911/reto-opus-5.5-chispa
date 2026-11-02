"""Traducción de tsjev (W10): ids de opción, etiqueta, plantilla y split intactos; heurísticas; determinismo."""
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from model.datos import validar
from model.meta import traducir


def leer(salida):
    filas = []
    for r in sorted(Path(salida, traducir.CORTO).glob("*.jsonl.gz")):
        with gzip.open(r, "rt", encoding="utf-8") as f:
            filas += [json.loads(x) for x in f]
    return filas


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.dir = Path(self._t.name)
        self.meta = self.dir / "meta"
        traducir.crear_fixture(self.meta)
        self.orig = {f["id"]: f for f in traducir.leer_meta(self.meta)}

    def correr(self, nombre="s", trad=None, **kw):
        s = self.dir / nombre
        res = traducir.correr(self.meta, s, trad or traducir.TraductorFalso(), **kw)
        return res, leer(s), s


class TestTraducir(Base):
    def test_ids_etiqueta_plantilla_y_split_se_conservan(self):
        res, filas, _ = self.correr()
        self.assertEqual(len(filas), 120)
        for g in filas:
            self.assertTrue(g["id"].endswith(":es"))
            o = self.orig[g["id"][:-3]]
            self.assertEqual(g["opciones"], o["opciones"])
            self.assertEqual(list(g["descripciones"]), o["opciones"])
            self.assertEqual((g["etiqueta"], g["blanda"], g["tipo"]), (o["etiqueta"], o["blanda"], o["tipo"]))
            self.assertEqual((g["plantilla"], g["split"], g["tarea"]), (o["plantilla"], o["split"], o["tarea"]))
            self.assertEqual(g["idioma"], "es")
            self.assertEqual(g["traducida"], {"modelo": "FALSO:marcador", "revision": "falso", "de": "en"})
            self.assertTrue(g["licencia"].startswith("mit; traducción:"))
            self.assertNotEqual(g["texto"], o["texto"])
            self.assertTrue(g["texto"].startswith("[falso-es] "))
        self.assertEqual({g["split"] for g in filas}, {"train", "dev", "test"})
        self.assertEqual([e for e in validar.errores_conjunto(filas) if "el id no sigue" not in e], [])  # el sufijo :es lo pide W10

    def test_noul_rehace_descripciones_con_la_pregunta_traducida(self):
        _, filas, _ = self.correr()
        nu = next(g for g in filas if g["tipo"] == "noul")
        self.assertEqual(nu["opciones"], ["false", "true"])
        self.assertEqual(nu["descripciones"]["true"], "true: " + nu["pregunta"])

    def test_topes_por_tarea_y_total(self):
        res, filas, _ = self.correr(max_por_tarea=10)
        self.assertEqual(len(filas), 30)
        self.assertEqual(set(res["filas_por_tarea"].values()), {10})
        res, filas, _ = self.correr("t2", max_por_tarea=10, max_filas=7)
        self.assertEqual(len(filas), 7)

    def test_es_determinista(self):
        _, a, _ = self.correr("a", max_por_tarea=15)
        _, b, _ = self.correr("b", max_por_tarea=15)
        self.assertEqual(a, b)
        self.assertEqual((self.dir / "a" / "muestra-revision.md").read_text(), (self.dir / "b" / "muestra-revision.md").read_text())
        _, c, _ = self.correr("c", max_por_tarea=15, semilla=7)
        self.assertNotEqual([g["id"] for g in a], [g["id"] for g in c])

    def test_deduplica_textos_antes_de_traducir(self):
        llamadas = []

        class Cuenta(traducir.TraductorFalso):
            def traducir(self, textos):
                llamadas.extend(textos)
                return super().traducir(textos)

        self.correr(trad=Cuenta())
        self.assertEqual(len(llamadas), len(set(llamadas)))
        self.assertLess(len(llamadas), 120 * 2)

    def test_tope_de_tiempo_cuenta_lo_que_falta(self):
        res, filas, _ = self.correr(minutos=0, trozo=50)
        self.assertEqual(filas, [])
        self.assertEqual(res["info"]["sin_traducir_por_tiempo"], 120)

    def test_muestra_de_revision(self):
        res, _, s = self.correr()
        md = (s / "muestra-revision.md").read_text(encoding="utf-8")
        self.assertEqual(md.count("\n## "), 50)
        self.assertIn("FALSO", md)
        self.assertEqual(res["pares_en_muestra"], 50)


class TestHeuristicas(Base):
    def test_basura(self):
        o = "The quick brown fox jumps over the lazy dog today."
        self.assertEqual(traducir.basura(o, ""), "vacia")
        self.assertEqual(traducir.basura(o, "   "), "vacia")
        self.assertEqual(traducir.basura(o, o), "identica")
        self.assertEqual(traducir.basura(o, "Sí"), "longitud")
        self.assertEqual(traducir.basura(o, "x" * (len(o) * 4)), "longitud")
        self.assertEqual(traducir.basura(o, "el perro el perro el perro el perro el perro el perro"), "repeticion")
        self.assertIsNone(traducir.basura(o, "El rápido zorro marrón salta sobre el perro perezoso hoy."))
        self.assertIsNone(traducir.basura("Paris", "Paris", identica=False))

    def test_filas_basura_se_descartan_y_se_cuentan(self):
        class Mala(traducir.TraductorFalso):
            def traducir(self, textos):
                return ["" if i % 4 == 0 else t for i, t in enumerate(super().traducir(textos))]

        res, filas, _ = self.correr(trad=Mala())
        self.assertGreater(res["descartadas_heuristica"].get("vacia", 0), 0)
        self.assertEqual(res["descartadas_total"] + len(filas), 120)
        self.assertTrue(all(g["texto"] and g["pregunta"] for g in filas))

    def test_identidad_descarta_todo(self):
        res, filas, _ = self.correr(trad=traducir.TraductorIdentidad())
        self.assertEqual(filas, [])
        self.assertEqual(res["descartadas_heuristica"], {"identica": 120})

    def test_main_falla_si_no_sale_nada(self):
        self.assertEqual(traducir.main([str(self.meta), str(self.dir / "m"), "--traductor", "identidad"]), 2)
        self.assertEqual(traducir.main([str(self.meta), str(self.dir / "m2"), "--traductor", "falso"]), 0)


class TestSeleccion(Base):
    def test_solo_comerciales_en_ingles(self):
        info = {}
        filas = traducir.seleccionar(self.meta, 1000, None, 0, info)
        self.assertEqual(len(filas), 120)
        self.assertEqual(info["tareas_con_filas"], 3)


if __name__ == "__main__":
    unittest.main()


class TestTrozos(unittest.TestCase):
    """Textos largos (tercer fallo de la traducción, 2026-11-02): se parten por frases en trozos de ≤ tope tokens."""

    @staticmethod
    def n_tok(t):
        return len(t.split())   # un token por palabra, para el test

    def test_texto_de_600_tokens_se_parte(self):
        frase = " ".join(["palabra"] * 29) + "."   # 30 tokens por frase
        texto = " ".join([frase] * 20)              # 600 tokens
        tr, trunc = traducir.trozos(texto, self.n_tok, 200)
        self.assertGreater(len(tr), 1)
        self.assertTrue(all(self.n_tok(x) <= 200 for x in tr))
        self.assertEqual(trunc, 0)
        self.assertEqual(" ".join(tr).split(), texto.split())   # no se pierde ni se reordena nada

    def test_una_frase_muy_larga_se_cuenta_truncada(self):
        texto = " ".join(["x"] * 600)   # una sola frase de 600 tokens
        tr, trunc = traducir.trozos(texto, self.n_tok, 200)
        self.assertEqual(tr, [texto])
        self.assertEqual(trunc, 1)

    def test_texto_corto_no_se_toca(self):
        self.assertEqual(traducir.trozos("Hola. Adiós.", self.n_tok, 200), (["Hola. Adiós."], 0))
