"""W2: robustez (M3), español frente a inglés (M4) y umbrales de la batería (M1). Sin modelos ni red."""
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "sdk" / "python"))

from chispa.variantes import generar   # noqa: E402

from model.l2 import espanol, robustez, umbrales_bateria   # noqa: E402

FILA = {"id": "t:test:1", "tarea": "intencion", "tipo": "choice", "pregunta": "¿Qué quiere hacer el usuario con el asistente?",
        "texto": "pon una alarma para mañana a las siete y media", "opciones": ["alarm_set", "weather_query", "general_greet"],
        "descripciones": {"alarm_set": "poner una alarma", "weather_query": "preguntar por el tiempo", "general_greet": "saludar"},
        "etiqueta": "weather_query", "idioma": "es", "split": "test"}
NOUL = {"id": "h:test:1", "tarea": "toxicidad", "tipo": "noul", "pregunta": "¿El mensaje contiene odio o es tóxico contra una persona o un grupo?",
        "texto": "eres un desastre", "opciones": ["false", "true"], "etiqueta": "true", "idioma": "es", "split": "test",
        "descripciones": {"false": "mensaje respetuoso o no ofensivo, aunque mencione grupos o insultos sin atacar",
                          "true": "mensaje de odio o tóxico contra una persona o un grupo"}}


class TestGenerador(unittest.TestCase):
    def var(self, fila, tipo, semilla=0):
        return robustez.variantes_de(fila, tipo, semilla, generar)

    def test_determinista(self):
        for t in robustez.TIPOS:
            self.assertEqual(self.var(FILA, t, 3), self.var(FILA, t, 3), t)
        self.assertEqual(self.var(FILA, "erratas", 5), self.var(FILA, "erratas", 5))
        self.assertNotEqual(self.var(FILA, "renombrar", 1)["opciones"], self.var(FILA, "renombrar", 2)["opciones"])

    def test_permutar_conserva_etiqueta_y_opciones(self):
        for s in range(10):
            v = self.var(FILA, "permutar", s)
            self.assertEqual(v["etiqueta"], FILA["etiqueta"])
            self.assertEqual(sorted(v["opciones"]), sorted(FILA["opciones"]))
            self.assertEqual(v["descripciones"], FILA["descripciones"])

    def test_renombrar_mapea_etiqueta_y_descripciones(self):
        v = self.var(FILA, "renombrar")
        self.assertEqual(v["etiqueta"], v["mapa"][FILA["etiqueta"]])
        self.assertEqual(len(set(v["opciones"])), 3)
        self.assertFalse(set(v["opciones"]) & set(FILA["opciones"]))
        for o in FILA["opciones"]:
            self.assertEqual(v["descripciones"][v["mapa"][o]], FILA["descripciones"][o])

    def test_permutar_y_renombrar_solo_en_choice(self):
        self.assertIsNone(self.var(NOUL, "permutar"))
        self.assertIsNone(self.var(NOUL, "renombrar"))
        self.assertIsNotNone(self.var(NOUL, "erratas"))

    def test_no_modifica_la_fila(self):
        copia = json.loads(json.dumps(FILA))
        for t in robustez.TIPOS:
            self.var(FILA, t)
        self.assertEqual(FILA, copia)

    def test_es_en(self):
        v = self.var(FILA, "pregunta_en")
        self.assertEqual(v["pregunta"], "What does the user want to do with the assistant?")
        self.assertEqual(v["descripciones"], FILA["descripciones"])
        self.assertIsNone(self.var(FILA, "esquema_en"))   # sin descripciones traducibles: no medido
        v = self.var(NOUL, "esquema_en")
        self.assertTrue(v["descripciones"]["true"].startswith("hateful"))
        self.assertEqual(v["etiqueta"], "true")
        otra = dict(FILA, pregunta="¿Otra pregunta?")
        self.assertIsNone(self.var(otra, "pregunta_en"))

    def test_estadistica(self):
        lo, hi = robustez.wilson(5, 100)
        self.assertLess(lo, 0.05)
        self.assertGreater(hi, 0.05)
        m, a, b = robustez.media_ic([1, 0, 0, -1, 0, 1])
        self.assertLessEqual(a, m)
        self.assertGreaterEqual(b, m)
        r = robustez.resumir([(True, True, False), (False, True, True), (False, False, False)])
        self.assertEqual((r["n"], r["cambian"]), (3, 1))
        self.assertAlmostEqual(r["delta_acc"], -1 / 3)


class TestEspanol(unittest.TestCase):
    HF = str(RAIZ / "model" / "l2" / "tests" / "fixtures_espanol")

    def test_pares_mismo_numero_y_esquema(self):
        pares, nm = espanol.cargar_pares(self.HF, 8)
        self.assertEqual(sorted(pares), ["massive", "mmmlu", "sib200"])
        self.assertEqual(sorted(nm), ["paws-x", "xnli"])
        for nombre, ps in pares.items():
            self.assertEqual(len(ps), 8)
            for es, en in ps:
                # en MMMLU las descripciones son el texto de cada opción, en el idioma de la fila
                campos = ("pregunta", "opciones", "etiqueta") + (() if nombre == "mmmlu" else ("descripciones",))
                self.assertEqual([es[c] for c in campos], [en[c] for c in campos])
                self.assertNotEqual(es["texto"], en["texto"])

    def test_mmmlu_sin_pareja_en_ingles_se_mide_solo_en_espanol(self):
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as t:
            shutil.copytree(self.HF, t, dirs_exist_ok=True)
            shutil.rmtree(Path(t) / "datasets--cais--mmlu")
            pares, nm = espanol.cargar_pares(t, 8)
            self.assertNotIn("mmmlu", pares)
            self.assertIn("sin pareja en inglés", nm["mmmlu"])
            es = espanol.cargar_solo_es(t, 8, nm)
            self.assertEqual(list(es), ["mmmlu"])
            self.assertEqual(len(es["mmmlu"]), 8)
            self.assertFalse(any(k.startswith("_") for k in es["mmmlu"][0]))
            self.assertEqual(espanol.cargar_solo_es(t, 8, {}), {})   # el par salió: no hay medida solo en español

    def test_mmmlu_con_pareja_desalineada_no_empareja(self):
        import shutil, tempfile
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as t:
            shutil.copytree(self.HF, t, dirs_exist_ok=True)
            ruta = next((Path(t) / "datasets--cais--mmlu").glob("**/test-*.parquet"))
            filas = pq.read_table(ruta).to_pylist()
            for x in filas:
                x["answer"] = (x["answer"] + 1) % 4   # otra letra correcta en todas
            pq.write_table(pa.Table.from_pylist(filas), ruta)
            pares, nm = espanol.cargar_pares(t, 8)
            self.assertNotIn("mmmlu", pares)
            self.assertIn("coinciden materia y respuesta en 0 de 12", nm["mmmlu"])

    def test_bootstrap_determinista_y_signo(self):
        y = ["a", "b"] * 20
        tareas = {"t": (y, list(y), ["a"] * 40, ["a", "b"])}   # es perfecto, en solo acierta la mitad
        r1, r2 = espanol.bootstrap(tareas, 200), espanol.bootstrap(tareas, 200)
        self.assertEqual(r1, r2)
        self.assertAlmostEqual(r1["t"]["d_acc"], 0.5)
        lo, hi = r1["t"]["d_acc_ic95"]
        self.assertLessEqual(lo, 0.5)
        self.assertGreaterEqual(hi, 0.5)
        self.assertEqual(r1["__media__"]["d_acc"], r1["t"]["d_acc"])

    def test_licencia_y_plan(self):
        self.assertEqual(espanol.licencia_tarjeta(self.HF, "Davlan/sib200"), "cc-by-sa-4.0")
        self.assertEqual(espanol.licencia_tarjeta(self.HF, "mteb/amazon_massive_intent"), "apache-2.0")
        plan = espanol.plan_md({}, self.HF)
        self.assertIn("NO COMPROBADA", plan)    # ALIA etc. no están en el fixture
        self.assertIn("solo test", plan)
        self.assertIn("general.sh", plan)


def corrida(exact, p50, p99, n=1000):
    m = {"n": n, "exactitud": exact, "f1_macro": exact - 0.01, "ece": 0.03, "cobertura": 0.8, "escalado": 0.1, "errores": 0.0, "p50_ms": p50, "p99_ms": p99}
    return {"manifiesto": "x", "fuente": "m.chispa", "global": m, "conjuntos": {"a": dict(m), "b": dict(m, n=50)}}


class TestUmbrales(unittest.TestCase):
    def test_umbrales(self):
        r = umbrales_bateria.proponer_umbrales(corrida(0.90, 10.0, 30.0), corrida(0.90, 12.0, 30.0))
        u = r["umbrales"]
        self.assertEqual(u["errores"], 0.0)
        self.assertGreaterEqual(u["exactitud"], 0.015)   # Wilson con n = 1000
        self.assertLessEqual(u["exactitud"], 0.03)
        self.assertGreaterEqual(u["p50_ms"], 0.5)
        self.assertIn("b", u["por_conjunto"])            # n = 50: IC95 mucho más ancho
        self.assertGreater(u["por_conjunto"]["b"]["exactitud"], u["exactitud"])
        self.assertNotIn("estabilidad", u)

    def test_ruido_entre_corridas_manda(self):
        r = umbrales_bateria.proponer_umbrales(corrida(0.90, 10.0, 30.0, n=100000), corrida(0.94, 10.0, 30.0, n=100000))
        self.assertGreaterEqual(r["umbrales"]["exactitud"], 0.08)

    def test_manifiesto_real_no_se_cambia(self):
        ruta = RAIZ / "sdk" / "python" / "ejemplos" / "bateria.json"
        antes = ruta.read_bytes()
        man = json.loads(antes)
        umbrales_bateria.proponer_umbrales(corrida(0.9, 10.0, 30.0), corrida(0.9, 10.0, 30.0), man)
        self.assertEqual(ruta.read_bytes(), antes)


if __name__ == "__main__":
    unittest.main()
