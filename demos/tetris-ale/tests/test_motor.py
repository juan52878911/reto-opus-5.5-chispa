import unittest

from tetris_ale.motor import (ALTO, ANCHO, GIROS, PIEZAS, TABLERO_VACIO, Juego, aplicar, colocaciones,
                              tablero_desde_texto)


class TestMotor(unittest.TestCase):
    def test_giros_distintos(self):
        self.assertEqual({p: len(GIROS[p]) for p in PIEZAS}, {"O": 1, "I": 2, "S": 2, "Z": 2, "T": 4, "L": 4, "J": 4})
        for p in PIEZAS:
            for forma in GIROS[p]:
                self.assertEqual(len(forma), 4)

    def test_numero_de_colocaciones_en_tablero_vacio(self):
        n = {p: len(colocaciones(TABLERO_VACIO, p)) for p in PIEZAS}
        self.assertEqual(n, {"O": 9, "I": 17, "S": 17, "Z": 17, "T": 34, "L": 34, "J": 34})

    def test_caida_directa(self):
        c = [c for c in colocaciones(TABLERO_VACIO, "I") if c.giro == 0 and c.col == 3][0]
        self.assertEqual(sorted(c.celdas), [(0, 3), (0, 4), (0, 5), (0, 6)])
        t = tablero_desde_texto(["..#.......", "..#......."])
        o = [c for c in colocaciones(t, "O") if c.col == 1][0]  # el O en columnas 1-2 se apoya en la columna 2 (altura 2)
        self.assertEqual(sorted(o.celdas), [(2, 1), (2, 2), (3, 1), (3, 2)])

    def test_la_caida_no_atraviesa_huecos(self):
        # el hueco bajo el saliente no se rellena: la pieza no puede entrar de lado
        t = tablero_desde_texto(["#####.....", ".........."])
        i = [c for c in colocaciones(t, "I") if c.giro == 0 and c.col == 0][0]
        self.assertEqual({f for f, _ in i.celdas}, {2})

    def test_columna_llena_no_admite_pieza_vertical(self):
        t = tuple(1 for _ in range(ALTO))  # columna 0 llena hasta arriba
        self.assertFalse([c for c in colocaciones(t, "I") if c.giro == 1 and c.col == 0])
        self.assertTrue([c for c in colocaciones(t, "I") if c.giro == 1 and c.col == 1])

    def test_aplicar_una_linea(self):
        t = tablero_desde_texto(["#########."])
        c = [c for c in colocaciones(t, "I") if c.giro == 1 and c.col == 9][0]
        ef = aplicar(t, c)
        self.assertEqual((ef.lineas, ef.celdas_erosionadas, ef.terminado), (1, 1, False))
        self.assertEqual(ef.tablero[:4], (1 << 9, 1 << 9, 1 << 9, 0))
        self.assertEqual(t, tablero_desde_texto(["#########."]))  # no muta

    def test_aplicar_dos_lineas(self):
        t = tablero_desde_texto(["########..", "########.."])
        c = [c for c in colocaciones(t, "O") if c.col == 8][0]
        ef = aplicar(t, c)
        self.assertEqual((ef.lineas, ef.celdas_erosionadas), (2, 8))
        self.assertEqual(ef.tablero, TABLERO_VACIO)

    def test_game_over(self):
        t = tablero_desde_texto(["#........."] * (ALTO - 2))
        sobre = [c for c in colocaciones(t, "O") if c.col == 0][0]
        self.assertTrue(aplicar(t, sobre).terminado)
        suelo = [c for c in colocaciones(t, "O") if c.col == 5][0]
        self.assertFalse(aplicar(t, suelo).terminado)

    def test_secuencia_determinista_por_semilla(self):
        def seq(s):
            j, out = Juego(s), []
            for _ in range(30):
                out.append(j.pieza)
                j.jugar(j.colocaciones()[0] if not j.terminado else None) if not j.terminado else None
            return out
        self.assertEqual(seq(7), seq(7))
        self.assertNotEqual(seq(7), seq(8))
        j = Juego(3)
        p, s = j.pieza, j.siguiente
        j.jugar(j.colocaciones()[0])
        self.assertEqual(j.pieza, s)
        self.assertEqual(j.piezas_colocadas, 1)
        self.assertEqual(ANCHO, 10)


if __name__ == "__main__":
    unittest.main()
