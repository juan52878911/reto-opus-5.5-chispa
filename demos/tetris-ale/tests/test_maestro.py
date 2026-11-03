import random
import unittest

from tetris_ale import maestro as M
from tetris_ale.motor import ALTO, TABLERO_VACIO, Juego, colocaciones, tablero_desde_texto, aplicar
from tetris_ale.partida import AgenteAleatorio, AgenteMaestro, jugar_partida

SEMILLAS = range(1, 21)


class TestMaestro(unittest.TestCase):
    def test_limpiar_una_linea_gana(self):
        t = tablero_desde_texto(["#########."])
        c = M.maestro(t, colocaciones(t, "I"), M.PESOS_EL_TETRIS)  # El-Tetris premia la línea sin dudar
        self.assertEqual((c.giro, c.col), (1, 9))
        # Dellacherie no es voraz: aquí valora más dejar la I plana (−17 frente a −17,5)
        self.assertEqual(M.ranking(t, colocaciones(t, "I"))[0][2], -17.0)

    def test_desempate_determinista(self):
        # tablero vacío: la O tiene 9 sitios; los pesos no distinguen simetrías, gana la menor (giro, columna) entre las de mayor valor
        a = M.maestro(TABLERO_VACIO, colocaciones(TABLERO_VACIO, "O"))
        b = M.maestro(TABLERO_VACIO, list(reversed(colocaciones(TABLERO_VACIO, "O"))))
        self.assertEqual((a.giro, a.col), (b.giro, b.col))

    def test_veto_descarta_lo_que_termina_la_partida(self):
        t = tablero_desde_texto(["#........."] * (ALTO - 2))
        cols = colocaciones(t, "O")
        self.assertTrue(any(aplicar(t, c).terminado for c in cols))
        self.assertFalse(any(e[1]["terminado"] for e in M.ranking(t, cols)))
        self.assertNotEqual(M.maestro(t, cols).col, 0)

    def test_veto_sin_alternativa_mantiene_todas(self):
        t = tablero_desde_texto(["#########." if i % 2 else "##########" for i in range(0)] or ["#........."] * (ALTO - 2))
        solo_malas = [c for c in colocaciones(t, "O") if aplicar(t, c).terminado]
        self.assertEqual(len(M.ranking(t, solo_malas)), len(solo_malas))

    def test_el_veto_alcanza_al_aleatorio(self):
        t = tablero_desde_texto(["#........."] * (ALTO - 2))
        j = Juego(1, t)
        j.pieza = "O"
        for s in range(30):
            ag = AgenteAleatorio(s)
            self.assertFalse(aplicar(t, ag.decidir(j).col).terminado)

    def test_pesos_citados(self):
        self.assertEqual(M.PESOS_DELLACHERIE["huecos"], -4.0)
        self.assertAlmostEqual(M.PESOS_EL_TETRIS["huecos"], -7.899265427351652)

    def test_hipotesis_maestro_supera_50_lineas_y_el_aleatorio_menos_de_2(self):
        # 20 semillas fijas, tope de 500 piezas. Si el maestro no llega a 50, hay un bug en los rasgos o los pesos.
        for nombre, ag in (("dellacherie", lambda s: AgenteMaestro()), ("el-tetris", lambda s: AgenteMaestro("e", M.PESOS_EL_TETRIS))):
            media = sum(jugar_partida(s, ag(s), 120)["lineas"] for s in SEMILLAS) / 20
            self.assertGreaterEqual(media, 40, nombre)  # 120 piezas ⇒ ≤ 48 líneas posibles; la prueba larga está en resultados-sim.md
        alea = sum(jugar_partida(s, AgenteAleatorio(s), 500)["lineas"] for s in SEMILLAS) / 20
        self.assertLess(alea, 2)


if __name__ == "__main__":
    unittest.main()
