"""Un test por fuente sobre su fixture (filas inventadas con la forma de la fuente real)."""
import collections
import unittest
from pathlib import Path

from model.datos import banking77, clinc150, hatecheck, inyecciones, massive, pawsx, sib200, validar, xnli

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def por_split(filas):
    return dict(collections.Counter(f["split"] for f in filas))


class Base(unittest.TestCase):
    def assertValidas(self, filas):
        self.assertEqual(validar.errores_conjunto(filas), [])


class TestMassive(Base):
    def test_fixture(self):
        filas, info = massive.convertir(FIX / "massive")
        self.assertValidas(filas)
        self.assertEqual(por_split(filas), {"train": 5, "dev": 2, "test": 3})
        f = filas[0]
        self.assertEqual((f["id"], f["tipo"], f["idioma"], f["etiqueta"]), ("massive:train:0", "choice", "es", "alarm_set"))
        self.assertEqual(len(f["opciones"]), 60)
        self.assertEqual(set(f["opciones"]), set(f["descripciones"]))
        self.assertTrue(all(x["uso_comercial"] for x in filas))
        self.assertNotIn("escalate", f["opciones"])


class TestHatecheck(Base):
    def test_fixture(self):
        filas, info = hatecheck.convertir(FIX / "hatecheck")
        self.assertValidas(filas)
        self.assertEqual(len(filas), 16)  # 17 casos, uno con desacuerdo de anotadores
        self.assertEqual(info["sin_acuerdo_anotadores"], 1)
        self.assertEqual(por_split(filas), {"train": 8, "dev": 2, "test": 6})
        self.assertTrue(all(f["tipo"] == "noul" and f["opciones"] == ["false", "true"] for f in filas))
        odio = [f for f in filas if f["texto"].startswith("Detesto")]
        self.assertTrue(odio and all(f["etiqueta"] == "true" for f in odio))
        self.assertTrue(all(f["etiqueta"] == "false" for f in filas if f["texto"].startswith("Respeto")))
        self.assertTrue(all(f["plantilla"].startswith("hc-") for f in filas))


class TestBanking77(Base):
    def test_fixture(self):
        filas, _ = banking77.convertir(FIX / "banking77")
        self.assertValidas(filas)
        self.assertEqual(por_split(filas), {"train": 11, "dev": 1, "test": 4})
        self.assertTrue(all(f["idioma"] == "en" and f["tarea"] == "banca" for f in filas))
        self.assertEqual(len(filas[0]["opciones"]), 77)
        self.assertEqual(set(filas[0]["opciones"]), set(filas[0]["descripciones"]))
        # los textos de test no pasan a train/dev
        self.assertFalse({f["texto"] for f in filas if f["split"] == "test"} & {f["texto"] for f in filas if f["split"] != "test"})
        # la descripción va en español aunque el texto sea inglés
        self.assertEqual(filas[0]["descripciones"]["card_arrival"], "seguimiento de la llegada de una tarjeta")


class TestClinc150(Base):
    def test_fixture_oos_a_escalate(self):
        filas, _ = clinc150.convertir(FIX / "clinc150")
        self.assertValidas(filas)
        self.assertEqual(por_split(filas), {"train": 8, "dev": 3, "test": 4})
        esc = [f for f in filas if f["etiqueta"] == "escalate"]
        self.assertEqual(len(esc), 4)  # 2 en train, 1 en dev, 1 en test
        self.assertTrue(all("escalate" in f["opciones"] and f["descripciones"]["escalate"] for f in filas))
        self.assertEqual(len(filas[0]["opciones"]), 151)
        self.assertNotIn("oos", filas[0]["opciones"])

    def test_formato_json_original(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "README.md").write_text("---\nlicense: cc-by-3.0\n---\n")
            par = lambda t, i: [t, i]
            datos = {"train": [par("what is my balance", "balance")], "val": [par("is it sunny", "weather")],
                     "test": [par("balance please", "balance")], "oos_train": [par("who is the president", "oos")],
                     "oos_val": [par("meaning of that word", "oos")], "oos_test": [par("tallest mountain", "oos")]}
            (Path(d) / "data_full.json").write_text(json.dumps(datos))
            filas, _ = clinc150.convertir(Path(d))
        self.assertEqual(por_split(filas), {"train": 2, "dev": 2, "test": 2})
        self.assertEqual(sum(f["etiqueta"] == "escalate" for f in filas), 3)


class TestInyecciones(Base):
    def test_fixture(self):
        filas, _ = inyecciones.convertir(FIX / "inyecciones")
        self.assertValidas(filas)
        self.assertEqual(sum(por_split(filas).values()), 13)
        self.assertEqual(por_split(filas)["test"], 3)
        self.assertEqual(sorted(collections.Counter(f["etiqueta"] for f in filas).items()), [("false", 8), ("true", 5)])
        self.assertTrue(all(f["tipo"] == "noul" and f["tarea"] == "inyeccion" for f in filas))
        inj = [f for f in filas if f["texto"].startswith("Ignore all previous")]
        self.assertEqual(inj[0]["etiqueta"], "true")


class TestXnli(Base):
    def test_fixture_solo_test_y_no_comercial(self):
        filas, _ = xnli.convertir(FIX / "xnli")
        self.assertValidas(filas)
        self.assertEqual(por_split(filas), {"test": 4})  # train (3) y validation (2) del fixture no salen
        self.assertTrue(all(f["uso_comercial"] is False and f["licencia"] == "CC-BY-NC-4.0" for f in filas))
        self.assertEqual([f["etiqueta"] for f in filas], ["entailment", "contradiction", "neutral", "entailment"])
        self.assertTrue(filas[0]["texto"].startswith("Premisa: ") and "\nHipótesis: " in filas[0]["texto"])


@unittest.skipUnless((Path.home() / "hf/hub/datasets--mteb--amazon_massive_intent").is_dir(), "MASSIVE no está en ~/hf")
class TestReales(Base):
    def test_massive_y_hatecheck_reales(self):
        filas, _ = massive.convertir()
        self.assertValidas(filas)
        self.assertEqual(por_split(filas), {"train": 11514, "dev": 2033, "test": 2974})
        filas, info = hatecheck.convertir()
        self.assertValidas(filas)
        self.assertEqual(len(filas) + info["sin_acuerdo_anotadores"], 3745)


if __name__ == "__main__":
    unittest.main()


class TestSib200Pawsx(Base):
    def test_sib200_fixture_y_mismo_esquema_que_m4(self):
        from model.l2 import espanol
        filas, info = sib200.convertir(FIX / "sib200")
        self.assertValidas(filas)
        self.assertEqual(por_split(filas), {"test": 2})  # SA sin decidir: solo test
        self.assertEqual(info["descartadas_nc"], 4)
        self.assertTrue(all(not f["uso_comercial"] and f["licencia"] == "CC-BY-SA-4.0" for f in filas))
        self.assertEqual((sib200.PREGUNTA, sib200.DESCRIPCIONES), (espanol.PREGUNTA_SIB, espanol.DESC_SIB))

    def test_pawsx_fixture_y_mismo_esquema_que_m4(self):
        from model.l2 import espanol
        filas, info = pawsx.convertir(FIX / "pawsx")
        self.assertValidas(filas)
        self.assertEqual(por_split(filas), {"train": 3, "dev": 2, "test": 4})
        self.assertTrue(all(f["uso_comercial"] for f in filas))
        self.assertEqual([f["etiqueta"] for f in filas if f["split"] == "train"], ["true", "false", "true"])
        self.assertEqual((pawsx.PREGUNTA, pawsx.DESCRIPCIONES), (espanol.PREGUNTA_PAWS, espanol.DESC_PAWS))

    def test_pawsx_sin_la_frase_de_la_tarjeta_solo_test(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(FIX / "pawsx", d, dirs_exist_ok=True)
            (Path(d) / "README.md").write_text("---\nlicense:\n- other\n---\nsin frase\n", encoding="utf-8")
            filas, _ = pawsx.convertir(d)
        self.assertEqual(por_split(filas), {"test": 4})
        self.assertFalse(any(f["uso_comercial"] for f in filas))
