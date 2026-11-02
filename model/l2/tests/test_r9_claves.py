import json
import unittest
from pathlib import Path

import numpy as np
import torch

from model.l2 import exportar as E
from model.l2.modelo import ModeloL2, texto_opcion
from model.l2.tests import gen_r9 as G
from model.l2.tests.test_t24_exportar import CodificadorDiminuto


class R9(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(1)
        cls.modelo, cls.enc = ModeloL2().eval(), CodificadorDiminuto()
        cls.fs = G.filas()

    def vec_de(self, fila, opcion):
        with torch.no_grad():
            h = self.modelo.torre(self.enc.pasaje([texto_opcion(fila, opcion)]))[0].numpy()
        return E.cuantizar_vec(h)

    def test_noul_usa_la_torre_de_true_en_cualquier_orden(self):
        torres = E.entradas_torres(self.modelo, self.enc, self.fs[:2])
        self.assertEqual(len(torres), 2)
        for r, (p, kind, ops, q, esc) in zip(self.fs[:2], torres):
            self.assertEqual(E.opcion_consulta(r), "true")
            self.assertEqual(E.texto_torre_consulta(r), texto_opcion(r, "true"))
            self.assertEqual(E.hash_clave(p, kind, ops), E.hash_clave(*E.clave_torre(r)))
            self.assertEqual((kind, ops), ("noul", (("false", G.DESC["false"]), ("true", G.DESC["true"]))))
            qt, et = self.vec_de(r, "true")
            np.testing.assert_array_equal(q, qt)
            self.assertEqual(esc, et)
            qf, _ = self.vec_de(r, "false")
            self.assertFalse(np.array_equal(q, qf))

    def test_noul_sin_true_falla(self):
        with self.assertRaises(ValueError):
            E.opcion_consulta({"tipo": "noul", "pregunta": "q", "opciones": ["a", "b"]})

    def test_score_es_el_nivel_maximo(self):
        self.assertEqual(E.opcion_consulta({"tipo": "score", "opciones": ["5", "4", "3", "2", "1", "6", "7", "8", "9", "10"]}), "10")
        with self.assertRaises(ValueError):
            E.opcion_consulta({"tipo": "score", "opciones": ["1", "2", "10"]})
        self.assertEqual(E.opcion_consulta({"tipo": "score", "opciones": ["3", "1", "2"]}), "3")

    def test_multi_una_entrada_por_opcion(self):
        r = self.fs[2]
        torres = E.entradas_torres(self.modelo, self.enc, [r])
        self.assertEqual(len(torres), 3)
        for o, (p, kind, ops, q, esc) in zip(r["opciones"], torres):
            self.assertEqual((p, kind, ops), (r["pregunta"], "multi", ((o, r["descripciones"].get(o, "")),)))
            np.testing.assert_array_equal(q, self.vec_de(r, o)[0])

    def test_fixture_r9_al_dia(self):
        esp = json.loads((G.FIX / "esquemas-r9.json").read_text(encoding="utf-8"))
        self.comparar(esp, G.generar())

    def comparar(self, esp, obt, ruta="$"):
        """Estructura y textos exactos; los floats con tolerancia relativa 1e-5: salen de la red con pesos aleatorios (semilla fija) y
        su último dígito depende de la CPU (FMA/AVX, hilos de BLAS). El test Go lee la fixture tal cual, así que no hace falta regenerarla."""
        if isinstance(esp, dict):
            self.assertEqual(sorted(esp), sorted(obt), ruta)
            for k in esp:
                self.comparar(esp[k], obt[k], f"{ruta}.{k}")
        elif isinstance(esp, list):
            self.assertEqual(len(esp), len(obt), ruta)
            for i, (a, b) in enumerate(zip(esp, obt)):
                self.comparar(a, b, f"{ruta}[{i}]")
        elif isinstance(esp, float):
            self.assertAlmostEqual(esp, obt, delta=1e-5 * max(1.0, abs(esp)), msg=ruta)
        else:
            self.assertEqual(esp, obt, ruta)


if __name__ == "__main__":
    unittest.main()
