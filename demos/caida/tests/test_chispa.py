import importlib.util
import json
import os
import sys
import tempfile
import unittest

from caida import api, evaluar, medir, panel, traza
from caida.entrenar_fewshot import comandos, esquemas, generar
from caida.motor import Juego
from caida.partida import AgenteChispa, jugar_partida
from caida.servidor_falso import ServidorFalso

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class TestPeticion(unittest.TestCase):
    def test_forma_exacta_tres_preguntas_en_una_peticion(self):
        with ServidorFalso("primera") as s:
            ag = AgenteChispa(s.url)
            j = Juego(1)
            ag.decidir(j)
            self.assertEqual(len(s.peticiones), 1, "una sola petición por turno")
            cuerpo = s.peticiones[0]
        self.assertEqual(set(cuerpo), {"state", "questions"})
        self.assertIsInstance(cuerpo["state"], str)
        qs = cuerpo["questions"]
        self.assertEqual([(q["id"], q["kind"]) for q in qs],
                         [("colocacion", "choice"), ("riesgo", "score"), ("completa", "noul")])
        self.assertEqual(qs[0]["question"], "¿Dónde coloco la pieza?")
        ops = qs[0]["options"]
        self.assertEqual([o["id"] for o in ops], ["1", "2", "3", "4", "5", "6"])
        self.assertTrue(all(set(o) == {"id", "description"} and o["description"] for o in ops))
        self.assertRegex(ops[0]["description"], r"^limpia \d+ filas?, .*deja \d+ huecos?, altura máxima \d+$")
        self.assertEqual([o["id"] for o in qs[1]["options"]], ["1", "2", "3", "4", "5"])
        self.assertNotIn("options", qs[2])
        self.assertEqual(len({q["id"] for q in qs}), 3)

    def test_las_opciones_son_las_6_mejores_del_profesor(self):
        from caida.agentes import ranking
        with ServidorFalso("primera") as s:
            j = Juego(2)
            d = AgenteChispa(s.url).decidir(j)
        r = ranking(j)
        self.assertEqual([(o["rot"], o["col"]) for o in d.opciones], [(c.rot, c.col) for c, _, _ in r[:6]])


class TestEscudo(unittest.TestCase):
    def test_escalar_siempre_escudo_100(self):
        with ServidorFalso("escalar") as s:
            r = jugar_partida(1, AgenteChispa(s.url), 25)
        ds = r["decisiones"]
        self.assertTrue(ds and all(d.escudo and d.motivo_escudo == "sin_opinion" for d in ds))
        self.assertEqual(evaluar.resumen([r])["tasa_escudo"], 1.0)

    def test_primera_coincide_con_el_profesor(self):
        with ServidorFalso("primera") as s:
            r = jugar_partida(1, AgenteChispa(s.url), 25)
        res = evaluar.resumen([r])
        self.assertEqual((res["coincidencia"], res["intervenciones_escudo"]), (1.0, 0))

    def test_sin_servidor_cuenta_error_de_red_como_escudo(self):
        d = AgenteChispa("http://127.0.0.1:9", timeout=0.5).decidir(Juego(1))
        self.assertTrue(d.escudo)
        self.assertEqual(d.motivo_escudo, "error_red")


class TestEvaluador(unittest.TestCase):
    def test_20_partidas_con_servidor_falso(self):
        with ServidorFalso("primera") as s:
            r = evaluar.evaluar(s.url, s.url, list(range(1, 21)), 40)
        self.assertEqual(set(r["agentes"]), {"aleatorio", "profesor", "chispa_zero_shot", "chispa_few_shot"})
        for a in r["agentes"].values():
            self.assertEqual(a["resumen"]["partidas"], 20)
            self.assertLessEqual(a["resumen"]["piezas_media"], 40)
            for k in ("latencia_ms_p50", "latencia_ms_p99"):
                self.assertIsNotNone(a["resumen"][k])
        self.assertEqual(r["agentes"]["chispa_zero_shot"]["resumen"]["coincidencia"], 1.0)
        self.assertGreater(r["agentes"]["profesor"]["resumen"]["piezas_media"], r["agentes"]["aleatorio"]["resumen"]["piezas_media"])
        json.dumps(r)
        self.assertIn("| chispa_few_shot |", evaluar.markdown(r))

    def test_cli_escribe_json_y_md(self):
        with ServidorFalso("escalar") as s, tempfile.TemporaryDirectory() as d:
            self.assertEqual(evaluar.main(["--url", s.url, "--salida", d, "--partidas", "2", "--max-piezas", "10"]), 0)
            self.assertTrue(os.path.exists(os.path.join(d, "evaluacion.json")))
            self.assertTrue(os.path.exists(os.path.join(d, "evaluacion.md")))
            self.assertEqual(json.load(open(os.path.join(d, "evaluacion.json")))["agentes"]["chispa_zero_shot"]["resumen"]["tasa_escudo"], 1.0)

    def test_url_muerta_sale_con_2(self):
        self.assertEqual(evaluar.main(["--url", "http://127.0.0.1:9", "--salida", tempfile.mkdtemp()]), 2)


class TestFewShot(unittest.TestCase):
    def test_formato_y_reparto(self):
        d = generar(30, semilla=5)
        self.assertEqual(set(d), {"colocacion", "riesgo", "completa"})
        for q, filas in d.items():
            self.assertEqual(len(filas), 30)
            self.assertTrue(all(set(f) == {"texto", "etiqueta"} and f["texto"] for f in filas))
        self.assertEqual({f["etiqueta"] for f in d["colocacion"]}, {"1", "2", "3", "4", "5", "6"})
        self.assertEqual({f["etiqueta"] for f in d["riesgo"]}, {"1", "2", "3", "4", "5"})
        self.assertEqual({f["etiqueta"] for f in d["completa"]}, {"false", "true"})
        self.assertEqual(generar(30, semilla=5), d, "determinista")

    def test_n_menor_que_clases_falla(self):
        with self.assertRaises(ValueError):
            generar(3)

    def test_etiqueta_completa_es_la_derivada(self):
        # una fila "true" debe corresponder a un tablero donde alguna colocación limpia fila
        d = generar(12, semilla=9)
        self.assertTrue(any(f["etiqueta"] == "true" for f in d["completa"]))

    def test_comandos_sin_conjunta_y_con_l2_torre(self):
        for c in comandos("out", "p.chispa-l1", "srv.chispa", "t.onnx"):
            self.assertIn("-m chispa train", c)
            for f in ("--ejemplos", "--esquema", "--l1 p.chispa-l1", "--l2 srv.chispa", "--torre t.onnx", "--salida"):
                self.assertIn(f, c)
            self.assertNotIn("--conjunta", c)

    @unittest.skipUnless(os.path.isdir(os.path.join(RAIZ, "sdk", "python", "chispa")), "no está sdk/python")
    def test_los_ficheros_los_acepta_el_cargador_del_sdk(self):
        sys.path.insert(0, os.path.join(RAIZ, "sdk", "python"))
        try:
            from chispa.datos import cargar_ejemplos, cargar_esquema, validar
        finally:
            sys.path.pop(0)
        datos = generar(30, semilla=5)
        with tempfile.TemporaryDirectory() as d:
            for q, esq in esquemas().items():
                ej = os.path.join(d, f"{q}.jsonl")
                with open(ej, "w", encoding="utf-8") as f:
                    f.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in datos[q]))
                es = os.path.join(d, f"{q}.json")
                json.dump(esq, open(es, "w", encoding="utf-8"), ensure_ascii=False)
                pregunta, _ = cargar_esquema(es)
                self.assertEqual(pregunta.kind, esq["tipo"])
                cuenta = validar(cargar_ejemplos(ej), pregunta)
                self.assertEqual(sum(cuenta.values()), 30)


class TestTraza(unittest.TestCase):
    def test_grabar_y_reproducir_sin_modelo(self):
        with ServidorFalso("primera") as s, tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "t.jsonl")
            r = traza.grabar(ruta, 3, s.url, 30)
            cab, turnos = traza.leer(ruta)
            self.assertEqual(cab["semilla"], 3)
            self.assertEqual(len(turnos), r["piezas"])
            t = turnos[0]
            for k in ("tablero", "pieza", "opciones", "preguntas", "elegida", "escudo", "ms_cliente", "ms_servidor", "puntos"):
                self.assertIn(k, t)
            self.assertEqual(set(t["preguntas"]), {"colocacion", "riesgo", "completa"})
            self.assertIn("probs", t["preguntas"]["colocacion"])
            self.assertEqual(len(list(traza.reproducir(ruta))), r["piezas"])  # sin servidor: motor + semilla

    def test_reproducir_detecta_traza_alterada(self):
        with ServidorFalso("primera") as s, tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "t.jsonl")
            traza.grabar(ruta, 3, s.url, 5)
            lineas = open(ruta).read().splitlines()
            m = json.loads(lineas[2])
            m["tablero"][-1] = "#########"
            lineas[2] = json.dumps(m)
            open(ruta, "w").write("\n".join(lineas) + "\n")
            with self.assertRaises(AssertionError):
                list(traza.reproducir(ruta))


class TestPanel(unittest.TestCase):
    def _turno(self, **kw):
        t = {"turno": 4, "opciones": [{"id": str(i), "descripcion": f"d{i}"} for i in range(1, 4)], "elegida": "2", "rot": 1, "col": 3,
             "preguntas": {"colocacion": {"answer": "2", "probs": {"1": 0.2, "2": 0.7, "3": 0.1}, "layer": "L2", "escalate": False},
                           "riesgo": {"answer": "3", "probs": {"1": 0.1, "2": 0.2, "3": 0.5, "4": 0.1, "5": 0.1}, "layer": "L1", "escalate": False},
                           "completa": {"answer": "true", "probs": {"false": 0.25, "true": 0.75}, "layer": "L0", "escalate": False}},
             "escudo": False, "forzada": False, "ms_cliente": 20.0, "puntos": 130, "filas_total": 1}
        t.update(kw)
        return t

    def test_calculo_del_panel(self):
        ac = panel.acumular(panel.acumular(panel.acumulado_inicial(), self._turno(ms_cliente=10.0)), self._turno(ms_cliente=30.0, escudo=True))
        p = panel.calcular_panel(self._turno(), ac)
        self.assertEqual([b["prob"] for b in p["barras"]], [0.2, 0.7, 0.1])
        self.assertEqual([b["elegida"] for b in p["barras"]], [False, True, False])
        self.assertEqual(p["riesgo"]["nivel"], 3)
        self.assertEqual([n["prob"] for n in p["riesgo"]["niveles"]][2], 0.5)
        self.assertEqual((p["completa"]["texto"], p["completa"]["p_si"]), ("sí", 0.75))
        self.assertEqual(p["capa"], "L2")
        self.assertEqual([c["id"] for c in p["capas"] if c["activa"]], ["L2"])
        self.assertEqual((p["escudo"], p["decisiones"]), (1, 2))
        self.assertAlmostEqual(p["decisiones_por_s"], 2 / 0.040)  # 2 decisiones en 40 ms
        self.assertEqual((p["puntos"], p["filas"], p["latencia_ms"]), (130, 1, 20.0))
        self.assertIn("opción 2", p["jugada"])

    def test_escalada(self):
        t = self._turno(escudo=True, elegida=None, preguntas={
            "colocacion": {"answer": "", "probs": {}, "layer": "escalar", "escalate": True},
            "riesgo": {"answer": "", "probs": {}, "layer": "escalar", "escalate": True},
            "completa": {"answer": "", "probs": {}, "layer": "escalar", "escalate": True}})
        p = panel.calcular_panel(t, panel.acumular(panel.acumulado_inicial(), t))
        self.assertEqual(p["capa"], "escalar")
        self.assertIsNone(p["riesgo"]["nivel"])
        self.assertEqual(p["completa"]["texto"], "—")
        self.assertTrue(p["jugada"].startswith("escudo"))
        self.assertTrue(all(b["prob"] == 0 for b in p["barras"]))
        self.assertEqual(p["escudo"], 1)

    def test_forzada_no_cuenta(self):
        t = self._turno(forzada=True, ms_cliente=None, preguntas={})
        ac = panel.acumular(panel.acumulado_inicial(), t)
        self.assertEqual(ac["decisiones"], 0)
        self.assertIsNone(panel.calcular_panel(t, ac)["decisiones_por_s"])

    def test_paneles_desde_traza_real(self):
        with ServidorFalso("primera") as s, tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "t.jsonl")
            traza.grabar(ruta, 1, s.url, 10)
            _, turnos = traza.leer(ruta)
        ps = panel.paneles(turnos)
        self.assertEqual(len(ps), len(turnos))
        self.assertEqual(ps[-1]["decisiones"], len(turnos))


class TestMedir(unittest.TestCase):
    def test_fria_y_caliente(self):
        with ServidorFalso("primera") as s:
            r = medir.medir(s.url, 10)
            n = len(s.peticiones)
        self.assertEqual(n, 10 + 1 + 10)
        for k in ("fria", "caliente"):
            for m in ("ms_p50", "ms_p95", "ms_p99", "decisiones_por_s"):
                self.assertIsNotNone(r[k][m])
            self.assertEqual(r[k]["errores_red"], 0)
        self.assertIn("| fria |", medir.markdown(r))

    def test_la_fria_manda_descripciones_distintas(self):
        with ServidorFalso("primera") as s:
            medir.medir(s.url, 5)
            fria = s.peticiones[:5]
        d = {o["description"] for p in fria for o in p["questions"][0]["options"]}
        self.assertEqual(len(d), 5 * 6)


@unittest.skipUnless(importlib.util.find_spec("PIL"), "sin Pillow (requirements-render.txt)")
class TestDibujo(unittest.TestCase):
    def test_fotograma_1080p(self):
        from caida import renderizar
        with ServidorFalso("primera") as s, tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "t.jsonl")
            traza.grabar(ruta, 1, s.url, 6)
            _, turnos = traza.leer(ruta)
        ims = list(renderizar.fotogramas(turnos[:2], 0.2))
        self.assertTrue(ims)
        self.assertEqual(ims[0].size, (1920, 1080))

    def test_mp4_de_punta_a_punta(self):
        from caida import renderizar
        if not renderizar.ruta_ffmpeg():
            self.skipTest("sin ffmpeg")
        with ServidorFalso("primera") as s, tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "t.jsonl")
            traza.grabar(ruta, 1, s.url, 4)
            self.assertEqual(renderizar.main(["--traza", ruta, "--salida", os.path.join(d, "v.mp4"), "--seg-por-turno", "0.3"]), 0)
            self.assertGreater(os.path.getsize(os.path.join(d, "v.mp4")), 1000)


if __name__ == "__main__":
    unittest.main()
