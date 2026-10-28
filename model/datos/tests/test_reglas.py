"""Reglas transversales: licencias NC solo en test, reparto por plantilla sin fugas, validador, CLI."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from model.datos import banking77, clinc150, comun, convertir, hatecheck, massive, validar, xnli

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def fila_ok(**cambios):
    f = {"id": "x:train:0", "tarea": "intencion", "tipo": "choice", "pregunta": "¿?", "texto": "hola",
         "opciones": ["a", "b"], "descripciones": {"a": "uno", "b": "dos"}, "etiqueta": "a", "idioma": "es",
         "split": "train", "fuente": "x train", "licencia": "cc-by-4.0", "uso_comercial": True}
    f.update(cambios)
    return f


class TestNoComercial(unittest.TestCase):
    def test_falla_si_fila_nc_cae_en_train_o_dev(self):
        for split in ("train", "dev"):
            errs = validar.errores_fila(fila_ok(id="x:%s:0" % split, split=split, licencia="CC-BY-NC-4.0", uso_comercial=False))
            self.assertTrue(any("solo test" in e for e in errs), (split, errs))
        self.assertEqual(validar.errores_fila(fila_ok(id="x:test:0", split="test", licencia="CC-BY-NC-4.0", uso_comercial=False)), [])

    def test_conjunto_con_fila_nc_en_train_es_invalido(self):
        filas, _ = xnli.convertir(FIX / "xnli")
        self.assertEqual(validar.errores_conjunto(filas), [])
        malas = copy.deepcopy(filas)
        malas[0]["split"], malas[0]["id"] = "train", "xnli:train:0"
        self.assertTrue(validar.errores_conjunto(malas))

    def test_licencia_nc_con_uso_comercial_true_es_error(self):
        for lic in ("CC-BY-NC-4.0", "cc-by-nd-4.0", "sin verificar (tarjeta: x)"):
            self.assertTrue(validar.errores_fila(fila_ok(licencia=lic)), lic)
        self.assertEqual(validar.errores_fila(fila_ok(licencia="cc-by-sa-4.0")), [])

    def test_ningun_conversor_emite_nc_fuera_de_test(self):
        for mod in (massive, hatecheck, banking77, clinc150, xnli):
            filas, _ = mod.convertir(FIX / mod.__name__.rsplit(".", 1)[1])
            self.assertFalse([f for f in filas if not f["uso_comercial"] and f["split"] != "test"], mod.__name__)

    def test_numerar_descarta_nc_fuera_de_test(self):
        kw = dict(tarea="t", tipo="choice", pregunta="p", texto="x", opciones=["a"], descripciones={"a": "a"},
                  etiqueta="a", idioma="es", fuente="f", licencia="CC-BY-NC-4.0", uso_comercial=False)
        filas, desc = comun.numerar("s", [("train", kw), ("dev", kw), ("test", kw), ("test", kw)])
        self.assertEqual((desc, [f["id"] for f in filas]), (2, ["s:test:0", "s:test:1"]))

    def test_tarjeta_que_no_confirma_la_licencia_deja_solo_test(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d) / "banking77"
            raiz.mkdir()
            for f in (FIX / "banking77").iterdir():
                (raiz / f.name).write_bytes(f.read_bytes())
            (raiz / "README.md").write_text("---\nlicense: cc-by-nc-4.0\n---\n")
            filas, info = banking77.convertir(raiz)
        self.assertEqual({f["split"] for f in filas}, {"test"})
        self.assertEqual(len(filas), 4)
        self.assertEqual(info["descartadas_nc"], 12)
        self.assertTrue(all(not f["uso_comercial"] and f["licencia"].startswith("sin verificar") for f in filas))


class TestRepartoPorPlantilla(unittest.TestCase):
    def test_plantilla_en_un_solo_split_fixture(self):
        filas, _ = hatecheck.convertir(FIX / "hatecheck")
        splits = {}
        for f in filas:
            splits.setdefault(f["plantilla"], set()).add(f["split"])
        self.assertTrue(all(len(s) == 1 for s in splits.values()), splits)
        self.assertEqual({s for v in splits.values() for s in v}, {"train", "dev", "test"})
        self.assertGreater(len(filas), len(splits))  # varias filas por plantilla

    def test_split_por_clave_estable_y_validador_detecta_fuga(self):
        self.assertEqual({comun.split_por_clave("hc-7") for _ in range(3)}, {comun.split_por_clave("hc-7")})
        a = fila_ok(id="x:train:0", plantilla="p1")
        b = fila_ok(id="x:test:0", split="test", plantilla="p1")
        self.assertTrue(any("varios splits" in e for e in validar.errores_conjunto([a, b])))
        c = fila_ok(id="x:train:1", plantilla="p1")
        self.assertEqual(validar.errores_conjunto([a, c]), [])

    def test_proporciones_aproximadas(self):
        n = 20000
        cuentas = {"train": 0, "dev": 0, "test": 0}
        for i in range(n):
            cuentas[comun.split_por_clave("plantilla-%d" % i, 0.1, 0.1)] += 1
        for s, esperado in (("train", 0.8), ("dev", 0.1), ("test", 0.1)):
            self.assertAlmostEqual(cuentas[s] / n, esperado, delta=0.02)


class TestValidador(unittest.TestCase):
    def test_fila_valida(self):
        self.assertEqual(validar.errores_fila(fila_ok()), [])

    def test_errores(self):
        casos = {
            "etiqueta fuera": fila_ok(etiqueta="z"),
            "falta descripción": fila_ok(descripciones={"a": "uno"}),
            "tipo malo": fila_ok(tipo="otro"),
            "noul mal": fila_ok(tipo="noul", etiqueta="a"),
            "split malo": fila_ok(split="val"),
            "opciones repetidas": fila_ok(opciones=["a", "a"]),
            "uso_comercial no bool": fila_ok(uso_comercial="si"),
            "texto vacío": fila_ok(texto=" "),
        }
        for nombre, f in casos.items():
            self.assertTrue(validar.errores_fila(f), nombre)
        f = fila_ok()
        del f["licencia"]
        self.assertTrue(validar.errores_fila(f))

    def test_ids_repetidos_y_split_en_id(self):
        errs = validar.errores_conjunto([fila_ok(), fila_ok()])
        self.assertTrue(any("repetido" in e for e in errs))
        self.assertTrue(validar.errores_conjunto([fila_ok(id="x:test:0")]))


class TestCLI(unittest.TestCase):
    def test_fixtures_a_disco_y_resumen(self):
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(convertir.main(["--salida", d, "--fixtures"]), 0)
            resumen = json.load(open(Path(d) / "resumen.json"))
            self.assertEqual(resumen["riesgo_suicida"]["estado"], "no disponible")  # sin fixture: la fuente no está
            for nombre in [n for n in convertir.FUENTES if n != "riesgo_suicida"]:
                self.assertEqual(resumen[nombre]["estado"], "convertida", nombre)
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(validar.main([str(Path(d) / (nombre + ".jsonl"))]), 0)
            self.assertIn("no disponible", resumen["necos-tox"])
            self.assertEqual(resumen["xnli"]["filas"], {"test": 4})

    def test_fuente_ausente_y_fuente_rota(self):
        with tempfile.TemporaryDirectory() as d:
            raiz = Path(d) / "hf"
            raiz.mkdir()
            antes = comun.HF_HUB
            comun.HF_HUB = raiz
            try:
                r = convertir.convertir_fuentes(Path(d) / "o", ["banking77"])
            finally:
                comun.HF_HUB = antes
            self.assertEqual(r["banking77"]["estado"], "no disponible")

    def test_fuente_desconocida_es_error(self):
        with self.assertRaises(SystemExit):
            convertir.main(["--salida", "/tmp/_nada", "--fuentes", "inventada"])


if __name__ == "__main__":
    unittest.main()
