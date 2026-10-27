import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import unittest
from collections import Counter

from model.etiquetado import acuerdo, preparar

AQUI = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(AQUI, "..", "etiquetar.html")


class TestKappa(unittest.TestCase):
    def test_acuerdo_total(self):
        self.assertAlmostEqual(acuerdo.kappa([("a", "a"), ("b", "b"), ("a", "a"), ("b", "b")]), 1.0)

    def test_acuerdo_por_azar(self):
        # a: 2 sí 2 no; b: 2 sí 2 no; coinciden en 2 de 4 -> po=.5, pe=.5 -> κ=0
        pares = [("s", "s"), ("s", "n"), ("n", "s"), ("n", "n")]
        self.assertAlmostEqual(acuerdo.kappa(pares), 0.0)

    def test_a_mano(self):
        # 20 pares: 10 s-s, 5 s-n, 0 n-s, 5 n-n -> po=.75; a: 15 s/5 n; b: 10 s/10 n
        # pe = (15*10 + 5*10)/400 = .5 -> κ = .25/.5 = .5
        pares = [("s", "s")] * 10 + [("s", "n")] * 5 + [("n", "n")] * 5
        self.assertAlmostEqual(acuerdo.kappa(pares), 0.5)

    def test_una_sola_clase(self):
        self.assertEqual(acuerdo.kappa([("a", "a")] * 3), 1.0)
        self.assertIsNone(acuerdo.kappa([]))


class TestAnalisis(unittest.TestCase):
    def test_adjudicar_y_discrepancias(self):
        oro = {"1": {"tarea": "t", "etiqueta": "x"}, "2": {"tarea": "t", "etiqueta": "x"},
               "3": {"tarea": "t", "etiqueta": "z"}}
        A = {i: {"id": i, "etiqueta": e} for i, e in (("1", "x"), ("2", "x"), ("3", "x"))}
        B = {i: {"id": i, "etiqueta": e, "dudoso": i == "3"} for i, e in (("1", "x"), ("2", "y"), ("3", "y"))}
        r = acuerdo.analizar(A, B, oro)
        self.assertEqual([d["id"] for d in r["discrepancias"]], ["2", "3"])
        adj = {x["id"]: x for x in r["adjudicado"]}
        self.assertEqual(adj["1"]["etiqueta"], "x")
        self.assertEqual(adj["2"]["etiqueta"], "x")      # el original desempata
        self.assertTrue(adj["3"]["conflicto"])           # ni a ni b coinciden con el original
        self.assertIsNone(adj["3"]["etiqueta"])
        self.assertAlmostEqual(r["con_original"]["a"], 2 / 3)
        self.assertAlmostEqual(r["con_original"]["b"], 1 / 3)
        self.assertEqual(r["confusion"]["t"]["x"]["y"], 2)


def fila(i, tarea, etiqueta, comercial=True, split="test"):
    return {"id": "f:%s:%d" % (split, i), "tarea": tarea, "etiqueta": etiqueta, "split": split,
            "uso_comercial": comercial, "texto": "t", "opciones": ["a", "b", "c"]}


class TestPreparar(unittest.TestCase):
    def setUp(self):
        self.filas = ([fila(i, "T", "a") for i in range(100)] + [fila(100 + i, "T", "b") for i in range(100)]
                      + [fila(200 + i, "T", "c") for i in range(10)]
                      + [fila(300 + i, "U", "a") for i in range(5)]
                      + [fila(400, "T", "a", split="train"), fila(401, "T", "a", comercial=False)])

    def test_estratificada(self):
        m = [f for f in preparar.preparar(self.filas, 30, 7) if f["tarea"] == "T"]
        self.assertEqual(len(m), 30)
        self.assertEqual(Counter(f["etiqueta"] for f in m), {"a": 10, "b": 10, "c": 10})

    def test_clase_pequena_reparte_el_resto(self):
        m = [f for f in preparar.preparar(self.filas, 60, 7) if f["tarea"] == "T"]
        self.assertEqual(Counter(f["etiqueta"] for f in m), {"a": 25, "b": 25, "c": 10})

    def test_solo_test_y_comercial(self):
        m = preparar.preparar(self.filas, 1000, 7)
        self.assertTrue(all(f["split"] == "test" and f["uso_comercial"] is not False for f in m))
        self.assertEqual(Counter(f["tarea"] for f in m), {"T": 210, "U": 5})
        m2 = preparar.preparar(self.filas, 1000, 7, incluir_no_comercial=True)
        self.assertEqual(len(m2), 216)

    def test_determinista(self):
        self.assertEqual(preparar.preparar(self.filas, 30, 7), preparar.preparar(self.filas, 30, 7))
        self.assertNotEqual(preparar.preparar(self.filas, 30, 7), preparar.preparar(self.filas, 30, 8))


@unittest.skipUnless(shutil.which("node"), "node no está instalado: el HTML no se prueba")
class TestIdsComoElArnes(unittest.TestCase):
    def test_ids_coinciden_con_chispa_eval(self):
        from model.evaluacion import chispa_eval
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        ruta = os.path.join(d, "sondeo_x.jsonl")
        with open(ruta, "w", encoding="utf-8") as f:
            for i in range(5):
                f.write(json.dumps({"tarea": "T", "etiqueta": "a", "split": "test", "texto": str(i)}) + "\n")
        esperados = [r["id"] for r in chispa_eval.asignar_ids(preparar.leer([ruta]), ruta)]
        with open(ruta, encoding="utf-8") as f:
            crudas = [json.loads(l) for l in f]
        self.assertEqual([r["id"] for r in preparar.leer([ruta])], esperados)
        self.assertEqual([r["id"] for r in chispa_eval.asignar_ids(crudas, ruta)],
                         ["sondeo_x:test:%d" % n for n in range(5)])


class TestHTML(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(HTML, encoding="utf-8") as f:
            src = f.read()
        m = re.search(r"// ==PURO==(.*?)// ==FIN==", src, re.S)
        assert m, "faltan los marcadores PURO/FIN"
        cls.js = m.group(1)
        cls.sin_red = not re.search(r"https?://|<link|src=", src)

    def node(self, codigo):
        r = subprocess.run(["node", "-e", self.js + codigo], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_sin_dependencias_externas(self):
        self.assertTrue(self.sin_red)

    def test_parseo(self):
        out = self.node("""
          var p = parseJSONL('{"id":"a","texto":"x","opciones":["1"]}\\n\\nbasura\\r\\n{"id":"b","texto":"y","opciones":["1","2"]}\\n{"id":3}');
          console.log(JSON.stringify([p.filas.length, p.errores]));""")
        self.assertEqual(json.loads(out), [2, [3, 5]])

    def test_exportar(self):
        out = self.node("""
          process.stdout.write(exportarJSONL({b:{etiqueta:"y",ts:"T2",dudoso:true}, a:{etiqueta:"x",ts:"T1"}, c:{dudoso:true}}, "ana"));""")
        filas = [json.loads(l) for l in out.splitlines()]
        self.assertEqual(filas, [{"id": "a", "etiqueta": "x", "anotador": "ana", "ts": "T1", "dudoso": False},
                                 {"id": "b", "etiqueta": "y", "anotador": "ana", "ts": "T2", "dudoso": True}])
        self.assertEqual(list(filas[0]), ["id", "etiqueta", "anotador", "ts", "dudoso"])

    def test_orden_con_semilla_por_anotador(self):
        out = self.node("""
          var f=[];for(var i=0;i<20;i++)f.push({id:String(i)});
          var o=function(n){return barajar(f,semillaDeNombre(n)).map(function(x){return x.id}).join(",")};
          console.log(JSON.stringify([o("ana")===o("ana"), o("ana")!==o("luis"), o("ana").split(",").length]));""")
        self.assertEqual(json.loads(out), [True, True, 20])

    def test_la_etiqueta_original_no_se_muestra(self):
        with open(HTML, encoding="utf-8") as f:
            codigo = f.read().split("// ==FIN==")[1]
        # la fila (f) nunca se lee por su etiqueta; solo la respuesta (r) del anotador
        self.assertIsNone(re.search(r"\bf\.etiqueta|filas\[[^\]]*\]\.etiqueta", codigo))


class TestFlujoExtremo(unittest.TestCase):
    def test_preparar_y_acuerdo_por_cli(self):
        with tempfile.TemporaryDirectory() as d:
            ent = os.path.join(d, "e.jsonl")
            filas = [fila(i, "T", "ab"[i % 2]) for i in range(40)]
            with open(ent, "w") as f:
                f.write("\n".join(json.dumps(x) for x in filas))
            mu = os.path.join(d, "m.jsonl")
            self.assertEqual(preparar.main(["--entrada", ent, "--por-tarea", "10", "--salida", mu]), 0)
            muestra = acuerdo.leer(mu)
            self.assertEqual(len(muestra), 10)
            ex = {}
            for n, i in enumerate(sorted(muestra)):
                ex[i] = {"id": i, "etiqueta": muestra[i]["etiqueta"], "anotador": "x", "ts": "t", "dudoso": False}
            r = acuerdo.analizar(ex, ex, muestra)
            self.assertEqual(r["kappa_global"], 1.0)
            self.assertEqual(r["con_original"], {"a": 1.0, "b": 1.0})


if __name__ == "__main__":
    unittest.main()
