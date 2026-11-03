import random
import unittest

from tetris_ale import maestro as M, opciones as O
from tetris_ale.motor import TABLERO_VACIO, colocaciones, tablero_desde_texto


class TestOpciones(unittest.TestCase):
    def test_descripcion_ejemplo(self):
        r = {"lineas": 1, "delta_huecos": 0, "altura_max": 7, "irregularidad": 4, "pozos": 2, "altura_aterrizaje": 3}
        self.assertEqual(O.descripcion(r), "limpia 1 línea, huecos +0, altura 7, irregularidad 4, pozos 2, aterriza a 3")
        r.update(lineas=0, delta_huecos=-2, altura_aterrizaje=2.5)
        self.assertEqual(O.descripcion(r), "no limpia líneas, huecos -2, altura 7, irregularidad 4, pozos 2, aterriza a 2,5")
        r.update(lineas=3)
        self.assertTrue(O.descripcion(r).startswith("limpia 3 líneas"))

    def test_estado_breve(self):
        t = tablero_desde_texto(["#.........", ".#........"])
        self.assertEqual(O.texto_estado(t, "T", "L"), "Pieza T, siguiente L. Tablero: altura 2, huecos 1.")
        self.assertEqual(O.texto_estado(t, "T"), "Pieza T. Tablero: altura 2, huecos 1.")

    def test_cinco_mejores_y_dos_al_azar(self):
        cols = colocaciones(TABLERO_VACIO, "T")
        rank = M.ranking(TABLERO_VACIO, cols)
        ops = O.construir(TABLERO_VACIO, cols, random.Random(1))
        self.assertEqual(sorted(o.id for o in ops), [str(i) for i in range(1, 8)])
        self.assertEqual(sorted(o.puesto for o in ops if o.puesto <= 5), [1, 2, 3, 4, 5])
        self.assertEqual(len([o for o in ops if o.puesto > 5]), 2)
        self.assertEqual(len({(o.col.giro, o.col.col) for o in ops}), 7)
        mejor = next(o for o in ops if o.puesto == 1)
        self.assertEqual((mejor.col.giro, mejor.col.col), (rank[0][0].giro, rank[0][0].col))

    def test_barajadas_y_deterministas_por_semilla(self):
        cols = colocaciones(TABLERO_VACIO, "T")
        orden = lambda s: [o.puesto for o in O.construir(TABLERO_VACIO, cols, random.Random(s))]
        self.assertEqual(orden(5), orden(5))
        self.assertGreater(len({tuple(orden(s)) for s in range(10)}), 1)
        self.assertGreater(len({orden(s).index(1) for s in range(40)}), 3)  # la del maestro no está siempre en la misma posición

    def test_pocas_colocaciones_se_ofrecen_todas(self):
        cols = colocaciones(TABLERO_VACIO, "O")[:4]
        self.assertEqual(len(O.construir(TABLERO_VACIO, cols, random.Random(0))), 4)

    def test_las_descripciones_llevan_los_rasgos(self):
        t = tablero_desde_texto(["#########."])
        ops = O.construir(t, colocaciones(t, "I"), random.Random(2), azar=12)  # sin recortar: la I tiene 17 colocaciones
        for o in ops:
            self.assertEqual(o.descripcion, O.descripcion(o.rasgos))
        vertical = next(o for o in ops if (o.col.giro, o.col.col) == (1, 9))
        self.assertTrue(vertical.descripcion.startswith("limpia 1 línea, huecos +0, altura 3"))
        cuerpo = O.peticion("estado", ops)
        q = cuerpo["questions"][0]
        self.assertEqual((q["kind"], len(cuerpo["questions"])), ("choice", 1))
        self.assertEqual([o["id"] for o in q["options"]], [o.id for o in ops])


if __name__ == "__main__":
    unittest.main()
