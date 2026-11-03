"""Percepción por RAM y conversión simulador ↔ controlador, sin emulador (RAM sintética)."""
import unittest

from tetris_ale import ale
from tetris_ale.ale_juego import BYTE_FILA, GIROS, TIPO_DE_FORMA, Lectura, celdas, normalizar, tablero_ram
from tetris_ale.motor import ALTO, colocaciones, tablero_desde_texto


def ram_con(celdas_on, fila=10):
    ram = [0] * 128
    for r, c in celdas_on:
        if c < 6:
            ram[21 - r] |= 1 << (5 - c)
        else:
            ram[43 - r] |= 1 << (c - 6)
    ram[BYTE_FILA] = fila
    return ram


class RAM(unittest.TestCase):
    def test_mapa_de_bits_ida_y_vuelta(self):
        cs = {(0, 0), (0, 5), (0, 6), (0, 9), (21, 3), (21, 7), (10, 4)}
        self.assertEqual(celdas(tablero_ram(ram_con(cs))), frozenset(cs))

    def test_pieza_es_tablero_menos_asentado(self):
        asentado = frozenset({(21, c) for c in range(9)})
        t = asentado | {(3, 4), (3, 5), (3, 6), (4, 5)}
        le = Lectura(ram_con(t), asentado)
        self.assertEqual(TIPO_DE_FORMA[le.forma], "T")
        self.assertEqual(le.columna, 4)

    def test_diecinueve_orientaciones(self):
        self.assertEqual(sum(len(v) for v in GIROS.values()), 19)
        self.assertEqual(len(TIPO_DE_FORMA), 19)


class Conversion(unittest.TestCase):
    def test_tablero_sim_invierte_filas(self):
        t = ale.tablero_sim({(ALTO - 1, 0), (ALTO - 1, 9), (ALTO - 2, 1)})
        self.assertEqual(t, tablero_desde_texto([".#........", "#........#"]))

    def test_objetivo_cubre_todas_las_colocaciones(self):
        # cada colocación del simulador da una forma que el controlador reconoce y la columna mínima de sus celdas
        t = tablero_desde_texto(["###.......", "####...###"])
        for tipo in "OISZTLJ":
            for c in colocaciones(t, tipo):
                forma, col = ale.objetivo(c)
                self.assertEqual(TIPO_DE_FORMA[forma], tipo)
                self.assertEqual(col, min(cc for _, cc in c.celdas))
                self.assertEqual(forma, normalizar([(ALTO - 1 - f, cc) for f, cc in c.celdas]))


if __name__ == "__main__":
    unittest.main()
