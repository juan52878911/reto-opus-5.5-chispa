import unittest

from tetris_ale.motor import TABLERO_VACIO, colocaciones, tablero_desde_texto
from tetris_ale.rasgos import (alturas, contar_huecos, irregularidad, pozos, rasgos, transiciones_columna,
                               transiciones_fila)


def col(t, pieza, giro, c):
    return [x for x in colocaciones(t, pieza) if x.giro == giro and x.col == c][0]


class TestRasgos(unittest.TestCase):
    def test_alturas(self):
        t = tablero_desde_texto(["..#.......", "#.#......#"])
        self.assertEqual(alturas(t), [1, 0, 2, 0, 0, 0, 0, 0, 0, 1])
        self.assertEqual(alturas(TABLERO_VACIO), [0] * 10)

    def test_huecos(self):
        self.assertEqual(contar_huecos(tablero_desde_texto(["#.........", ".#........"])), 1)
        # dos celdas vacías bajo la misma columna cuentan las dos; un voladizo sin nada encima no cuenta
        self.assertEqual(contar_huecos(tablero_desde_texto(["#.........", "..........", ".........."])), 2)
        self.assertEqual(contar_huecos(tablero_desde_texto(["#.#.......", "#........."])), 1)  # bajo la columna 2
        self.assertEqual(contar_huecos(tablero_desde_texto(["#.........", "#........."])), 0)

    def test_transiciones_fila(self):
        # |1 # . # . . . . . . . 1|: 1→0, 0→1, 1→0, 0→1(pared) = 4
        self.assertEqual(transiciones_fila(tablero_desde_texto(["#.#......."])), 4)
        self.assertEqual(transiciones_fila(TABLERO_VACIO), 0)  # las filas vacías sobre la torre no cuentan
        self.assertEqual(transiciones_fila(tablero_desde_texto(["##########"])), 0)
        self.assertEqual(transiciones_fila(tablero_desde_texto(["#.........", "#........."])), 4)  # 2 por fila

    def test_transiciones_columna(self):
        self.assertEqual(transiciones_columna(TABLERO_VACIO), 10)  # suelo lleno → vacío en cada columna
        self.assertEqual(transiciones_columna(tablero_desde_texto(["#........."])), 10)
        # columna 0: lleno, vacío, lleno, vacío (techo) = 3 en vez de 1
        self.assertEqual(transiciones_columna(tablero_desde_texto(["#.........", "..........", "#........."])), 12)

    def test_pozos(self):
        t = tablero_desde_texto(["#.#.......", "#.#.......", "#.#......."])
        self.assertEqual(pozos(t), 6)  # columna 1: profundidad 3 → 1+2+3; las demás no tienen pared alta a ambos lados
        # una columna en la pared izquierda cuenta con la pared como alta
        self.assertEqual(pozos(tablero_desde_texto([".#........", ".#........"])), 3)

    def test_irregularidad(self):
        t = tablero_desde_texto(["#.#.......", "#.#.......", "#.#......."])
        self.assertEqual(irregularidad(alturas(t)), 9)

    def test_altura_aterrizaje(self):
        self.assertEqual(rasgos(TABLERO_VACIO, col(TABLERO_VACIO, "I", 0, 0))["altura_aterrizaje"], 1)
        self.assertEqual(rasgos(TABLERO_VACIO, col(TABLERO_VACIO, "I", 1, 0))["altura_aterrizaje"], 2.5)

    def test_rasgos_de_una_colocacion(self):
        t = tablero_desde_texto(["#########."])
        r = rasgos(t, col(t, "I", 1, 9))
        self.assertEqual((r["lineas"], r["celdas_erosionadas"]), (1, 1))
        self.assertEqual((r["huecos"], r["delta_huecos"], r["altura_max"], r["altura_total"]), (0, 0, 3, 3))
        self.assertEqual(r["irregularidad"], 3)
        self.assertEqual(r["pozos"], 0)  # la columna 8 está a ras de la 7: no es un pozo

    def test_delta_huecos(self):
        t = tablero_desde_texto([".........." , "#........."])
        r = rasgos(t, col(t, "I", 0, 0))  # la I horizontal apoyada en la columna 0
        self.assertEqual((r["delta_huecos"], r["huecos"]), (3, 3))  # tapa las columnas 1-3 vacías de la fila 0


if __name__ == "__main__":
    unittest.main()
