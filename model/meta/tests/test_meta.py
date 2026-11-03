"""Conversores de metaentrenamiento (T1.8): mapeo al esquema, filtro de licencia, fuentes prohibidas y salida en trozos."""
import contextlib
import gzip
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from model.datos import validar
from model.meta import comun, convertir, pawsx_es, sib200_es, synthetic_zeroshot, tasksource_jev
from model.meta.tests import falsos

FICHAS_OK = {"demo/colores": ("demo/colores", "commercial", "mit")}


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.hub = Path(self._t.name) / "hf"
        self.addCleanup(self._t.cleanup)
        p = mock.patch.dict(os.environ, {"HF_HOME": str(self.hub)})
        p.start()
        self.addCleanup(p.stop)


class TestTasksource(Base):
    def test_mapeo_choice_score_noul(self):
        falsos.tasksource(self.hub, [falsos.fila_ts(0), falsos.fila_ts(1, kind="score"), falsos.fila_ts(2, kind="noul")],
                          FICHAS_OK)
        filas, info = tasksource_jev.convertir()
        ch, sc, nu = filas
        self.assertEqual((ch["texto"], ch["pregunta"], ch["tipo"], ch["opciones"]),
                         ("Texto inventado número 0.", "¿Cuál es el color?", "choice", ["rojo", "verde", "azul"]))
        self.assertEqual(ch["etiqueta"], "verde")
        self.assertEqual(ch["descripciones"], {"rojo": "rojo", "verde": "verde", "azul": "azul"})
        self.assertAlmostEqual(sum(ch["blanda"].values()), 1.0)
        self.assertEqual(sc["opciones"], ["1", "2", "3", "4"])
        self.assertEqual((sc["etiqueta"], sc["descripciones"]["4"]), ("4", "muy bien"))
        self.assertEqual((nu["tipo"], nu["opciones"], nu["etiqueta"]), ("noul", ["false", "true"], "true"))
        self.assertAlmostEqual(nu["blanda"]["false"], 0.2)
        self.assertEqual((ch["fuente"].split(":")[1].split()[0], ch["licencia"], ch["uso_comercial"]),
                         ("demo/colores", "mit", True))
        self.assertEqual(validar.errores_conjunto(filas), [])
        self.assertEqual(info["filas_leidas"], 3)

    def test_trampa_solo_commercial(self):
        """Falla si se cuela una fila que no sea `commercial` (non-commercial, unspecified, vacía, mayúsculas…)."""
        usos = ["commercial", "non-commercial", "unspecified", "", None, "Commercial", "commercial-ish"]
        falsos.tasksource(self.hub, [falsos.fila_ts(i, uso=u) for i, u in enumerate(usos)], FICHAS_OK)
        filas, info = tasksource_jev.convertir()
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["texto"], "Texto inventado número 0.")
        self.assertTrue(all(f["uso_comercial"] for f in filas))
        self.assertEqual(info["descartadas_licencia_non-commercial"], 1)
        self.assertEqual(info["descartadas_licencia_unspecified"], 1)
        self.assertEqual(info["descartadas_licencia_vacia"], 2)
        self.assertEqual(info["descartadas_licencia_Commercial"], 1)

    def test_tarea_no_comercial_en_sources_yaml_se_descarta_aunque_la_fila_diga_commercial(self):
        fichas = dict(FICHAS_OK, **{"demo/nc": ("demo/nc", "non-commercial", "cc-by-nc-4.0")})
        falsos.tasksource(self.hub, [falsos.fila_ts(0), falsos.fila_ts(1, source="demo/nc")], fichas)
        filas, info = tasksource_jev.convertir()
        self.assertEqual([f["tarea"] for f in filas], ["demo/colores"])
        self.assertEqual(info["descartadas_licencia_fuente_no_comercial"], 1)

    def test_texto_de_licencia_nc_se_descarta(self):
        falsos.tasksource(self.hub, [falsos.fila_ts(0), falsos.fila_ts(1, license="CC BY-NC-SA 4.0 (DPI)")], FICHAS_OK)
        filas, info = tasksource_jev.convertir()
        self.assertEqual(len(filas), 1)
        self.assertEqual(info["descartadas_licencia_texto_nc"], 1)

    def test_trampa_sin_gliclass_xnli_anli_ni_derivados(self):
        """Falla si una tarea de GLiClass, XNLI o ANLI (o derivada) llega a la salida aunque la fila sea `commercial`."""
        malas = ["anli/a1", "multilingual/xnli", "gliclass/zeroshot", "multilingual/americas_nli/all_languages",
                 "dataset_train_nli", "multilingual/multilingual-NLI-26lang-2mil7", "r1_anli", "neutra/sin_pista"]
        fichas = {t: (t, "commercial", "mit") for t in malas}
        fichas["WANLI"] = ("alisawuffles/WANLI", "commercial", "cc-by-4.0")
        fichas["neutra/sin_pista"] = ("facebook/anli", "commercial", "mit")  # el nombre del dataset de origen delata
        filas_in = [falsos.fila_ts(i, source=t) for i, t in enumerate(malas + ["WANLI"])]
        falsos.tasksource(self.hub, filas_in, fichas)
        filas, info = tasksource_jev.convertir()
        self.assertEqual([f["tarea"] for f in filas], ["WANLI"])  # WANLI no es ANLI
        self.assertEqual(info["descartadas_prohibida"], len(malas))
        for f in filas:
            self.assertIsNone(comun.prohibida(f["fuente"], f["tarea"]))

    def test_filas_invalidas_se_cuentan(self):
        malas = [falsos.fila_ts(0, target=[0.5, 0.5]), falsos.fila_ts(1, options=["a", "a", "b"]),
                 falsos.fila_ts(2, target=[0.0, 0.0, 0.0]), falsos.fila_ts(3, kind="otro"),
                 falsos.fila_ts(4, state=" "), falsos.fila_ts(5, kind="noul", target=[1.5])]
        falsos.tasksource(self.hub, malas + [falsos.fila_ts(6)], FICHAS_OK)
        filas, info = tasksource_jev.convertir()
        self.assertEqual(len(filas), 1)
        self.assertEqual(info["descartadas_invalidas"], 6)

    def test_splits_ids_y_fragmento_sin_datos(self):
        falsos.tasksource(self.hub, [falsos.fila_ts(0), falsos.fila_ts(1)], FICHAS_OK,
                          filas_val=[falsos.fila_ts(2)], filas_test=[falsos.fila_ts(3)])
        filas, _ = tasksource_jev.convertir()
        self.assertEqual([f["id"] for f in filas], ["tsjev:train:0", "tsjev:train:1", "tsjev:dev:0", "tsjev:test:0"])
        d = falsos.snap(self.hub, "tasksource/tasksource-jev-typed-decisions")
        for p in (d / "data").glob("*.parquet"):
            p.unlink()
        filas, info = tasksource_jev.convertir()
        self.assertEqual((filas, info["sin_datos"]), ([], True))
        self.assertEqual(info["censo_sources_yaml"]["commercial"]["tareas"], 1)


class TestOtrasFuentes(Base):
    def test_synthetic_zeroshot(self):
        falsos.synthetic(self.hub)
        filas, info = synthetic_zeroshot.convertir()
        self.assertEqual(len(filas), 90)
        self.assertEqual(validar.errores_conjunto(filas), [])
        f = filas[0]
        self.assertEqual((f["tipo"], f["idioma"], f["licencia"], f["opciones"]), ("noul", "en", "apache-2.0", ["false", "true"]))
        self.assertIn(f["pregunta"], f["descripciones"]["true"])
        gato = [x for x in filas if x["pregunta"] == "Habla de gatos." and x["tarea"].endswith("categories")]
        self.assertTrue(all(x["etiqueta"] == "true" for x in gato))  # labels 0 = se cumple
        self.assertEqual({x["tarea"] for x in filas},
                         {"synthetic_zeroshot/refinedweb_categories", "synthetic_zeroshot/written_texts_for_tasks_v2"})
        por_texto = {}
        for x in filas:
            por_texto.setdefault(x["texto"], set()).add(x["split"])
        self.assertTrue(all(len(s) == 1 for s in por_texto.values()))

    def test_licencia_sin_confirmar_deja_solo_test(self):
        falsos.synthetic(self.hub, licencia="cc-by-nc-4.0", n_textos=300)
        filas, info = synthetic_zeroshot.convertir()
        self.assertTrue(filas)
        self.assertEqual({f["split"] for f in filas}, {"test"})
        self.assertTrue(all(not f["uso_comercial"] for f in filas))
        self.assertGreater(info["descartadas_licencia_nc_fuera_de_test"], 0)

    def test_pawsx_es(self):
        falsos.pawsx(self.hub)
        filas, info = pawsx_es.convertir()
        self.assertEqual(len(filas), 12)
        self.assertEqual(validar.errores_conjunto(filas), [])
        f = filas[1]
        self.assertEqual(f["texto"], "Frase uno 1." + pawsx_es.SEPARADOR + "Frase dos 1.")
        self.assertEqual((f["tipo"], f["etiqueta"], f["idioma"]), ("noul", "true", "es"))
        self.assertEqual(filas[0]["etiqueta"], "false")
        self.assertEqual({x["split"] for x in filas}, {"train", "dev", "test"})
        self.assertNotIn(pawsx_es.SEPARADOR.strip(), "Frase uno 0.Frase dos 0.")

    def test_pawsx_sin_libre_uso_en_la_tarjeta_solo_test(self):
        falsos.pawsx(self.hub, cuerpo="Sin condiciones claras.")
        filas, _ = pawsx_es.convertir()
        self.assertEqual({f["split"] for f in filas}, {"test"})
        self.assertFalse(any(f["uso_comercial"] for f in filas))

    def test_sib200_es(self):
        falsos.sib200(self.hub)
        filas, info = sib200_es.convertir()
        # SA sin decidir: solo test (7 de las 28 filas del falso; las 21 de train y dev se descartan)
        self.assertEqual(len(filas), 7)  # las comillas del texto no se comen líneas
        self.assertEqual({f["split"] for f in filas}, {"test"})
        self.assertFalse(any(f["uso_comercial"] for f in filas))
        self.assertEqual(info["descartadas_licencia_nc_fuera_de_test"], 21)
        self.assertEqual(validar.errores_conjunto(filas), [])
        self.assertEqual((len(filas[0]["opciones"]), filas[0]["tipo"]), (7, "choice"))
        falsos.sib200(self.hub, licencia="cc-by-nc-4.0")
        self.assertEqual({f["split"] for f in sib200_es.convertir()[0]}, {"test"})


class TestTrampasGlobales(Base):
    def test_ninguna_fuente_declarada_es_prohibida(self):
        for corto, mod in convertir.FUENTES.items():
            self.assertIsNone(comun.prohibida(mod.REPO, corto), mod.REPO)
        for mod in convertir.FUENTES.values():
            self.assertIsNone(comun.prohibida(getattr(mod, "CORTO")))

    def test_no_se_puede_abrir_un_repo_prohibido(self):
        for repo in ("knowledgator/gliclass-modern-base-v3.0", "facebook/xnli", "facebook/anli", "x/GLiClass-data"):
            with self.assertRaises(comun.FuenteProhibida):
                comun.raiz_hf(repo)

    def test_salida_rechaza_fila_prohibida_y_no_comercial_fuera_de_test(self):
        with tempfile.TemporaryDirectory() as d:
            s = comun.Salida(d)
            base = {"id": "x:train:0", "tarea": "t", "tipo": "noul", "split": "train", "fuente": "ok", "uso_comercial": True}
            for campo, valor in (("fuente", "facebook/xnli es train"), ("tarea", "anli/a1"), ("fuente", "gliclass x")):
                with self.assertRaises(comun.FuenteProhibida):
                    s.anadir("x", dict(base, **{campo: valor}))
            with self.assertRaises(ValueError):
                s.anadir("x", dict(base, uso_comercial=False))
            s.cerrar()
            self.assertEqual(s.resumen()["filas_total"], 0)

    def test_patron_prohibido_no_tiene_falsos_positivos_obvios(self):
        for ok in ("WANLI", "alisawuffles/WANLI", "multilingual/klue/nli", "tasksource/conj_nli", "nli4ct", "banking77"):
            self.assertIsNone(comun.prohibida(ok), ok)


class TestCorrer(Base):
    def test_extremo_a_extremo_trozos_y_resumen(self):
        falsos.tasksource(self.hub, [falsos.fila_ts(i, uso=("commercial", "non-commercial", "unspecified")[i % 3])
                                     for i in range(30)] + [falsos.fila_ts(99, kind="noul")], FICHAS_OK)
        falsos.synthetic(self.hub)
        falsos.pawsx(self.hub)
        falsos.sib200(self.hub)
        with tempfile.TemporaryDirectory() as d:
            res = convertir.correr(d, solo=[c for c in convertir.FUENTES if c != "tsinst"], chunk_bytes=2000)
            r = json.loads((Path(d) / "resumen.json").read_text(encoding="utf-8"))
            self.assertEqual(r["filas_por_fuente"], {"tsjev": 11, "synzs": 90, "pawsx": 12, "sib200": 7})
            self.assertEqual(r["descartadas"]["tsjev"], {"licencia_non-commercial": 10, "licencia_unspecified": 10})
            self.assertEqual(r["descartadas_por_licencia"]["tsjev"], r["descartadas"]["tsjev"])
            self.assertEqual(r["filas_por_tipo"]["choice"], 10 + 7)  # sib200: solo test
            self.assertEqual(r["filas_por_fuente_tipo_split"]["tsjev"]["choice"], {"train": 10})
            self.assertEqual(r["tareas_distintas"], 5)
            self.assertEqual(r["fuentes_vacias"], [])
            trozos = [f for f in r["ficheros"] if f.startswith("synzs/train-")]
            self.assertGreater(len(trozos), 1)
            n = 0
            for f in r["ficheros"]:
                with gzip.open(Path(d) / f, "rt", encoding="utf-8") as fh:
                    for linea in fh:
                        row = json.loads(linea)
                        self.assertEqual(validar.errores_fila(row), [])
                        self.assertTrue(row["uso_comercial"])
                        self.assertIsNone(comun.prohibida(row["fuente"], row["tarea"]))
                        n += 1
            self.assertEqual(n, r["filas_total"])

    def test_fuente_ausente_se_anota_y_main_falla(self):
        falsos.pawsx(self.hub)
        with tempfile.TemporaryDirectory() as d:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(convertir.main([d, "--solo", "pawsx,sib200"]), 2)
            self.assertIn("sib200", json.loads((Path(d) / "resumen.json").read_text(encoding="utf-8"))["ausentes"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(convertir.main([d, "--solo", "pawsx"]), 0)


if __name__ == "__main__":
    unittest.main()
