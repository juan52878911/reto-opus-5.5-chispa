import json
import shutil
import tempfile
import unittest
from pathlib import Path

from onnx import TensorProto as TP

from chispa import formato
from chispa.cliente import ChispaError
from chispa.cli import main
from chispa.train import encontrar_go, encontrar_repo, entrenar

from fixture_torre import onnx_torre
from test_train import ESQ, PAL

SINTETICO = Path(__file__).resolve().parents[3] / "server/torre/testdata/sintetico.onnx"
CON_GO = unittest.skipUnless(encontrar_go() and encontrar_repo(), "sin Go o sin repositorio")


class TestTorreTrain(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        (self.d / "l1.bin").write_bytes(b"l1-falso")
        (self.d / "l2.chispa").write_bytes(formato.escribir({formato.L2: b"onnx", formato.ESQUEMAS: b"esq"}))

    def onnx(self, nombre="t.onnx", **kw):
        (self.d / nombre).write_bytes(onnx_torre(**kw))
        return self.d / nombre

    def jsonl(self, k):
        with open(self.d / "ej.jsonl", "w") as f:
            for c in ("alta", "baja"):
                for i in range(k):
                    f.write(json.dumps({"texto": f"{PAL[c]} caso{i}", "etiqueta": c}) + "\n")
        return self.d / "ej.jsonl"

    def correr(self, ej, salida="s.chispa", **kw):
        kw.setdefault("log", lambda m: None)
        return entrenar(ej, self.d / "e.json", self.d / salida, **kw)

    def torr(self, salida="s.chispa"):
        return formato.leer_torr(formato.leer((self.d / salida).read_bytes())[formato.TORR])

    def test_zero_shot_con_el_sintetico(self):
        inf = self.correr(None, l1=self.d / "l1.bin", l2=str(self.d / "l2.chispa"), torre=SINTETICO)
        self.assertEqual(inf["secciones"], ["META", "L1", "L2", "ESQUEMAS", "CALIB", "TORR"])
        t = self.torr()
        self.assertEqual((t["dim"], t["max_len"], t["prefijo"], t["onnx"]), (256, 128, "passage: ", SINTETICO.read_bytes()))
        self.assertEqual(inf["bytes"], (self.d / "s.chispa").stat().st_size)

    def test_sin_torre_la_salida_es_la_de_siempre(self):
        a = self.correr(None, "a.chispa", l1=self.d / "l1.bin", l2=str(self.d / "l2.chispa"))
        b = self.correr(None, "b.chispa", l1=self.d / "l1.bin", l2=str(self.d / "l2.chispa"), torre=None)
        self.assertEqual((self.d / "a.chispa").read_bytes(), (self.d / "b.chispa").read_bytes())
        self.assertNotIn("TORR", a["secciones"] + b["secciones"])
        con = self.correr(None, "c.chispa", l1=self.d / "l1.bin", l2=str(self.d / "l2.chispa"), torre=self.onnx())
        sec = formato.leer((self.d / "c.chispa").read_bytes())
        sec.pop(formato.TORR)
        self.assertEqual(formato.escribir(sec), (self.d / "a.chispa").read_bytes())
        self.assertIn("TORR", con["secciones"])

    def test_few_shot_sin_go(self):
        inf = self.correr(self.jsonl(5), usar_go=False, torre=self.onnx())
        self.assertEqual(inf["secciones"], ["META", "CALIB", "TORR"])
        self.assertEqual(self.torr()["dim"], 8)

    @CON_GO
    def test_few_shot_con_go(self):
        a = self.correr(self.jsonl(5), "a.chispa", l2=str(self.d / "l2.chispa"))
        b = self.correr(self.jsonl(5), "b.chispa", l2=str(self.d / "l2.chispa"), torre=self.onnx())
        self.assertEqual(b["secciones"], a["secciones"] + ["TORR"])
        ba = (self.d / "a.chispa").read_bytes()
        self.assertEqual(formato.escribir(formato.leer(ba)), ba)  # reescribir en Python no altera lo que escribió Go
        sec = formato.leer((self.d / "b.chispa").read_bytes())
        del sec[formato.TORR]
        # el .chispa de Go y el reescrito en Python coinciden byte a byte (salvo L0/CALIB, que dependen del reloj: se comparan secciones)
        self.assertEqual(sec.keys(), formato.leer((self.d / "a.chispa").read_bytes()).keys())
        self.assertEqual(self.torr("b.chispa")["onnx"], (self.d / "t.onnx").read_bytes())

    @CON_GO
    def test_conjunta_con_train_escaso_cae_a_few_shot(self):
        logs = []
        inf = self.correr(self.jsonl(5), "c.chispa", l2=str(self.d / "l2.chispa"), conjunta=True, torre=self.onnx(), log=logs.append)
        self.assertTrue(any("--conjunta necesita al menos 20" in m for m in logs), logs)
        self.assertEqual((inf["modo"], inf["secciones"][-1]), ("few-shot", "TORR"))
        self.assertEqual(self.torr("c.chispa")["dim"], 8)

    def test_onnx_invalido(self):
        casos = [(dict(entrada="ids"), "input_ids"), (dict(salida="y"), "falta la salida h"), (dict(opset=13), "opset 13"),
                 (dict(tipo_ids=TP.INT32), "int64")]
        for kw, msg in casos:
            with self.assertRaisesRegex(ChispaError, msg):
                self.correr(None, l1=self.d / "l1.bin", torre=self.onnx(**kw))
            self.assertFalse((self.d / "s.chispa").exists(), kw)

    def test_sin_normalizar_falla_la_prueba(self):
        with self.assertRaisesRegex(ChispaError, "no está normalizada"):
            self.correr(None, l1=self.d / "l1.bin", torre=self.onnx(norm=False))

    def test_no_es_onnx_ni_existe(self):
        (self.d / "x.onnx").write_bytes(b"basura")
        for r, msg in ((self.d / "x.onnx", "no es un ONNX"), (self.d / "no.onnx", "no existe")):
            with self.assertRaisesRegex(ChispaError, msg):
                self.correr(None, l1=self.d / "l1.bin", torre=r)

    def test_metadatos_flags_y_choques(self):
        o = self.onnx("m.onnx", meta={"chispa.torre.max_len": 64, "chispa.torre.prefijo": "doc: "})
        self.correr(None, l1=self.d / "l1.bin", torre=o)
        t = self.torr()
        self.assertEqual((t["dim"], t["max_len"], t["prefijo"]), (8, 64, "doc: "))
        self.correr(None, l1=self.d / "l1.bin", torre=self.onnx(), torre_max_len=32, torre_prefijo="x: ")
        t = self.torr()
        self.assertEqual((t["max_len"], t["prefijo"]), (32, "x: "))
        for kw, msg in (({"torre_max_len": 32}, "choca con los metadatos"), ({"torre_prefijo": "q: "}, "choca"), ({"torre_dim": 16}, "dim")):
            with self.assertRaisesRegex(ChispaError, msg):
                self.correr(None, l1=self.d / "l1.bin", torre=o, **kw)
        with self.assertRaisesRegex(ChispaError, "dim"):
            self.correr(None, l1=self.d / "l1.bin", torre=self.onnx(), torre_dim=16)

    def test_sin_onnx_instalado_error_claro_y_sin_torre_no_se_importa(self):
        import sys
        from unittest import mock
        with mock.patch.dict(sys.modules, {"onnx": None}):
            with self.assertRaisesRegex(ChispaError, "paquete `onnx`"):
                self.correr(None, l1=self.d / "l1.bin", torre=self.onnx())
            self.correr(None, l1=self.d / "l1.bin")  # sin --torre, no toca onnx

    def test_sin_onnxruntime_avisa_y_sigue(self):
        import sys
        from unittest import mock
        logs = []
        with mock.patch.dict(sys.modules, {"onnxruntime": None}):
            self.correr(None, l1=self.d / "l1.bin", torre=self.onnx(), log=logs.append)
        self.assertTrue(any("sin onnxruntime" in m for m in logs), logs)
        self.assertIn(formato.TORR, formato.leer((self.d / "s.chispa").read_bytes()))

    def test_cli(self):
        self.assertEqual(main(["train", "--esquema", str(self.d / "e.json"), "--salida", str(self.d / "s.chispa"), "--l1",
                               str(self.d / "l1.bin"), "--torre", str(self.onnx()), "--torre-max-len", "50"]), 0)
        self.assertEqual(self.torr()["max_len"], 50)
        self.assertEqual(main(["train", "--esquema", str(self.d / "e.json"), "--salida", str(self.d / "t.chispa"), "--l1",
                               str(self.d / "l1.bin"), "--torre", str(self.d / "no.onnx")]), 1)


if __name__ == "__main__":
    unittest.main()
