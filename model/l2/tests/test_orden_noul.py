import gzip
import json
import tempfile
import unittest
from pathlib import Path

from model.l2 import contar_orden_noul as c
from model.l2.modelo import texto_consulta, texto_opcion
from model.l2.tests.falso import fila


def texto_anterior(f):   # implementación previa a R9b
    return texto_opcion(f, f["opciones"][-1])


class TextoConsulta(unittest.TestCase):
    def test_false_true_igual_que_antes(self):
        for tipo, k in (("noul", None), ("score", 5), ("score", 3)):
            f = fila(1, tipo, k=k)
            self.assertEqual(texto_consulta(f), texto_anterior(f))

    def test_true_false_usa_true(self):
        f = fila(1, "noul")
        f["opciones"] = ["true", "false"]
        self.assertEqual(texto_consulta(f), texto_opcion(f, "true"))
        self.assertNotEqual(texto_consulta(f), texto_anterior(f))

    def test_noul_sin_true_falla(self):
        f = fila(1, "noul")
        f["opciones"] = ["no", "si"]
        with self.assertRaisesRegex(ValueError, "sin opción «true»"):
            texto_consulta(f)

    def test_score_desordenado(self):
        f = fila(1, "score", k=4)
        f["opciones"] = ["3", "1", "4", "2"]
        self.assertEqual(texto_consulta(f), texto_opcion(f, "4"))
        f["opciones"] = ["10", "9", "2"]   # no 1..K contiguos: error (R16)
        with self.assertRaises(ValueError):
            texto_consulta(f)
        f["opciones"] = ["a", "b"]
        with self.assertRaises(ValueError):
            texto_consulta(f)

    def test_igual_que_el_exportador(self):
        from model.l2.exportar import texto_torre_consulta
        for ops, tipo in ((["true", "false"], "noul"), (["false", "true"], "noul"), (["2", "5", "1", "4", "3"], "score")):
            f = dict(fila(1, tipo), opciones=ops)
            self.assertEqual(texto_consulta(f), texto_torre_consulta(f))


class Recuento(unittest.TestCase):
    def test_meta_y_tabla(self):
        def f(tipo, ops, split="train"):
            return {"tipo": tipo, "opciones": ops, "tarea": "t", "split": split}
        filas = [f("noul", ["false", "true"]), f("noul", ["true", "false"]), f("noul", ["true", "false"], "dev"),
                 f("noul", ["true", "x", "false"]), f("noul", ["a", "b"]), f("choice", ["true", "false"])]
        with tempfile.TemporaryDirectory() as d:
            for fuente in ("tsjev", "tsinst"):
                (Path(d) / "meta" / fuente).mkdir(parents=True)
                with gzip.open(Path(d) / "meta" / fuente / "train-0.jsonl.gz", "wt", encoding="utf-8") as fh:
                    fh.write("\n".join(json.dumps(r, ensure_ascii=False) for r in filas) + "\n")
                    fh.write(json.dumps({"tipo": "noul", "opciones": ["false", "true"], "tarea": "u", "split": "train",
                                         "pregunta": "a b"}) + "\n")
            n = c.main(["--salida", d + "/o", "--meta", d + "/meta"])
            self.assertEqual(n, 0)
            r = json.load(open(d + "/o/orden-noul.json"))
            self.assertEqual(r["total"], {"noul": 12, "true_false": 4, "true_no_ultima": 6, "afectadas": 6, "sin_true": 2})
            self.assertEqual({x["fuente"] for x in r["filas"]}, {"meta/tsjev", "meta/tsinst"})
            self.assertIn("| meta/tsjev | t | dev | 1 | 1 | 1 | 1 | 0 |", open(d + "/o/orden-noul.md").read())

    def test_jevbench_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            c.main(["--salida", d, "--jevbench", "model/evaluacion/tests/fixtures/jevbench"])
            self.assertGreater(json.load(open(d + "/orden-noul.json"))["total"]["noul"], 0)


if __name__ == "__main__":
    unittest.main()
