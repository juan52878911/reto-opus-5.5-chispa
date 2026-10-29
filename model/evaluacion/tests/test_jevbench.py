import json
import tempfile
import unittest
from pathlib import Path

from model.evaluacion import chispa_eval as CE
from model.evaluacion import jevbench as J
from model.evaluacion import jevbench_cascada as JC
from model.evaluacion import jevbench_informe as JI

FIX = Path(__file__).parent / "fixtures" / "jevbench"


def caso(i, estado="x", etq="a", labels=("a", "b"), grupo=None, tipo="choice", instr="¿Cuál?"):
    crit = {o: "desc " + o for o in labels} if tipo == "choice" else {"false": "no", "true": "sí"}
    return {"id": i, "family": "f", "group": grupo, "split": "public", "state": estado, "labels": list(labels), "expected": etq,
            "question": {"type": tipo, "instructions": instr, "criteria": crit}, "provenance": {"license": "MIT"}}


def escribir(d, casos):
    p = Path(d) / "datasets" / "public"
    p.mkdir(parents=True)
    (p / "easy.jsonl").write_text("".join(json.dumps(c) + "\n" for c in casos))
    return d


class TestCargar(unittest.TestCase):
    def test_fixture_real(self):
        filas = J.cargar_jevbench(FIX)
        self.assertEqual(len(filas), 13)
        self.assertEqual(len({f["id"] for f in filas}), 13)
        self.assertTrue(all(f["split"] == "test" and f["uso_comercial"] and f["licencia"] == "MIT" for f in filas))
        self.assertEqual(J.cargar_jevbench(FIX / "datasets" / "public")[0]["id"], filas[0]["id"])
        self.assertEqual({f["tipo"] for f in filas}, {"choice", "noul", "score"})
        for f in filas:   # el oro siempre es una opción y las filas pasan por el arnés
            self.assertIn(f["etiqueta"], f["opciones"])
        CE.evaluar(filas, [{"id": f["id"], "probs": {o: 1 / len(f["opciones"]) for o in f["opciones"]}} for f in filas])

    def test_conversiones(self):
        filas = {f["id"]: f for f in J.cargar_jevbench(FIX)}
        n = next(f for f in filas.values() if f["tipo"] == "noul")
        self.assertEqual(n["opciones"], ["false", "true"])
        self.assertEqual(n["etiqueta"], {"no": "false", "yes": "true"}[n["oro_jev"]])
        self.assertTrue(n["descripciones"]["true"])
        s = next(f for f in filas.values() if f["tipo"] == "score")
        self.assertEqual(s["etiqueta"], str(s["oro_jev"] + 1))
        self.assertEqual(s["opciones"][0], "1")
        d = [f for f in filas.values() if f["texto"].startswith("{")]
        self.assertTrue(d and isinstance(json.loads(d[0]["texto"]), dict))

    def test_fichero_suelto_y_errores(self):
        with tempfile.TemporaryDirectory() as t:
            escribir(t, [caso("c1")])
            self.assertEqual(len(J.cargar_jevbench(Path(t) / "datasets/public/easy.jsonl")), 1)
            bad = Path(t) / "mal.jsonl"
            bad.write_text(json.dumps({"id": "z"}) + "\n")
            with self.assertRaisesRegex(ValueError, "falta 'family'"):
                J.cargar_jevbench(bad)
            bad.write_text(json.dumps(caso("z", etq="c")) + "\n")
            with self.assertRaisesRegex(ValueError, "fuera de las opciones"):
                J.cargar_jevbench(bad)
            bad.write_text(json.dumps(caso("z", tipo="otro")) + "\n")
            with self.assertRaisesRegex(ValueError, "desconocido"):
                J.cargar_jevbench(bad)
            with self.assertRaisesRegex(ValueError, "no hay datasets"):
                J.cargar_jevbench(t + "/datasets")


class TestSoporte(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        casos = [caso("a1", etq="a", grupo="g1"), caso("a2", etq="a", grupo="g1"), caso("a3", etq="a"), caso("b1", etq="b"),
                 caso("b2", etq="b"), caso("solo", instr="otra pregunta")]
        self.f = J.cargar_jevbench(escribir(self.t.name, casos))
        self.por = {r["id"].split(":")[-1]: r for r in self.f}

    def tearDown(self):
        self.t.cleanup()

    def test_deja_fuera_caso_y_parafrasis(self):
        ids = {r["id"].split(":")[-1] for r in J.soporte(self.por["a1"], self.f, 8)}
        self.assertEqual(ids, {"a3", "b1", "b2"})   # sin a1 ni su paráfrasis a2, y sin el de otro esquema
        self.assertEqual(J.soporte(self.por["solo"], self.f, 8), [])

    def test_tope_k_por_opcion(self):
        s = J.soporte(self.por["a3"], self.f, 1)
        self.assertEqual(sorted(r["etiqueta"] for r in s), ["a", "b"])
        self.assertEqual(J.soporte(self.por["a3"], self.f, 1), s)   # determinista

    def test_pliegues_y_cobertura(self):
        pl = {c[1]: (rs, sop) for c, rs, sop in J.pliegues(self.f, 8)}
        self.assertEqual({r["id"].split(":")[-1] for r in pl["g1"][0]}, {"a1", "a2"})   # las paráfrasis son un pliegue
        self.assertEqual(len(pl), 5)
        self.assertTrue(J.cubre_opciones(pl["g1"][0][0], pl["g1"][1]))
        sop_b1 = pl[self.por["b1"]["id"]][1]
        self.assertTrue(J.cubre_opciones(self.por["b1"], sop_b1))
        self.assertFalse(J.cubre_opciones(self.por["a3"], [r for r in sop_b1 if r["etiqueta"] == "b"]))

    def test_esquema_incluye_instrucciones(self):
        self.assertNotEqual(self.por["a1"]["esquema"], self.por["solo"]["esquema"])
        self.assertEqual(self.por["a1"]["esquema"], self.por["b2"]["esquema"])


class TestCascadaYInforme(unittest.TestCase):
    def test_esquema_y_cuerpo(self):
        filas = {f["id"]: f for f in J.cargar_jevbench(FIX)}
        for f in filas.values():
            e = JC.esquema_json(f)
            self.assertEqual(list(e["opciones"]), f["opciones"])
            q = JC.cuerpo_decide(f)["questions"][0]
            self.assertEqual(q["kind"], f["tipo"])
            if f["tipo"] == "noul":
                self.assertNotIn("options", q)
            else:
                self.assertEqual([o["id"] for o in q["options"]], f["opciones"])

    def test_informe(self):
        with tempfile.TemporaryDirectory() as t:
            casos = [caso(f"c{i}", etq="a" if i % 2 else "b", instr="q") for i in range(6)]
            filas = J.cargar_jevbench(escribir(t + "/jev", casos))
            d = Path(t) / "sal"
            (d / "pred").mkdir(parents=True)
            (d / "jevbench_filas.jsonl").write_text("".join(json.dumps(f) + "\n" for f in filas))

            def pred(f, bien, **x):
                o = f["etiqueta"] if bien else next(o for o in f["opciones"] if o != f["etiqueta"])
                return dict({"id": f["id"], "probs": {o2: (0.9 if o2 == o else 0.1) for o2 in f["opciones"]}, "ms": 1.0}, **x)
            w = lambda n, ps: (d / "pred" / f"{n}.jsonl").write_text("".join(json.dumps(p) + "\n" for p in ps))
            w("l2_k0", [pred(f, i < 3, soporte_n=0) for i, f in enumerate(filas)])
            w("l2_k8", [pred(f, i < 5, soporte_n=5) for i, f in enumerate(filas)])
            w("cascada_k8", [pred(f, i < 4, escalate=i == 5, layer="L0") for i, f in enumerate(filas[:5])])
            (d / "pred" / "cascada_k8_omitidos.json").write_text(json.dumps([{"id": filas[5]["id"], "motivo": "sin tiempo"}]))
            txt = JI.informe(d)
            r = json.loads((d / "informe.json").read_text())
            self.assertAlmostEqual(r["variantes"]["l2_k0"]["todos"]["exactitud"], 0.5)
            self.assertAlmostEqual(r["variantes"]["l2_k8"]["todos"]["exactitud"], 5 / 6)
            self.assertEqual(r["variantes"]["cascada_k8"]["cascada"]["n"], 5)
            self.assertEqual(r["variantes"]["cascada_k8"]["cascada"]["escalados"], 0)
            self.assertFalse(r["H1"]["cumple"])
            self.assertEqual(r["H2"]["l2_k8"]["mejora_en"], 2)   # casos 3 y 4
            self.assertEqual(r["H2"]["cascada_k8"]["empeora_en"], 0)
            self.assertIn("H1", txt)
            self.assertIn("1 sin tiempo", txt)

    def test_wilson(self):
        lo, hi = JI.wilson(55, 100)
        self.assertLess(lo, 0.55)
        self.assertGreater(hi, 0.55)
        self.assertEqual(JI.wilson(0, 0), (None, None))


if __name__ == "__main__":
    unittest.main()
