import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from serpiente import agentes, analisis, api, estado, evaluar, medir, renderizar, traza
from serpiente.motor import LADO, MAX_PASOS, Juego, a_texto, mover
from serpiente.partida import AgenteAleatorio, AgenteChispa, AgenteProfesor, argmax_probs, jugar_partida
from serpiente.servidor_falso import ServidorFalso

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def juego_con(cuerpo, d, comida):
    j = Juego(1)
    j.cuerpo, j.dir, j.comida = tuple(cuerpo), d, comida
    return j


class TestMotor(unittest.TestCase):
    def test_inicio(self):
        j = Juego(1)
        self.assertEqual((LADO, j.longitud, j.pasos, j.dir), (16, 3, 0, 1))
        self.assertNotIn(j.comida, j.cuerpo)

    def test_avanza_una_casilla_y_gira_relativo(self):
        j = Juego(1)
        j.comida = (0, 0)
        cab = j.cuerpo[0]
        j.paso("recto")
        self.assertEqual(j.cuerpo[0], (cab[0], cab[1] + 1))
        j.paso("izquierda")  # mirando a la derecha, izquierda = arriba
        self.assertEqual(j.cuerpo[0], (cab[0] - 1, cab[1] + 1))
        self.assertEqual(j.dir, 0)
        j.paso("derecha")
        self.assertEqual(j.dir, 1)
        self.assertEqual(j.longitud, 3)

    def test_choque_con_muro(self):
        j = juego_con([(0, 5), (1, 5), (2, 5)], 0, (9, 9))
        r = j.paso("recto")
        self.assertEqual((r.choque, j.terminado, j.motivo), ("muro", True, "muro"))
        with self.assertRaises(ValueError):
            j.paso("recto")

    def test_choque_consigo_misma(self):
        cuerpo = [(5, 5), (5, 4), (6, 4), (6, 5), (6, 6)]  # la cabeza gira hacia abajo y entra en (6,5)
        j = juego_con(cuerpo, 1, (9, 9))
        r = j.paso("derecha")
        self.assertEqual((r.choque, j.motivo), ("cuerpo", "cuerpo"))

    def test_la_cola_se_aparta(self):
        # cuadrado de 4: la cabeza puede entrar en la casilla de la cola porque esta se libera
        nuevo, come, choque = mover([(5, 5), (5, 4), (6, 4), (6, 5)], 2, (9, 9))
        self.assertEqual((choque, come), ("", False))
        self.assertEqual(nuevo[0], (6, 5))

    def test_comer_hace_crecer_y_cambia_la_comida(self):
        j = juego_con([(5, 5), (5, 4), (5, 3)], 1, (5, 6))
        r = j.paso("recto")
        self.assertTrue(r.comio)
        self.assertEqual((j.longitud, j.comidas), (4, 1))
        self.assertNotEqual(j.comida, (5, 6))
        self.assertNotIn(j.comida, j.cuerpo)

    def test_comer_la_cola_no_deja_entrar_en_ella(self):
        # si en ese paso come, la cola no se aparta: entrar en su casilla es choque
        _, _, choque = mover([(5, 5), (5, 4), (6, 4), (6, 5)], 2, (6, 5))
        self.assertEqual(choque, "cuerpo")

    def test_tope_de_pasos(self):
        j = Juego(1)
        j.comida = (0, 0)
        for _ in range(MAX_PASOS):
            if j.terminado:
                break
            j.paso(agentes.profesor(j))
            j.comida = j.comida if not j.terminado else None
        self.assertEqual((j.pasos, j.motivo), (MAX_PASOS, "tope"))

    def test_determinismo_con_semilla(self):
        a = jugar_partida(7, AgenteAleatorio(7))
        b = jugar_partida(7, AgenteAleatorio(7))
        self.assertEqual({k: v for k, v in a.items() if k != "decisiones"}, {k: v for k, v in b.items() if k != "decisiones"})
        self.assertEqual([d.giro for d in a["decisiones"]], [d.giro for d in b["decisiones"]])
        j1, j2 = Juego(3), Juego(3)
        self.assertEqual((j1.comida, a_texto(j1.cuerpo, j1.comida)), (j2.comida, a_texto(j2.cuerpo, j2.comida)))
        self.assertNotEqual([Juego(s).comida for s in range(1, 8)], [Juego(1).comida] * 7)


class TestEstado(unittest.TestCase):
    def test_texto_con_palabras(self):
        j = juego_con([(8, 8), (8, 7), (8, 6)], 1, (5, 10))  # mira a la derecha; comida 3 arriba y 2 delante
        t = estado.texto_estado(j)
        self.assertIn("La serpiente mira a la derecha", t)
        self.assertIn("La chispa queda a 2 casillas delante y 3 casillas a la izquierda (distancia 5)", t)
        self.assertIn("Casillas libres antes de chocar: izquierda 8, recto 7, derecha 7.", t)
        self.assertIn("Longitud 3", t)
        self.assertIn("Zona cerrada pequeña: izquierda no, recto no, derecha no.", t)

    def test_detras_y_derecha_y_singular(self):
        j = juego_con([(8, 8), (8, 7), (8, 6)], 1, (9, 7))  # una casilla detrás y una a la derecha (abajo)
        self.assertIn("La chispa queda a 1 casilla detrás y 1 casilla a la derecha (distancia 2)", estado.texto_estado(j))

    BOLSILLO = [(1, 1), (1, 2), (2, 2), (3, 2), (3, 1), (3, 0), (2, 0), (1, 0), (0, 0), (0, 1)]  # (2,1) es un hueco de 1 casilla

    def test_zona_cerrada_y_choque(self):
        j = juego_con(self.BOLSILLO, 3, (10, 10))  # mira a la izquierda; izquierda = abajo, entra en el hueco (2,1)
        a = analisis.analizar(j.cuerpo, j.dir, j.comida)
        self.assertEqual(a["izquierda"]["choque"], "")
        self.assertTrue(a["izquierda"]["cerrada"])
        self.assertEqual(a["recto"]["choque"], "cuerpo")
        self.assertIn("zona cerrada pequeña", estado.descripcion(a["izquierda"], j.longitud))
        self.assertIn("Zona cerrada pequeña: izquierda sí", estado.texto_estado(j))
        j2 = juego_con([(0, 5), (1, 5), (2, 5)], 0, (9, 9))
        self.assertIn("choca enseguida contra el muro", dict(estado.opciones(j2))["recto"])

    def test_opciones_fijas_en_espanol(self):
        ops = estado.opciones(Juego(1))
        self.assertEqual([i for i, _ in ops], ["izquierda", "recto", "derecha"])
        self.assertTrue(all("libres antes de chocar" in d for _, d in ops))


class TestProfesor(unittest.TestCase):
    def test_va_a_la_comida(self):
        j = juego_con([(8, 8), (8, 7), (8, 6)], 1, (8, 12))
        self.assertEqual(agentes.profesor(j), "recto")
        j = juego_con([(8, 8), (8, 7), (8, 6)], 1, (2, 8))
        self.assertEqual(agentes.profesor(j), "izquierda")

    def test_no_se_suicida_si_hay_salida(self):
        # pegado al muro de arriba mirando arriba, comida al otro lado: nunca elige la opción que choca
        j = juego_con([(0, 5), (1, 5), (2, 5)], 0, (0, 0))
        g, _ = agentes.elegir(j.cuerpo, j.dir, j.comida)
        self.assertNotEqual(g, "recto")
        for s in range(1, 6):
            r = jugar_partida(s, AgenteProfesor())
            self.assertNotIn(r["fin"], ("muro", "cuerpo"), f"semilla {s}")

    def test_rechaza_la_ruta_corta_que_encierra(self):
        j = juego_con(TestEstado.BOLSILLO, 3, (2, 1))  # la comida está en el hueco: comerla encierra a la serpiente
        a = analisis.analizar(j.cuerpo, j.dir, j.comida)
        self.assertEqual(a["izquierda"]["dist_comida"], 0)  # la opción más corta come...
        g, razon = agentes.elegir(j.cuerpo, j.dir, j.comida)
        self.assertEqual(g, "derecha")  # ...pero el profesor la descarta (y recto choca)
        self.assertFalse(a[g]["cerrada"])

    def test_sin_camino_elige_el_mayor_espacio(self):
        j = juego_con([(8, 8), (8, 7), (8, 6), (8, 5)], 1, (8, 7))  # comida dentro del cuerpo: inalcanzable
        g, razon = agentes.elegir(j.cuerpo, j.dir, j.comida)
        a = analisis.analizar(j.cuerpo, j.dir, j.comida)
        self.assertEqual(razon, "espacio")
        self.assertEqual(a[g]["area"], max(x["area"] for x in a.values() if not x["choque"]))

    def test_todas_chocan(self):
        j = juego_con([(0, 0), (1, 0), (1, 1)], 3, (9, 9))  # esquina; izquierda=abajo choca con (1,0), recto muro, derecha muro
        self.assertEqual(agentes.elegir(j.cuerpo, j.dir, j.comida)[1], "sin_salida")


class TestCliente(unittest.TestCase):
    def test_forma_de_la_peticion(self):
        with ServidorFalso("primera") as s:
            ag = AgenteChispa(s.url)
            ag.decidir(Juego(1))
            self.assertEqual(len(s.peticiones), 1)
            c = s.peticiones[0]
        self.assertEqual(set(c), {"state", "questions"})
        q = c["questions"][0]
        self.assertEqual((q["id"], q["kind"], q["question"]), ("giro", "choice", api.PREGUNTA_GIRO))
        self.assertEqual([o["id"] for o in q["options"]], ["izquierda", "recto", "derecha"])
        self.assertTrue(all(set(o) == {"id", "description"} and o["description"] for o in q["options"]))
        self.assertEqual(c["state"], estado.texto_estado(Juego(1)))

    def test_decidir_tau_con_opinion(self):
        with ServidorFalso("recto") as s:
            d = AgenteChispa(s.url).decidir(Juego(1))
        self.assertEqual((d.giro, d.decidio, d.opino, d.escudo), ("recto", "chispa_tau", True, False))
        self.assertAlmostEqual(d.confianza, 0.7)

    def test_decidir_tau_escala_es_escudo(self):
        with ServidorFalso("escalar_probs") as s:
            d = AgenteChispa(s.url, decidir="tau").decidir(Juego(1))
        self.assertEqual((d.decidio, d.escudo, d.motivo_escudo, d.giro), ("escudo", True, "bajo_tau", agentes.profesor(Juego(1))))

    def test_decidir_argmax_usa_probs_aunque_escale(self):
        with ServidorFalso("escalar_probs") as s:
            d = AgenteChispa(s.url, decidir="argmax").decidir(Juego(1))
        self.assertEqual((d.decidio, d.escudo, d.giro), ("chispa_bajo_tau", False, "izquierda"))

    def test_decidir_argmax_sin_probs_es_escudo(self):
        with ServidorFalso("escalar") as s:
            d = AgenteChispa(s.url, decidir="argmax").decidir(Juego(1))
        self.assertEqual((d.decidio, d.escudo), ("escudo", True))

    def test_error_de_red_es_escudo(self):
        d = AgenteChispa("http://127.0.0.1:9", timeout=0.5).decidir(Juego(1))
        self.assertEqual((d.decidio, d.motivo_escudo, d.giro), ("escudo", "error_red", agentes.profesor(Juego(1))))

    def test_decidir_invalido(self):
        with self.assertRaises(ValueError):
            AgenteChispa("http://x", decidir="otro")

    def test_forzada_no_pregunta(self):
        j = juego_con([(0, 0), (1, 0), (1, 1)], 3, (9, 9))
        with ServidorFalso("primera") as s:
            d = AgenteChispa(s.url).decidir(j)
            self.assertEqual(len(s.peticiones), 0)
        self.assertTrue(d.forzada)

    def test_argmax_probs(self):
        ids = ["izquierda", "recto", "derecha"]
        self.assertEqual(argmax_probs({"izquierda": 0.1, "recto": 0.6, "derecha": 0.3}, ids), "recto")
        self.assertIsNone(argmax_probs({"recto": 1.0}, ids))
        self.assertIsNone(argmax_probs({}, ids))
        self.assertIsNone(argmax_probs({"izquierda": float("nan"), "recto": 1, "derecha": 0}, ids))


class TestEvaluar(unittest.TestCase):
    def test_evaluar_con_servidor_falso(self):
        with ServidorFalso("escalar_probs") as s, tempfile.TemporaryDirectory() as d:
            r = evaluar.evaluar(s.url, [1, 2], decidir="argmax")
            self.assertEqual(set(r["agentes"]), {"aleatorio", "profesor", "chispa_zero_shot"})
            ch = r["agentes"]["chispa_zero_shot"]["resumen"]
            self.assertEqual(ch["escudo_pct"], 0.0)
            self.assertGreater(ch["bajo_tau_pct"], 99.0)  # argmax: todo se juega bajo τ
            for k in ("pasos_media", "pasos_mediana", "comida_media", "comida_mediana", "coincidencia_pct", "latencia_ms_p50", "latencia_ms_p99"):
                self.assertIsNotNone(ch[k], k)
            pr = r["agentes"]["profesor"]["resumen"]
            self.assertEqual((pr["coincidencia_pct"], pr["pasos_mediana"]), (100.0, 500))
            rc = evaluar.main(["--url", s.url, "--salida", d, "--partidas", "2", "--decidir", "tau"])
            self.assertEqual(rc, 0)
            with open(os.path.join(d, "evaluacion.json"), encoding="utf-8") as f:
                j = json.load(f)
            self.assertEqual(j["semillas"], [1, 2])
            self.assertEqual(j["agentes"]["chispa_zero_shot"]["resumen"]["escudo_pct"], 100.0)  # tau + escalar: todo escudo
            with open(os.path.join(d, "evaluacion.md"), encoding="utf-8") as f:
                self.assertIn("| chispa_zero_shot |", f.read())

    def test_evaluar_por_defecto_20_partidas(self):
        with mock.patch.object(evaluar, "evaluar", return_value={"semillas": [], "agentes": {}}) as m, \
                mock.patch.object(evaluar, "markdown", return_value=""), mock.patch.object(evaluar.api, "salud"), \
                mock.patch.object(evaluar, "escribir_json"), tempfile.TemporaryDirectory() as d:
            evaluar.main(["--url", "http://x", "--salida", d])
        self.assertEqual(m.call_args[0][1], list(range(1, 21)))

    def test_coincidencia_cuenta_solo_donde_chispa_decide(self):
        with ServidorFalso("escalar") as s:  # todo escudo: no hay decisiones de Chispa que comparar
            r = evaluar.evaluar(s.url, [1], agentes=["chispa_zero_shot"])
        ch = r["agentes"]["chispa_zero_shot"]["resumen"]
        self.assertEqual((ch["escudo_pct"], ch["decisiones_chispa"], ch["coincidencia_pct"]), (100.0, 0, None))


class TestTrazaYMedir(unittest.TestCase):
    def test_traza_se_reproduce(self):
        with ServidorFalso("aleatorio") as s, tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "t.jsonl")
            r = traza.grabar(ruta, 5, s.url)
            pasos = list(traza.reproducir(ruta))
            self.assertEqual(len(pasos), r["pasos"])
            self.assertEqual(pasos[-1]["fin"], r["fin"])
            cab, ts = traza.leer(ruta)
            self.assertEqual(cab["semilla"], 5)
            self.assertIn(ts[0]["decidio"], ("chispa_tau", None))

    def test_jugar_main_y_servidor_caido(self):
        with ServidorFalso("recto") as s, tempfile.TemporaryDirectory() as d:
            self.assertEqual(traza.main(["--url", s.url, "--salida", os.path.join(d, "t.jsonl"), "--semilla", "2"]), 0)
        self.assertEqual(traza.main(["--url", "http://127.0.0.1:9", "--salida", "/tmp/no.jsonl"]), 2)

    def test_medir(self):
        with ServidorFalso("primera") as s:
            r = medir.medir(s.url, n=5)
        self.assertEqual((r["fria"]["ok"], r["caliente"]["ok"]), (5, 5))
        self.assertIsNotNone(r["fria"]["ms_p99"])
        self.assertIn("fria", medir.markdown(r))


class TestRender(unittest.TestCase):
    def test_plan_dura_entre_20_y_40_s(self):
        for n in (1, 5, 40, 100, 250, 385, 500, 2000):
            m, f, remate = renderizar.plan(n)
            seg = (m * f + remate) / renderizar.FPS
            self.assertTrue(20.0 <= seg <= 40.0, f"n={n}: {seg} s")
            self.assertLessEqual(m, n)
            self.assertGreaterEqual(f, 3)

    def _traza(self, d):
        with ServidorFalso("aleatorio") as s:
            ruta = os.path.join(d, "t.jsonl")
            traza.grabar(ruta, 3, s.url)
        return traza.leer(ruta)[1]

    def test_fotogramas_con_pil_simulado(self):
        """Sin Pillow: se ejecuta el dibujo con un PIL de mentira y se cuentan los fotogramas."""
        fake = mock.MagicMock()
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(sys.modules, {"PIL": fake, "PIL.Image": fake.Image,
                                                                              "PIL.ImageDraw": fake.ImageDraw,
                                                                              "PIL.ImageFont": fake.ImageFont}):
            pasos = self._traza(d)
            n = sum(1 for _ in renderizar.fotogramas(pasos))
        m, f, remate = renderizar.plan(len(pasos))
        self.assertEqual(n, m * f + remate)

    @unittest.skipUnless(renderizar.hay_pillow(), "sin Pillow")
    def test_fotograma_real(self):
        with tempfile.TemporaryDirectory() as d:
            t = self._traza(d)[0]
            im = renderizar.dibujar_fotograma(t, [tuple(c) for c in t["cuerpo"]], tuple(t["comida"]), t["dir"], False)
        self.assertEqual(im.size, (1920, 1080))

    def test_main_sin_pillow_sale_con_3(self):
        with mock.patch.object(renderizar, "hay_pillow", return_value=False):
            self.assertEqual(renderizar.main(["--traza", "x", "--salida", "y.mp4"]), 3)


class TestCorrerSh(unittest.TestCase):
    def test_argumentos_invalidos(self):
        p = subprocess.run(["bash", os.path.join(AQUI, "correr.sh"), "--decidir", "otro"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 64)


if __name__ == "__main__":
    unittest.main()
