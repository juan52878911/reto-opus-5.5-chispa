"""G.8: tasksource-instruct-v0, tareas que se dejan fuera y reparto por tarea (todo con datos inventados)."""
import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from model.datos import validar
from model.meta import comun, convertir, muestreo, tasksource_instruct as TI
from model.meta.tests import falsos

COMERCIALES = {"demo/sentimiento", "demo/abierta", "demo/rara", "demo/noprohibida", "demo/anli_r1"}


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.hub = Path(self._t.name) / "hf"
        self.addCleanup(self._t.cleanup)
        p = mock.patch.dict(os.environ, {"HF_HOME": str(self.hub)})
        p.start()
        self.addCleanup(p.stop)


class TestInstruct(Base):
    def datos(self):
        train = [falsos.fila_inst(i) for i in range(30)]
        train += [{"inputs": "Texto %d" % i, "targets": "respuesta libre número %d" % i, "task": "demo/abierta"} for i in range(30)]
        train += [falsos.fila_inst(i, "demo/rara", ("a", "b")) for i in range(3)] + [falsos.fila_inst(3, "demo/rara", ("c",))]
        train += [falsos.fila_inst(i, "demo/pagada") for i in range(30)]          # no figura como comercial
        train += [falsos.fila_inst(i, "demo/anli_r1") for i in range(30)]         # ANLI: prohibida aunque conste comercial
        falsos.instruct(self.hub, train, [falsos.fila_inst(i) for i in range(6)])

    def test_solo_comercial_cerrado_y_sin_prohibidas(self):
        self.datos()
        fs, info = TI.convertir(comerciales=COMERCIALES)
        self.assertEqual({f["tarea"] for f in fs}, {"instruct/demo/sentimiento"})
        self.assertEqual(len([f for f in fs if f["split"] == "train"]), 30)
        self.assertEqual(len([f for f in fs if f["split"] == "dev"]), 6)
        f = fs[0]
        self.assertEqual(f["opciones"], ["negativo", "neutro", "positivo"])
        self.assertEqual(f["tipo"], "choice")
        self.assertIn(f["etiqueta"], f["opciones"])
        self.assertEqual(f["blanda"][f["etiqueta"]], 1.0)
        self.assertEqual(validar.errores_fila(f), [])
        self.assertEqual(info["descartadas_tarea_no_comercial"], 60)   # demo/pagada y la de ANLI, que sale de la lista
        self.assertGreaterEqual(info["descartadas_tarea_abierta"], 30)
        self.assertEqual(info["tareas_con_vocabulario"], 1)

    def test_sin_lista_comercial_no_convierte(self):
        self.datos()
        fs, info = TI.convertir(comerciales=set())
        self.assertEqual(fs, [])
        self.assertTrue(info["sin_datos"])

    def test_comercial_sale_de_sources_yaml_de_tsjev(self):
        self.datos()
        falsos.tasksource(self.hub, [falsos.fila_ts(0)], {"demo/sentimiento": ("d", "commercial", "mit"),
                                                          "demo/pagada": ("d", "non-commercial", "cc-by-nc")})
        self.assertEqual(TI.tareas_comerciales(), {"demo/sentimiento"})
        fs, _ = TI.convertir()
        self.assertEqual({f["tarea"] for f in fs}, {"instruct/demo/sentimiento"})

    def test_tope_por_tarea_y_ids_sin_huecos(self):
        self.datos()
        fs, _ = TI.convertir(comerciales=COMERCIALES, tope_tarea=10)
        tr = [f for f in fs if f["split"] == "train"]
        self.assertEqual(len(tr), 10)
        self.assertEqual([f["id"] for f in tr], ["tsinst:train:%d" % i for i in range(10)])

    def test_extremo_a_extremo_con_el_resto(self):
        self.datos()
        with mock.patch.dict(os.environ, {"CHISPA_INSTRUCT_TAREAS": str(self._escribir_lista())}):
            with tempfile.TemporaryDirectory() as d:
                import contextlib, io
                with contextlib.redirect_stdout(io.StringIO()):
                    convertir.correr(d, solo=["tsinst"])
                r = json.loads((Path(d) / "resumen.json").read_text(encoding="utf-8"))
                self.assertEqual(r["filas_por_fuente"], {"tsinst": 36})
                with gzip.open(Path(d) / r["ficheros"][0], "rt", encoding="utf-8") as fh:
                    self.assertIsNone(comun.prohibida(json.loads(fh.readline())["tarea"]))

    def _escribir_lista(self):
        p = Path(self._t.name) / "tareas.txt"
        p.write_text("# comerciales\ndemo/sentimiento\n", encoding="utf-8")
        return p


class TestFuera(unittest.TestCase):
    def test_lista_fija_con_semilla_y_proporcion(self):
        tareas = ["t/%d" % i for i in range(2000)]
        fuera = muestreo.lista_fuera(tareas)
        self.assertEqual(fuera, muestreo.lista_fuera(list(reversed(tareas))))     # no depende del orden
        self.assertTrue(0.08 < len(fuera) / len(tareas) < 0.12)
        self.assertEqual(muestreo.lista_fuera(tareas, semilla=1) == fuera, False)

    def test_la_misma_tarea_cae_igual_en_tsjev_y_en_instruct(self):
        for i in range(200):
            t = "demo/%d" % i
            self.assertEqual(muestreo.tarea_fuera(t), muestreo.tarea_fuera("instruct/" + t))

    def test_solo_afecta_a_tasksource(self):
        fila = {"id": "massive:train:0", "tarea": "x"}
        self.assertFalse(muestreo.es_fuera(fila))
        n = sum(muestreo.es_fuera({"id": "tsjev:train:0", "tarea": "demo/%d" % i}) for i in range(1000))
        self.assertTrue(50 < n < 150)

    def test_cupos(self):
        c = {"a": 10, "b": 500, "c": 5000}
        self.assertEqual(muestreo.cupos(c, 100), {"a": 10, "b": 100, "c": 100})
        k = muestreo.cupos(c, 1000, maximo=210)
        self.assertEqual(k["a"], 10)
        self.assertLessEqual(sum(k.values()), 210)
        self.assertGreaterEqual(sum(k.values()), 200)
        self.assertEqual(muestreo.cupos(c, 1000, maximo=10_000), {"a": 10, "b": 500, "c": 1000})


if __name__ == "__main__":
    unittest.main()
