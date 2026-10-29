import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from model.l2 import datos as D
from model.l2 import entrenar
from model.l2.tests.falso import CodificadorFalso, fila


def con_id(prefijo, i, tarea, split="train", **kw):
    r = fila(i, tarea=tarea, **kw)
    r["id"] = "%s:%s:%d" % (prefijo, split, i)
    r["split"] = split
    return r


class Excluir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        # massive y clinc150 comparten `tarea`: se agrupan por el prefijo del id, no por la tarea
        self.locales = [con_id("massive", i, "intencion") for i in range(6)] + [con_id("clinc150", i, "intencion") for i in range(6)] \
            + [con_id("deepset", i, "inyeccion", k=None) for i in range(4)] + [con_id("hatecheck", i, "odio") for i in range(4)] \
            + [con_id("massive", 50 + i, "intencion", split="dev") for i in range(3)] + [con_id("otra", i, "otra") for i in range(3)]
        with open(d / "d.jsonl", "w", encoding="utf-8") as f:
            for r in self.locales:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        self.ruta = str(d / "d.jsonl")
        self.meta = [con_id("tsjev", i, "otra") for i in range(3)] + [con_id("sintetica", i, "massive") for i in range(3)]

    def tearDown(self):
        self.tmp.cleanup()

    def args(self, excluir):
        return Namespace(datos=[self.ruta], herramientas=False, meta="m", max_filas=1000, semilla=0, episodios=True, blandas=[],
                         maestro_extra=[], excluir_tareas=excluir)

    def preparar(self, excluir):
        with mock.patch.object(D, "submuestrear_meta", lambda *a, **k: (list(self.meta), {}, {})):
            return entrenar.preparar_filas(self.args(excluir))

    def test_sin_excluir_no_quita_nada(self):
        filas, _, meta = self.preparar([])
        self.assertEqual(len(filas), 23)
        self.assertEqual(len(meta), 6)

    def test_no_queda_ninguna_fila_excluida(self):
        excl = ["massive", "hatecheck", "inyecciones"]
        filas, info, meta = self.preparar(excl)
        self.assertEqual({D.conjunto(r) for r in filas}, {"clinc150", "otra"})  # clinc150 conserva la misma `tarea` que massive
        self.assertEqual(len(filas), 9)
        self.assertFalse([r for r in filas + meta if D.conjunto(r) in excl])
        self.assertEqual(info["excluir"]["sin_filas_locales"], [])

    def test_agrupa_por_conjunto_no_por_tarea(self):
        # una fila de meta con tarea "massive" pero otro conjunto sí se excluye si se pide por su conjunto
        filas, _, meta = self.preparar(["massive"])
        self.assertTrue(any(r["id"].startswith("clinc150") for r in filas))
        self.assertEqual(len(meta), 3)  # sintetica tiene tarea "massive": D.conjunto la agrupa por `tarea` y cae
        self.assertFalse([r for r in filas if r["id"].startswith("massive")])

    def test_avisa_de_nombre_sin_filas(self):
        _, info, _ = self.preparar(["massive", "noexiste"])
        self.assertEqual(info["excluir"]["sin_filas_locales"], ["noexiste"])

    def test_dev_tambien(self):
        a = self.args(["massive"])
        a.meta, a.dev_max = None, 4000
        dev = entrenar.preparar_dev(a)
        self.assertEqual([r["id"] for r in dev if r["id"].startswith("massive")], [])
        self.assertEqual(dev, [])  # los únicos dev del fixture son de massive

    def test_main_con_la_opcion(self):
        from contextlib import redirect_stdout
        from io import StringIO
        enc = CodificadorFalso()
        sal, out = Path(self.tmp.name) / "sal", StringIO()
        with mock.patch.object(entrenar, "Codificador", lambda **kw: enc), redirect_stdout(out):
            rc = entrenar.main(["--salida", str(sal), "--datos", self.ruta, "--pasos", "2", "--lote", "4", "--device", "cpu",
                                "--ckpt-cada", "0", "--excluir-tareas", "massive,hatecheck,inyecciones"])
        self.assertEqual(rc, 0)
        self.assertIn('"filas": 9', out.getvalue())


if __name__ == "__main__":
    unittest.main()
