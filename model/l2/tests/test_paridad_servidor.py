import unittest

import numpy as np

from model.bench.torre import paridad_servidor as P
from model.l2.modelo import texto_consulta, texto_opcion


def fila(tipo, ops, desc):
    return {"id": "x:1", "tipo": tipo, "pregunta": "¿Qué?", "texto": "hola", "opciones": ops, "descripciones": desc, "etiqueta": ops[0]}


class Paridad(unittest.TestCase):
    def test_choice_igual_que_python(self):
        f = fila("choice", ["a", "b"], {"a": "uno", "b": "dos"})
        self.assertEqual(P.textos_servidor(f), P.textos_python(f))
        self.assertEqual(P.textos_servidor(f)[0], texto_opcion(f, "a"))

    def test_noul_y_score_sin_descripcion_en_la_peticion(self):
        # la petición de /v1/decide no lleva descripción de «true» ni de los niveles: si la fila de Python la tiene, los textos difieren
        n = fila("noul", ["false", "true"], {"true": "se cumple"})
        self.assertNotEqual(P.textos_servidor(n), [texto_consulta(n)])
        self.assertEqual(P.textos_servidor(n), ["passage: ¿Qué? · true · "])
        n0 = fila("noul", ["false", "true"], {})
        self.assertEqual(P.textos_servidor(n0), [texto_consulta(n0)])
        s = fila("score", ["1", "2", "3"], {})
        self.assertEqual(P.textos_servidor(s), [texto_consulta(s)])
        self.assertTrue(P.textos_servidor(s)[0].endswith(" · 3 · "))

    def test_cuantizar_go(self):
        q, e = P.cuantizar_go(np.array([0.5, -1.0, 0.0]))
        self.assertEqual(q.tolist(), [64.0, -127.0, 0.0])   # 63,5 → 64: las mitades se redondean hacia fuera de cero
        self.assertAlmostEqual(e, 1 / 127)
        self.assertEqual(P.cuantizar_go(np.zeros(3))[1], 1.0)

    def test_probs_calib(self):
        p = P.probs_calib("choice", 2, [0.5, 0.3], {"choice": {"T": 0.1}})
        self.assertAlmostEqual(float(p.sum()), 1.0)
        self.assertGreater(p[0], p[1])
        pn = P.probs_calib("noul", 2, [0.0], {"noul": {"a": 4.0, "b": -4.0}})
        self.assertAlmostEqual(float(pn[1]), 1 / (1 + np.exp(4)), places=6)
        ps = P.probs_calib("score", 3, [1.0], {"score3": {"a": 2.0, "b": 1.0}, "score3#1": {"a": 0.5}})
        self.assertAlmostEqual(float(ps.sum()), 1.0)

    def test_probs_calib_score_sin_calib(self):
        # CALIB de `chispa train`: solo choice/noul; el servidor no tiene valores por defecto para score (L2.score escala) → None
        self.assertIsNone(P.probs_calib("score", 4, [0.3], {"choice": {"T": 0.1}}))
        self.assertIsNone(P.probs_calib("score", 5, [0.3], {"score4": {"a": 2.0, "b": 1.0}}))
        self.assertIsNone(P.probs_calib("score", 3, [0.3], {"score3": {"a": 2.0, "b": 1.0}}))   # falta score3#1
        self.assertAlmostEqual(float(P.probs_calib("noul", 2, [0.3], {}).sum()), 1.0)   # noul y choice sí tienen defecto
        self.assertAlmostEqual(float(P.probs_calib("choice", 3, [0.3, 0.2, 0.1], {}).sum()), 1.0)

    def test_resumen_cuenta_causas(self):
        base = {"consulta": {"truncado_python": False, "truncado_servidor": True}, "torre": [{"igual": True}], "replay_fiel": 0.0, "delta_p_max": 0.2}
        fs = [{**base, "tipo": "choice", "elegida": {}, "causa": "calib"}, {**base, "tipo": "choice", "elegida": {}, "causa": None},
              {**base, "tipo": "noul", "causa": "escalado"}]
        r = P.resumen(fs)
        self.assertEqual(r["choice"]["causas"], {"calib": 1})
        self.assertEqual((r["todos"]["casos"], r["todos"]["escalados"], r["todos"]["discrepan"]), (3, 1, 1))


if __name__ == "__main__":
    unittest.main()
