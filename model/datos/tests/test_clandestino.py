import csv
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from model.datos import clandestino, convertir, validar

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "clandestino"


def copia(d, cab=None, filas=None, licencia="mit"):
    """Snapshot de fixture en `d` con otras columnas o filas, o con otra licencia en la tarjeta."""
    d = Path(d)
    (d / "README.md").write_text("---\nlicense: %s\n---\n# t\n" % licencia, encoding="utf-8")
    with open(FIX / "clandestino.csv", encoding="utf-8", newline="") as fh:
        base = list(csv.DictReader(fh))
    filas = base if filas is None else filas
    cab = cab or list(base[0])
    with open(d / "datos.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cab, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    return d


class Clandestino(unittest.TestCase):
    def setUp(self):
        self.filas, self.info = clandestino.convertir(FIX)

    def test_solo_filas_de_personas(self):
        self.assertEqual(self.info["descartadas_ia"], 30)
        self.assertFalse(any("máquina" in f["texto"] for f in self.filas))
        self.assertEqual({f["texto"] for f in self.filas}, {f["texto"] for f in self.filas if "inventado" in f["texto"]})

    def test_filas_validas_y_licencia(self):
        self.assertEqual(validar.errores_conjunto(self.filas), [])
        self.assertTrue(all(f["licencia"] == "MIT" and f["uso_comercial"] is True for f in self.filas))
        self.assertEqual(self.info["licencia"], "MIT")
        self.assertEqual({f["split"] for f in self.filas}, {"train", "dev", "test"})

    def test_cuatro_familias_de_anotacion(self):
        por = defaultdict(list)
        for f in self.filas:
            por[f["tarea"]].append(f)
        self.assertEqual(sorted(por), ["clandestino_danino", "clandestino_gravedad", "clandestino_grupo_estudiantes",
                                       "clandestino_grupo_turistas", "clandestino_grupo_vecinos", "clandestino_tipo"])
        self.assertEqual({f["tipo"] for f in por["clandestino_gravedad"]}, {"score"})
        self.assertEqual(por["clandestino_gravedad"][0]["opciones"], ["1", "2", "3", "4", "5"])
        self.assertEqual({f["etiqueta"] for f in por["clandestino_gravedad"]}, {"1", "2", "3", "4", "5"})
        self.assertEqual({f["tipo"] for f in por["clandestino_danino"]}, {"noul"})
        t = por["clandestino_tipo"]
        self.assertEqual((t[0]["tipo"], t[0]["opciones"]), ("choice", ["amenaza", "burla", "exclusion"]))
        self.assertTrue(all(f["pregunta"].startswith("¿") for f in self.filas))
        # multi -> una noul por grupo y mensaje, con la etiqueta de pertenencia
        g = [f for f in por["clandestino_grupo_vecinos"]]
        self.assertEqual({f["etiqueta"] for f in g}, {"false", "true"})
        self.assertEqual(len(g), len(por["clandestino_tipo"]))

    def test_plantilla_en_un_solo_split(self):
        split = {}
        for f in self.filas:
            self.assertEqual(split.setdefault(f["plantilla"], f["split"]), f["split"], "fuga de la plantilla %s" % f["plantilla"])
        # y el mismo mensaje no cae en dos splits
        textos = {}
        for f in self.filas:
            self.assertEqual(textos.setdefault(f["texto"], f["split"]), f["split"])

    def test_tarjeta_sin_mit_deja_solo_test(self):
        with tempfile.TemporaryDirectory() as d:
            filas, info = clandestino.convertir(copia(d, licencia="cc-by-nc-4.0"))
        self.assertTrue(filas)
        self.assertEqual({f["split"] for f in filas}, {"test"})
        self.assertTrue(all(f["uso_comercial"] is False and f["licencia"].startswith("sin verificar") for f in filas))
        self.assertEqual(validar.errores_conjunto(filas), [])
        self.assertGreater(info["descartadas_licencia_nc_fuera_de_test"], 0)

    def test_valores_invalidos_se_descartan_y_se_cuentan(self):
        with open(FIX / "clandestino.csv", encoding="utf-8", newline="") as fh:
            base = [r for r in csv.DictReader(fh) if r["Is AI Generated"] == "false"]
        base[0]["Score"], base[1]["Score"], base[2]["Label"], base[3]["Type"] = "0", "6", "quizá", ""
        with tempfile.TemporaryDirectory() as d:
            filas, info = clandestino.convertir(copia(d, filas=base))
        self.assertEqual(info["descartadas_invalidas"], {"score_fuera_de_1_5": 2, "sino_ilegible": 1, "tipo_vacio": 1})
        self.assertEqual(sum(f["tarea"] == "clandestino_gravedad" for f in filas), len(base) - 2)

    def test_grupos_con_poco_soporte_no_dan_pregunta(self):
        with tempfile.TemporaryDirectory() as d:
            filas, info = clandestino.convertir(copia(d), min_grupo=10 ** 6)
        self.assertEqual(info["grupos"], [])
        self.assertFalse(any(f["tarea"].startswith("clandestino_grupo") for f in filas))

    def test_columnas_con_otro_formato_de_nombre(self):
        with open(FIX / "clandestino.csv", encoding="utf-8", newline="") as fh:
            base = list(csv.DictReader(fh))
        ren = {"Text": "message", "Is AI Generated": "is_ai_generated", "Template ID": "template-id", "Score": "Rating"}
        filas = [{ren.get(k, k): v for k, v in r.items()} for r in base]
        with tempfile.TemporaryDirectory() as d:
            f2, _ = clandestino.convertir(copia(d, cab=list(filas[0]), filas=filas))
        self.assertEqual(f2, self.filas)

    def test_falla_con_mensaje_claro_si_las_columnas_no_coinciden(self):
        for quita, frag in (("Is AI Generated", "falta la columna Is AI Generated"), ("Template ID", "falta la columna Template ID"),
                            ("Text", "falta la columna Text")):
            with tempfile.TemporaryDirectory() as d:
                cab = [c for c in ("Text", "Is AI Generated", "Template ID", "Score") if c != quita]
                with self.assertRaises(ValueError) as cm:
                    clandestino.convertir(copia(d, cab=cab))
            self.assertIn(frag, str(cm.exception))
            self.assertIn("el fichero trae", str(cm.exception))   # lista las columnas que sí hay
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError) as cm:
                clandestino.convertir(copia(d, cab=["Text", "Is AI Generated", "Template ID", "Language"]))
        self.assertIn("ninguna columna de anotación", str(cm.exception))

    def test_ia_ilegible_falla(self):
        with tempfile.TemporaryDirectory() as d:
            with open(FIX / "clandestino.csv", encoding="utf-8", newline="") as fh:
                base = list(csv.DictReader(fh))
            base[0]["Is AI Generated"] = "tal vez"
            with self.assertRaises(ValueError):
                clandestino.convertir(copia(d, filas=base))

    def test_en_convertir_es_opcional(self):
        self.assertNotIn("clandestino", convertir.FUENTES)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(convertir.main(["--salida", d, "--fixtures", "--fuentes", "clandestino"]), 0)
            self.assertTrue((Path(d) / "clandestino.jsonl").is_file())
            self.assertEqual(validar.main([str(Path(d) / "clandestino.jsonl")]), 0)
        with tempfile.TemporaryDirectory() as d:
            convertir.main(["--salida", d, "--fixtures", "--fuentes", "massive"])
            self.assertFalse((Path(d) / "clandestino.jsonl").exists())

    def test_licencias_md_recoge_la_fuente(self):
        txt = (Path(clandestino.__file__).parent / "LICENCIAS.md").read_text(encoding="utf-8")
        fila = next(l for l in txt.splitlines() if "microsoft/Clandestino" in l)
        for frag in ("MIT", "no dañar", "vigilancia", "aceptada por Juan, 2026-11-02", "Is AI Generated"):
            self.assertIn(frag, fila)


if __name__ == "__main__":
    unittest.main()
