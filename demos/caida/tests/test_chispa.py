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
    def test_forma_exacta_dos_peticiones_por_turno(self):
        with ServidorFalso("primera") as s:
            ag = AgenteChispa(s.url)
            ag.preparar(1)
            ag.decidir(Juego(1))
            self.assertEqual(len(s.peticiones), 2, "choice, y score + noul")
            ch, resto = s.peticiones
        for c in (ch, resto):
            self.assertEqual(set(c), {"state", "questions"})
            self.assertIsInstance(c["state"], str)
        self.assertEqual([(q["id"], q["kind"]) for q in ch["questions"]], [("colocacion", "choice")])
        self.assertEqual([(q["id"], q["kind"]) for q in resto["questions"]], [("riesgo", "score"), ("completa", "noul")])
        q0 = ch["questions"][0]
        self.assertEqual(q0["question"], "¿Dónde coloco la pieza?")
        ops = q0["options"]
        self.assertEqual([o["id"] for o in ops], ["1", "2", "3", "4", "5", "6"])
        self.assertTrue(all(set(o) == {"id", "description"} and o["description"] for o in ops))
        self.assertRegex(ops[0]["description"], r"^limpia \d+ filas?, .*deja \d+ huecos?, altura máxima \d+$")
        self.assertEqual([o["id"] for o in resto["questions"][0]["options"]], ["1", "2", "3", "4", "5"])
        self.assertNotIn("options", resto["questions"][1])

    def test_el_estado_de_riesgo_y_completa_no_lleva_las_opciones(self):
        with ServidorFalso("primera") as s:
            AgenteChispa(s.url).decidir(Juego(1))
            ch, resto = s.peticiones
        self.assertIn("Opciones:", ch["state"])
        self.assertNotIn("Opciones:", resto["state"])
        self.assertTrue(ch["state"].startswith(resto["state"]), "el del choice es el del resto más la lista de opciones")
        self.assertIn("Pieza:", resto["state"])

    def test_las_opciones_son_las_6_mejores_del_profesor_barajadas(self):
        from caida.agentes import ranking
        with ServidorFalso("primera") as s:
            j = Juego(2)
            ag = AgenteChispa(s.url)
            ag.preparar(2)
            d = ag.decidir(j)
        r = ranking(j)
        for o in d.opciones:  # el mapeo a la colocación real está en cada opción
            c = r[o["rank"] - 1][0]
            self.assertEqual((o["rot"], o["col"]), (c.rot, c.col))
        self.assertEqual(sorted(o["rank"] for o in d.opciones), [1, 2, 3, 4, 5, 6])
        self.assertNotEqual([o["rank"] for o in d.opciones], [1, 2, 3, 4, 5, 6], "con la semilla 2 el orden no es el del profesor")

    def test_el_barajado_depende_de_la_semilla_de_la_partida(self):
        def ordenes(sem):
            with ServidorFalso("escalar") as s:
                r = jugar_partida(sem, AgenteChispa(s.url), 6)
            return [[o["rank"] for o in d.opciones] for d in r["decisiones"] if not d.forzada]
        self.assertEqual(ordenes(4), ordenes(4))
        self.assertNotEqual(ordenes(4), ordenes(5))


class TestEstadoUnico(unittest.TestCase):
    def test_entrenamiento_e_inferencia_usan_la_misma_funcion(self):
        """Cada ejemplo de entrenamiento coincide con el `state` que `peticiones_turno` manda para esa misma pregunta."""
        from unittest import mock
        from caida import entrenar_fewshot, estado
        vistos = []
        real = estado.texto_pregunta

        def espia(q, j, ops):
            t = real(q, j, ops)
            bodies = estado.peticiones_turno(j, ops)  # el juego aún no ha avanzado: es la petición de ESE turno
            vistos.append((q, t, next(b["state"] for b in bodies if q in [x["id"] for x in b["questions"]])))
            return t

        with mock.patch.object(entrenar_fewshot, "texto_pregunta", espia):
            generar(12, semilla=9)
        self.assertGreater(len(vistos), 30)
        for q, t, enviado in vistos:
            self.assertEqual(t, enviado, q)
            self.assertEqual("Opciones:" in t, q == "colocacion", q)

    def test_ejemplos_de_riesgo_y_completa_sin_lista_de_opciones(self):
        d = generar(12, semilla=9)
        for q in ("riesgo", "completa"):
            self.assertTrue(all("Opciones:" not in f["texto"] and "Pieza:" in f["texto"] for f in d[q]), q)
        self.assertTrue(all("Opciones:" in f["texto"] for f in d["colocacion"]))


class TestEscudo(unittest.TestCase):
    def test_escalar_siempre_escudo_100(self):
        with ServidorFalso("escalar") as s:
            r = jugar_partida(1, AgenteChispa(s.url), 25)
        ds = r["decisiones"]
        self.assertTrue(ds and all(d.escudo and d.motivo_escudo == "sin_opinion" for d in ds))
        self.assertEqual(evaluar.resumen([r])["tasa_escudo"], 1.0)

    def test_siempre_la_1_baja_al_azar_entre_6_al_barajar(self):
        """Con las opciones barajadas, «siempre la 1» ya no es la del profesor: coincide como un azar entre 6."""
        with ServidorFalso("primera") as s:
            ps = [jugar_partida(sem, AgenteChispa(s.url), 40) for sem in range(1, 21)]
        res = evaluar.resumen(ps)
        self.assertEqual(res["intervenciones_escudo"], 0)
        self.assertEqual(res["n_chispa_tau"], res["decisiones"])
        self.assertTrue(0.10 < res["coincidencia"] < 0.24, res["coincidencia"])

    def test_sin_barajar_la_1_es_la_del_profesor(self):
        with ServidorFalso("primera") as s:
            r = jugar_partida(1, AgenteChispa(s.url, barajar=False), 25)
        res = evaluar.resumen([r])
        self.assertEqual((res["coincidencia"], res["intervenciones_escudo"]), (1.0, 0))

    def test_tau_por_defecto_con_probs_y_escalada_es_escudo(self):
        with ServidorFalso("escalar_probs") as s:
            r = jugar_partida(1, AgenteChispa(s.url), 25)
        self.assertTrue(all(d.decidio == "escudo" for d in r["decisiones"]))
        self.assertEqual(evaluar.resumen([r])["tasa_escudo"], 1.0)

    def test_argmax_juega_el_argmax_aunque_escale(self):
        with ServidorFalso("escalar_probs") as s:
            r = jugar_partida(1, AgenteChispa(s.url, decidir="argmax", barajar=False), 25)
        ds = r["decisiones"]
        self.assertTrue(ds and all(d.decidio == "chispa_bajo_tau" and not d.escudo and d.id_elegida == "1" for d in ds))
        res = evaluar.resumen([r])
        self.assertEqual((res["n_chispa_bajo_tau"], res["n_chispa_tau"], res["n_escudo"]), (len(ds), 0, 0))
        self.assertEqual(res["coincidencia_chispa_bajo_tau"], 1.0)

    def test_argmax_sin_probs_juega_el_profesor_y_cuenta_escudo(self):
        with ServidorFalso("escalar") as s:
            r = jugar_partida(1, AgenteChispa(s.url, decidir="argmax"), 25)
        res = evaluar.resumen([r])
        self.assertTrue(all(d.decidio == "escudo" for d in r["decisiones"]))
        self.assertEqual((res["n_escudo"], res["n_chispa_bajo_tau"], res["coincidencia_escudo"]), (len(r["decisiones"]), 0, 1.0))

    def test_argmax_ciego_coincide_como_azar(self):
        with ServidorFalso("escalar_probs_ciego") as s:
            ps = [jugar_partida(sem, AgenteChispa(s.url, decidir="argmax"), 40) for sem in range(1, 21)]
        res = evaluar.resumen(ps)
        self.assertEqual(res["n_chispa_bajo_tau"], res["decisiones"])
        self.assertTrue(0.10 < res["coincidencia_chispa_bajo_tau"] < 0.24, res["coincidencia_chispa_bajo_tau"])

    def test_probs_invalidas(self):
        from caida.partida import argmax_probs
        ids = ["1", "2", "3"]
        self.assertEqual(argmax_probs({"1": 0.1, "2": 0.6, "3": 0.3}, ids), "2")
        self.assertEqual(argmax_probs({"1": 0.5, "2": 0.5, "3": 0.0}, ids), "1")
        for malas in (None, {}, [], {"1": 1.0}, {"1": "x", "2": 1, "3": 0}, {"1": float("nan"), "2": 1, "3": 0},
                      {"1": -1, "2": 1, "3": 0}, {"1": 0, "2": 0, "3": 0}, {"1": True, "2": 0, "3": 0}):
            self.assertIsNone(argmax_probs(malas, ids), malas)

    def test_decidir_invalido(self):
        with self.assertRaises(ValueError):
            AgenteChispa("http://x", decidir="otro")

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
        self.assertLess(r["agentes"]["chispa_zero_shot"]["resumen"]["coincidencia"], 0.5)  # opciones barajadas
        self.assertGreater(r["agentes"]["profesor"]["resumen"]["piezas_media"], r["agentes"]["aleatorio"]["resumen"]["piezas_media"])
        json.dumps(r)
        self.assertIn("| chispa_few_shot |", evaluar.markdown(r))

    def test_cli_escribe_json_y_md(self):
        with ServidorFalso("escalar") as s, tempfile.TemporaryDirectory() as d:
            self.assertEqual(evaluar.main(["--url", s.url, "--salida", d, "--partidas", "2", "--max-piezas", "10"]), 0)
            self.assertTrue(os.path.exists(os.path.join(d, "evaluacion.json")))
            self.assertTrue(os.path.exists(os.path.join(d, "evaluacion.md")))
            self.assertEqual(json.load(open(os.path.join(d, "evaluacion.json")))["agentes"]["chispa_zero_shot"]["resumen"]["tasa_escudo"], 1.0)

    def test_cli_argmax_separa_las_tres_cifras(self):
        with ServidorFalso("escalar_probs") as s, tempfile.TemporaryDirectory() as d:
            self.assertEqual(evaluar.main(["--url", s.url, "--salida", d, "--partidas", "2", "--max-piezas", "10", "--decidir", "argmax"]), 0)
            r = json.load(open(os.path.join(d, "evaluacion.json")))
            md = open(os.path.join(d, "evaluacion.md")).read()
        self.assertEqual(r["decidir"], "argmax")
        z = r["agentes"]["chispa_zero_shot"]["resumen"]
        self.assertEqual((z["n_escudo"], z["n_chispa_tau"]), (0, 0))
        self.assertGreater(z["n_chispa_bajo_tau"], 0)
        self.assertIn("bajo_tau", md)
        self.assertIn("`argmax`", md)

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

    def test_traza_argmax_guarda_decidio_modo_y_mapeo(self):
        with ServidorFalso("escalar_probs") as s, tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "t.jsonl")
            traza.grabar(ruta, 3, s.url, 12, decidir="argmax")
            cab, turnos = traza.leer(ruta)
            self.assertEqual(cab["decidir"], "argmax")
            self.assertTrue(all(t["decidio"] == "chispa_bajo_tau" and not t["escudo"] for t in turnos))
            self.assertTrue(all(sorted(o["rank"] for o in t["opciones"]) == [1, 2, 3, 4, 5, 6] for t in turnos))
            ps = panel.paneles(turnos, cab["decidir"])
            self.assertTrue(all(p["etiqueta_bajo_tau"] == "bajo τ: el servidor escalaría" and p["modo"] == "argmax" for p in ps))
            self.assertEqual(ps[-1]["bajo_tau"], len(turnos))
            self.assertEqual(ps[-1]["escudo"], 0)
            self.assertEqual(len(list(traza.reproducir(ruta))), len(turnos))

    def test_traza_tau_marca_chispa_tau_y_escudo(self):
        with ServidorFalso("primera") as s, ServidorFalso("escalar") as e, tempfile.TemporaryDirectory() as d:
            traza.grabar(os.path.join(d, "a"), 3, s.url, 8)
            traza.grabar(os.path.join(d, "b"), 3, e.url, 8)
            cab, a = traza.leer(os.path.join(d, "a"))
            _, b = traza.leer(os.path.join(d, "b"))
        self.assertEqual(cab["decidir"], "tau")
        self.assertTrue(all(t["decidio"] == "chispa_tau" for t in a))
        self.assertTrue(all(t["decidio"] == "escudo" for t in b))
        self.assertTrue(all(p["etiqueta_bajo_tau"] is None and p["modo"] == "tau" for p in panel.paneles(a)))

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
        self.assertEqual(n, 2 * (10 + 1 + 10), "dos peticiones por decisión")
        for k in ("fria", "caliente"):
            for m in ("ms_p50", "ms_p95", "ms_p99", "decisiones_por_s"):
                self.assertIsNotNone(r[k][m])
            self.assertEqual(r[k]["errores_red"], 0)
        self.assertIn("| fria |", medir.markdown(r))

    def test_la_fria_manda_descripciones_distintas(self):
        with ServidorFalso("primera") as s:
            medir.medir(s.url, 5)
            fria = s.peticiones[:10][0::2]  # las del choice de 5 decisiones
        d = {o["description"] for p in fria for o in p["questions"][0]["options"]}
        self.assertEqual(len(d), 5 * 6)


class TestCorrerSh(unittest.TestCase):
    def test_correr_con_decidir_argmax_termina_con_0(self):
        import subprocess
        sh = os.path.join(RAIZ, "demos", "caida", "correr.sh")
        with ServidorFalso("escalar_probs") as s, tempfile.TemporaryDirectory() as d:
            p = subprocess.run(["bash", sh, "--url", s.url, "--salida", d, "--decidir", "argmax", "--partidas", "2",
                                "--max-piezas", "8", "--n-medir", "3"], capture_output=True, text=True, timeout=300)
            self.assertEqual(p.returncode, 0, p.stdout[-1500:] + p.stderr[-1500:])
            ev = json.load(open(os.path.join(d, "evaluacion.json")))
            cab, _ = traza.leer(os.path.join(d, "traza.jsonl"))
            self.assertEqual(json.load(open(os.path.join(d, "latencia.json")))["decidir"], "argmax")
        self.assertEqual((ev["decidir"], cab["decidir"]), ("argmax", "argmax"))

    def test_decidir_invalido_falla(self):
        import subprocess
        sh = os.path.join(RAIZ, "demos", "caida", "correr.sh")
        p = subprocess.run(["bash", sh, "--url", "http://127.0.0.1:9", "--salida", tempfile.mkdtemp(), "--decidir", "otro"],
                           capture_output=True, text=True, timeout=60)
        self.assertNotEqual(p.returncode, 0)


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
