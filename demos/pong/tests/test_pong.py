import random
import unittest

from pong import opciones as O
from pong.motor import ALTO, RADIO, X_PALA, Estado, Juego, corte, reflejar
from pong.partida import AgenteOptimo, Partida


class Motor(unittest.TestCase):
    def test_reflejar(self):
        self.assertEqual(reflejar(100), 100)
        self.assertAlmostEqual(reflejar(RADIO - 10), RADIO + 10)
        self.assertAlmostEqual(reflejar(ALTO - RADIO + 10), ALTO - RADIO - 10)

    def test_corte_con_rebote_coincide_con_la_simulacion(self):
        j = Juego(3)
        e = j.e
        e.bx, e.by, e.vx, e.vy = 320, 100, 6, -5
        y, tics = corte(e, "derecha")
        j.e.palas["derecha"] = 9999  # que no la toque: se mide dónde cruza
        for _ in range(int(tics)):
            j.paso()
        self.assertLess(abs(j.e.by + j.e.vy * (tics - int(tics)) - y), 1e-6 + abs(j.e.vy))
        self.assertIsNone(corte(Estado(vx=-5), "derecha"))

    def test_optimo_contra_optimo_rebota(self):
        p = Partida(Juego(1), {"izquierda": AgenteOptimo(), "derecha": AgenteOptimo()}, 1)
        p.jugar(ritmo=20)  # 20× más rápido que el tiempo real
        r = p.resumen()
        self.assertGreater(sum(r["golpes"].values()), 10)
        self.assertEqual(r["agentes"]["derecha"]["coincide_optima_pct"], 100.0)


class Opciones(unittest.TestCase):
    def test_tres_opciones_barajadas_y_optima(self):
        e = Estado(bx=320, by=240, vx=6, vy=0)
        e.palas["derecha"] = 100
        estado, ops = O.construir(e, "derecha", random.Random(1))
        self.assertEqual(sorted(o.nombre for o in ops), ["bajar", "quieta", "subir"])
        self.assertEqual(O.optima(ops).nombre, "bajar")
        self.assertIn("punto de corte a 240 px", estado)
        self.assertTrue(all(o.descripcion.startswith(o.nombre + ": la pala queda a ") for o in ops))

    def test_mismo_texto_para_los_dos(self):
        e = Estado(vx=6)
        estado, ops = O.construir(e, "derecha", random.Random(2))
        c, l = O.peticion_chispa(estado, ops), O.peticion_laya(estado, ops)
        self.assertEqual(c["state"], l["state"])
        self.assertEqual({o["id"]: o["description"] for o in c["questions"][0]["options"]}, l["criteria"])


if __name__ == "__main__":
    unittest.main()
