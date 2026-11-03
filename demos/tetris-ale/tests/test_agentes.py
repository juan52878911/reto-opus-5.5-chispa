import json
import os
import tempfile
import unittest

from tetris_ale import evaluar as E
from tetris_ale.motor import Juego
from tetris_ale.partida import AgenteChispa, AgenteMaestro, jugar_partida
from tetris_ale.servidor_falso import ServidorFalso


def juega(url, modo="tau", semilla=1, piezas=60):
    return jugar_partida(semilla, AgenteChispa(url, decidir=modo), piezas)


class TestAgentes(unittest.TestCase):
    def test_peticion_con_una_sola_pregunta_choice(self):
        with ServidorFalso("primera") as s:
            juega(s.url, piezas=5)
            self.assertEqual(len(s.peticiones), 5)
            for p in s.peticiones:
                self.assertEqual(len(p["questions"]), 1)
                q = p["questions"][0]
                self.assertEqual(q["kind"], "choice")
                self.assertTrue(p["state"].startswith("Pieza "))
                self.assertTrue(all("limpia" in o["description"] for o in q["options"]))

    def test_si_chispa_opina_se_juega_su_opcion(self):
        with ServidorFalso("primera") as s:
            p = juega(s.url)
        ds = [d for d in p["decisiones"] if not d.forzada]
        self.assertTrue(all(d.decidio == "chispa_tau" and not d.escudo for d in ds))
        self.assertTrue(all(d.id_elegida == "1" for d in ds))
        # la «1» es una opción barajada, no la del maestro: la coincidencia es de azar
        self.assertLess(sum(d.coincide for d in ds) / len(ds), 0.8)

    def test_escalar_juega_el_maestro_y_cuenta_escudo(self):
        with ServidorFalso("escalar") as s:
            p = juega(s.url)
        m = jugar_partida(1, AgenteMaestro(), 60)
        self.assertEqual((p["lineas"], p["piezas"]), (m["lineas"], m["piezas"]))
        ds = [d for d in p["decisiones"] if not d.forzada]
        self.assertTrue(all(d.escudo and d.decidio == "escudo" for d in ds))

    def test_argmax_juega_las_probs_aunque_escale(self):
        with ServidorFalso("escalar_probs") as s:
            tau, argmax = juega(s.url, "tau"), juega(s.url, "argmax")
        self.assertTrue(all(d.escudo for d in tau["decisiones"] if not d.forzada))
        ds = [d for d in argmax["decisiones"] if not d.forzada]
        self.assertTrue(all(d.decidio == "chispa_bajo_tau" and not d.escudo for d in ds))

    def test_red_caida_juega_el_maestro(self):
        with ServidorFalso("primera") as s:
            url = s.url
        p = jugar_partida(1, AgenteChispa(url, timeout=0.5), 20)
        ds = [d for d in p["decisiones"] if not d.forzada]
        self.assertTrue(all(d.escudo and d.motivo_escudo == "error_red" for d in ds))
        self.assertEqual(p["lineas"], jugar_partida(1, AgenteMaestro(), 20)["lineas"])

    def test_chispa_que_lee_los_rasgos_se_acerca_al_maestro(self):
        # el servidor falso «rasgos» solo ve las descripciones: si el texto lleva la señal, coincide mucho más que el azar (1/7)
        with ServidorFalso("rasgos") as s:
            p = juega(s.url, piezas=100)
        ds = [d for d in p["decisiones"] if not d.forzada]
        self.assertGreater(sum(d.coincide for d in ds) / len(ds), 0.5)

    def test_decidir_invalido(self):
        with self.assertRaises(ValueError):
            AgenteChispa("http://x", decidir="otro")


class TestEvaluar(unittest.TestCase):
    def test_evaluar_con_servidor_falso(self):
        with ServidorFalso("rasgos") as s:
            r = E.evaluar([1, 2], 40, url=s.url)
        self.assertEqual(list(r["agentes"]), ["aleatorio", "maestro", "el-tetris", "chispa"])
        res = {n: a["resumen"] for n, a in r["agentes"].items()}
        self.assertEqual(res["maestro"]["coincidencia"], 1.0)
        self.assertGreater(res["maestro"]["lineas_media"], res["aleatorio"]["lineas_media"])
        self.assertIsNotNone(res["chispa"]["latencia_ms_p99"])
        md = E.markdown(r)
        self.assertIn("| chispa |", md)
        self.assertIn("líneas/partida", md)
        json.dumps(r)

    def test_porcentaje_bajo_tau(self):
        with ServidorFalso("escalar") as s:
            r = E.evaluar([1], 30, url=s.url, agentes=["chispa"])
        self.assertEqual(r["agentes"]["chispa"]["resumen"]["pct_bajo_tau"], 100.0)

    def test_cli_escribe_json_y_markdown(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(E.main(["--salida", d, "--partidas", "2", "--max-piezas", "30"]), 0)
            self.assertTrue(os.path.exists(os.path.join(d, "evaluacion.json")))
            self.assertTrue(os.path.exists(os.path.join(d, "evaluacion.md")))

    def test_cli_sin_servidor_falla_claro(self):
        with ServidorFalso() as s:
            url = s.url
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(E.main(["--url", url, "--salida", d]), 2)


if __name__ == "__main__":
    unittest.main()
