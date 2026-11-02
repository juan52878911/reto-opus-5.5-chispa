import random
import unittest

from caida import motor
from caida.agentes import aleatorio, profesor
from caida.motor import ALTO, ANCHO, CHISPA, NORMAL, Colocacion, Juego, aplicar, colocaciones, rotaciones, tablero_vacio


def partida(semilla, n=60):
    j, rng, jugadas = Juego(semilla), random.Random(semilla), []
    while not j.terminado and j.piezas_colocadas < n:
        c = aleatorio(j, rng)
        jugadas.append((j.pieza.nombre, c.rot, c.col, c.fila))
        j.jugar(c)
    return jugadas, j.puntos, j.filas_limpiadas


class TestMotor(unittest.TestCase):
    def test_tablero_9x15(self):
        self.assertEqual((ANCHO, ALTO), (9, 15))
        self.assertEqual(len(tablero_vacio()), 15)
        self.assertEqual(len(tablero_vacio()[0]), 9)

    def test_determinismo_por_semilla(self):
        self.assertEqual(partida(7), partida(7))
        self.assertNotEqual(partida(7), partida(8))

    def test_secuencia_de_piezas_no_depende_del_agente(self):
        a, b = Juego(3), Juego(3)
        sa, sb = [], []
        for _ in range(10):
            sa.append(a.pieza)
            a.jugar(colocaciones(a.tablero, a.pieza)[0])
            sb.append(b.pieza)
            b.jugar(colocaciones(b.tablero, b.pieza)[-1])
        self.assertEqual(sa, sb)

    def test_ninguna_pieza_clasica(self):
        # Las formas clásicas de 4 celdas son todas las unidas por lados: aquí las de 4 celdas no lo están.
        for nombre, celdas in motor.PIEZAS.items():
            self.assertTrue(2 <= len(celdas) <= 4, nombre)
            for rot in rotaciones(tuple((r, c, 1) for r, c in celdas)):
                if len(rot) == 4:
                    cs = {(r, c) for r, c, _ in rot}
                    vistos, pila = set(), [next(iter(cs))]
                    while pila:
                        r, c = pila.pop()
                        if (r, c) in vistos:
                            continue
                        vistos.add((r, c))
                        pila += [x for x in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)) if x in cs]
                    self.assertLess(len(vistos), 4, f"{nombre} sería una forma clásica")

    def test_colocaciones_dentro_y_caida_instantanea(self):
        t = tablero_vacio()
        p = motor.Pieza("domino", ((0, 0, 1), (0, 1, 1)))
        cs = colocaciones(t, p)
        horiz = [c for c in cs if c.rot == 0]
        self.assertEqual(len(horiz), ANCHO - 1)
        self.assertTrue(all(c.fila == ALTO - 1 for c in horiz))
        vert = [c for c in cs if c.rot == 1]
        self.assertEqual(len(vert), ANCHO)
        self.assertTrue(all(c.fila == ALTO - 2 for c in vert))

    def _fila_casi_llena(self, chispa_en=None):
        t = tablero_vacio()
        for c in range(ANCHO - 1):
            t[ALTO - 1][c] = CHISPA if c == chispa_en else NORMAL
        return t

    def test_limpieza_de_fila_sin_chispa(self):
        t = self._fila_casi_llena()
        t[ALTO - 2][0] = NORMAL  # algo encima: debe bajar una fila
        col = Colocacion(0, ANCHO - 1, ALTO - 1, ((ALTO - 1, ANCHO - 1, NORMAL),))
        ef = aplicar(t, col)
        self.assertEqual((ef.filas, ef.columnas), (1, ()))
        self.assertEqual(ef.tablero[ALTO - 1][0], NORMAL)  # la celda de encima bajó
        self.assertEqual(sum(x != 0 for f in ef.tablero for x in f), 1)

    def test_regla_de_chispa_borra_la_columna(self):
        t = self._fila_casi_llena(chispa_en=2)
        for r in range(3, ALTO - 1):
            t[r][2] = NORMAL          # columna 2 llena de bloques por encima de la fila
        t[5][5] = NORMAL              # un bloque ajeno que debe sobrevivir y bajar
        col = Colocacion(0, ANCHO - 1, ALTO - 1, ((ALTO - 1, ANCHO - 1, NORMAL),))
        ef = aplicar(t, col)
        self.assertEqual(ef.filas, 1)
        self.assertEqual(ef.columnas, (2,))
        self.assertTrue(all(ef.tablero[r][2] == 0 for r in range(ALTO)), "la columna 2 debe quedar vacía")
        self.assertEqual(ef.celdas_columna, ALTO - 1 - 3)
        self.assertEqual(ef.tablero[6][5], NORMAL)  # gravedad: el bloque de la fila 5 bajó 1 (una fila borrada debajo)
        self.assertEqual(ef.tablero[5][5], 0)

    def test_chispa_fuera_de_fila_llena_no_borra(self):
        t = tablero_vacio()
        t[10][4] = CHISPA
        col = Colocacion(0, 0, ALTO - 1, ((ALTO - 1, 0, NORMAL),))
        ef = aplicar(t, col)
        self.assertEqual((ef.filas, ef.columnas), (0, ()))
        self.assertEqual(ef.tablero[10][4], CHISPA)

    def test_game_over(self):
        j = Juego(1)
        for r in range(ALTO):
            for c in range(ANCHO):
                j.tablero[r][c] = NORMAL if c != 0 or r > 5 else 0
        j.tablero[0][0] = NORMAL
        j._siguiente()
        self.assertTrue(j.terminado)
        self.assertEqual(j.colocaciones(), [])

    def test_profesor_gana_al_aleatorio_en_20_semillas(self):
        prof = alea = 0
        for s in range(1, 21):
            j = Juego(s)
            while not j.terminado and j.piezas_colocadas < 150:
                j.jugar(profesor(j))
            prof += j.piezas_colocadas
            j = Juego(s)
            rng = random.Random(s)
            while not j.terminado and j.piezas_colocadas < 150:
                j.jugar(aleatorio(j, rng))
            alea += j.piezas_colocadas
        self.assertGreater(prof, 3 * alea)


if __name__ == "__main__":
    unittest.main()
