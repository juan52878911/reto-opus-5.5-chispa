import unittest

from model.bench.torre import paridad_servidor as P
from model.l2 import exportar as E


def filas():
    ops = {"choice": ["a", "b"], "noul": ["false", "true"], "score2": ["1", "2"], "score3": ["1", "2", "3"],
           "score4": ["1", "2", "3", "4"], "score5": ["1", "2", "3", "4", "5"]}
    return [{"id": "x:%s" % k, "tipo": "score" if k.startswith("score") else k, "opciones": o} for k, o in ops.items()]


class CalibCompleta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modelo = E.modelo_aleatorio()
        cls.esperado = P.calib_del_checkpoint(cls.modelo, filas())

    def test_trae_todas_las_cabezas_y_coincide_con_el_checkpoint(self):
        r = E.calib_completa(self.modelo, {"tipos": {}, "tau_escalate": 0.6})
        self.assertEqual(set(r["tipos"]), set(self.esperado))
        for clave in ("choice", "noul", "score2", "score5", "score5#1", "score5#3"):
            self.assertIn(clave, r["tipos"])
        for clave, esp in self.esperado.items():
            for campo, v in esp.items():
                self.assertAlmostEqual(r["tipos"][clave][campo], v, delta=1e-6, msg=clave + "." + campo)
        self.assertEqual(r["tau_escalate"], 0.6)

    def test_cabeza_presente_no_se_toca(self):
        propia = {"T": 3.0, "a": 7.0, "b": -2.0, "theta": 0.9}
        r = E.calib_completa(self.modelo, {"tipos": {"choice": propia}, "tau_escalate": 0.6})
        self.assertEqual(r["tipos"]["choice"], propia)
        self.assertEqual(set(r["tipos"]), set(self.esperado))


if __name__ == "__main__":
    unittest.main()
