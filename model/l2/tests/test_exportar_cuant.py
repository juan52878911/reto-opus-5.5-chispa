import tempfile
import unittest
from pathlib import Path

import onnx
import torch

from model.l2 import exportar as E
from model.l2.modelo import ModeloL2
from model.l2.tests.test_t24_exportar import CodificadorDiminuto, encoder_diminuto, filas_prueba


def cuantizados(ruta, prefijo):
    m = onnx.load(str(ruta), load_external_data=False)
    return [n.name for n in m.graph.node if n.name.startswith(prefijo) and n.op_type in ("MatMulInteger", "DynamicQuantizeLinear")]


class Cuantizacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(1)
        cls.dir = tempfile.TemporaryDirectory()
        cls.d = Path(cls.dir.name)
        E.exportar_onnx(E.Envoltura(encoder_diminuto(), ModeloL2().ranuras), cls.d / "fp32.onnx", 1000)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def cuant(self, modo, pc):
        sal = self.d / ("%s-%s.onnx" % (modo, pc))
        E.cuantizar(self.d / "fp32.onnx", sal, modo, pc)
        return sal

    def test_todo_cuantiza_las_ranuras(self):
        self.assertTrue(cuantizados(self.cuant("todo", False), E.PREFIJO_RANURAS))

    def test_codificador_deja_las_ranuras_en_fp32(self):
        for pc in (False, True):
            sal = self.cuant("codificador", pc)
            self.assertEqual(cuantizados(sal, E.PREFIJO_RANURAS), [])
            self.assertTrue(cuantizados(sal, "/encoder/"))
            self.assertLess(sal.stat().st_size, (self.d / "fp32.onnx").stat().st_size)

    def test_ninguna_copia_el_fp32(self):
        self.assertEqual(self.cuant("ninguna", False).read_bytes(), (self.d / "fp32.onnx").read_bytes())

    def test_modo_desconocido(self):
        with self.assertRaises(ValueError):
            E.cuantizar(self.d / "fp32.onnx", self.d / "x.onnx", "mitad")

    def test_fraccion_de_tokens_podados(self):
        enc, filas = CodificadorDiminuto(), filas_prueba()
        todo = {"original": 1000, "ids_originales": list(range(1000)), "unk": 3}
        self.assertEqual(E.fraccion_unk(enc, filas, todo), 0.0)
        nada = {"original": 1000, "ids_originales": [3], "unk": 3}
        self.assertGreater(E.fraccion_unk(enc, filas, nada), 0.5)

    def test_umbral_de_paridad(self):
        inf = {"cuant": "todo", "paridad": {"acuerdo_top1": 0.80, "dif_media": 0.004, "dif_max": 0.34}}
        with self.assertRaisesRegex(RuntimeError, "acuerdo top-1 0.800 < 0.950"):
            E.comprobar_paridad(inf, E.MIN_TOP1)
        E.comprobar_paridad(inf, 0.7)
        E.comprobar_paridad({}, E.MIN_TOP1)  # sin paridad medida no hay qué comprobar


if __name__ == "__main__":
    unittest.main()
