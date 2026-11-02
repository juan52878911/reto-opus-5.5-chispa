"""texto_torre en `chispa train` (META del l2.chispa y del ONNX de la torre) y la validación de META de `formato.meta`."""
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from chispa import formato
from chispa.cliente import ChispaError
from chispa.cli import main
from chispa.train import _cierre_entrenar, entrenar, resumen_capas

from tests.fixture_torre import onnx_torre
from tests.test_train import ESQ

SHA = "ab" * 32


class TestMetaValida(unittest.TestCase):
    def test_licencias_anidadas(self):
        with self.assertRaisesRegex(ValueError, "licencias.*strings"):
            formato.meta(["q"], {"massive": {"licencia": "CC-BY"}}, "")
        with self.assertRaisesRegex(ValueError, "licencias"):
            formato.meta(["q"], ["CC-BY"], "")

    def test_dorado(self):
        for malo in ("dorado/v3.jsonl", "AB" * 32, "ab" * 31, 7):
            with self.assertRaisesRegex(ValueError, "dorado.*sha256"):
                formato.meta(["q"], {}, malo)

    def test_validos(self):
        d = json.loads(formato.meta(["q"], {"massive": "CC-BY"}, SHA))
        self.assertEqual((d["licencias"], d["dorado"], "texto_torre" in d), ({"massive": "CC-BY"}, SHA, False))
        self.assertEqual(json.loads(formato.meta(["q"]))["dorado"], "")
        self.assertEqual(json.loads(formato.meta(["q"], texto_torre="v2_sin_id"))["texto_torre"], "v2_sin_id")
        self.assertNotIn("texto_torre", json.loads(formato.meta(["q"], texto_torre="v1")))
        with self.assertRaisesRegex(ValueError, "texto_torre.*v9"):
            formato.meta(["q"], texto_torre="v9")


class TestTextoTorreTrain(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        (self.d / "l1.bin").write_bytes(b"l1-falso")

    def l2(self, texto=None, nombre="l2.chispa", **meta):
        secs = {formato.L2: b"onnx", formato.ESQUEMAS: struct.pack("<II", 8, 0)}
        if texto is not None or meta:
            secs[formato.META] = json.dumps({"version": 1, "tareas": ["x"], "licencias": {}, "dorado": "",
                                             **({"texto_torre": texto} if texto else {}), **meta}).encode()
        (self.d / nombre).write_bytes(formato.escribir(secs))
        return str(self.d / nombre)

    def onnx(self, texto=None):
        (self.d / "t.onnx").write_bytes(onnx_torre(meta={"chispa.torre.texto_torre": texto} if texto else None))
        return self.d / "t.onnx"

    def correr(self, **kw):
        return entrenar(None, self.d / "e.json", self.d / "s.chispa", l1=self.d / "l1.bin", log=lambda m: None, **kw)

    def texto(self):
        return json.loads(formato.leer((self.d / "s.chispa").read_bytes())[formato.META]).get("texto_torre")

    def test_l2_v2_y_onnx_v2_dan_chispa_v2(self):
        inf = self.correr(l2=self.l2("v2_sin_id"), torre=self.onnx("v2_sin_id"))
        self.assertEqual(self.texto(), "v2_sin_id")
        self.assertEqual(inf["texto_torre"], "v2_sin_id")
        self.assertIn("TORR", inf["secciones"])
        # lo que lee el lector de Go (MetaTexto): los campos de Meta siguen ahí
        d = json.loads(formato.leer((self.d / "s.chispa").read_bytes())[formato.META])
        self.assertEqual(sorted(d), ["dorado", "licencias", "tareas", "texto_torre", "version"])

    def torr(self):
        return formato.leer_torr(formato.leer((self.d / "s.chispa").read_bytes())[formato.TORR])

    def test_torr_lleva_la_version_del_texto(self):
        self.correr(l2=self.l2("v2_sin_id"), torre=self.onnx("v2_sin_id"))
        raw = formato.leer((self.d / "s.chispa").read_bytes())[formato.TORR]
        self.assertEqual((struct.unpack("<I", raw[:4])[0], self.torr()["texto_torre"]), (2, "v2_sin_id"))
        inf = self.correr(l2=self.l2(), torre=self.onnx())  # v1: TORR v1, como siempre
        raw = formato.leer((self.d / "s.chispa").read_bytes())[formato.TORR]
        self.assertEqual((struct.unpack("<I", raw[:4])[0], self.torr()["texto_torre"], inf["torre"]["texto_torre"]), (1, "v1", "v1"))

    def test_avisa_de_descripciones_repetidas(self):
        (self.d / "e.json").write_text(json.dumps({"id": "u", "pregunta": "¿Cuál?", "tipo": "choice", "opciones": {
            "a": "igual", "b": "  igual\t", "c": "otra", "d": "", "e": " "}}))
        for version, avisa in (("v2_sin_id", True), ("v1", False)):
            log = []
            entrenar(None, self.d / "e.json", self.d / "s.chispa", l1=self.d / "l1.bin", l2=self.l2(None if version == "v1" else version),
                     torre=self.onnx(None if version == "v1" else version), log=log.append)
            av = [m for m in log if "descripción repetida" in m]
            self.assertEqual(len(av), 1 if avisa else 0, log)
            if avisa:
                self.assertIn("'a', 'b'", av[0])
                self.assertIn("'igual'", av[0])
        from chispa.torre import descripciones_repetidas
        from chispa.datos import Opcion
        self.assertEqual(descripciones_repetidas([Opcion("a", "x"), Opcion("b", "y"), Opcion("c", " x ")]), {"x": ["a", "c"]})
        self.assertEqual(descripciones_repetidas([Opcion("a", "Saldo"), Opcion("b", "saldo"), Opcion("c", ""), Opcion("d", " ")]), {})

    def test_l2_v2_sin_torre_copia_v2(self):
        self.correr(l2=self.l2("v2_sin_id"))
        self.assertEqual(self.texto(), "v2_sin_id")

    def test_l2_v2_y_onnx_sin_clave_falla_y_no_deja_fichero(self):
        with self.assertRaisesRegex(ChispaError, "texto_torre no coincide.*v2_sin_id.*v1"):
            self.correr(l2=self.l2("v2_sin_id"), torre=self.onnx())
        self.assertFalse((self.d / "s.chispa").exists())

    def test_l2_sin_campo_es_v1(self):
        inf = self.correr(l2=self.l2(), torre=self.onnx())
        self.assertEqual((self.texto(), inf["texto_torre"]), (None, "v1"))
        self.correr(l2=self.l2(licencias={"a": "b"}))
        self.assertIsNone(self.texto())

    def test_flag(self):
        self.correr(l2=self.l2("v2_sin_id"), torre=self.onnx("v2_sin_id"), texto_torre="v2_sin_id")
        self.assertEqual(self.texto(), "v2_sin_id")
        for kw in ({"l2": self.l2("v2_sin_id", "a.chispa"), "texto_torre": "v1"},
                   {"l2": self.l2(None, "b.chispa"), "texto_torre": "v2_sin_id"},
                   {"l2": self.l2("v2_sin_id", "c.chispa"), "torre": self.onnx("v2_sin_id"), "texto_torre": "v1"},
                   {"torre": self.onnx("v2_sin_id"), "texto_torre": "v1"}):
            with self.assertRaisesRegex(ChispaError, "no coincide"):
                self.correr(**kw)

    def test_flag_sin_l2_escribe_lo_que_diga(self):
        self.correr(texto_torre="v2_sin_id")
        self.assertEqual(self.texto(), "v2_sin_id")
        self.correr()
        self.assertIsNone(self.texto())  # por defecto v1
        self.correr(torre=self.onnx("v2_sin_id"))  # sin L2, manda el ONNX
        self.assertEqual(self.texto(), "v2_sin_id")

    def test_valores_desconocidos(self):
        with self.assertRaisesRegex(ChispaError, "texto_torre.*v9"):
            self.correr(l2=self.l2("v9"))
        with self.assertRaisesRegex(ChispaError, "texto_torre.*v9"):
            self.correr(l2=self.l2(), torre=self.onnx("v9"))
        with self.assertRaisesRegex(ChispaError, "--texto-torre"):
            self.correr(texto_torre="v9")

    def test_ckpt_cierre_con_l2_generado(self):
        """Con --ckpt el l2.chispa nace dentro de train: _cierre_entrenar recibe su versión por el informe (`_texto_torre_l2`)."""
        (self.d / "s.chispa").write_bytes(formato.escribir({formato.META: formato.meta(["x"]), formato.L2: b"o"}))
        inf = {"_texto_torre_l2": "v2_sin_id", "secciones": ["META", "L2"]}
        _cierre_entrenar(inf, self.d / "s.chispa", None, None, lambda m: None, True)
        self.assertEqual(self.texto(), "v2_sin_id")
        self.assertNotIn("_texto_torre_l2", inf)
        tor = {"dim": 8, "max_len": 128, "prefijo": "passage: ", "onnx": b"x", "texto_torre": "v1"}
        with self.assertRaisesRegex(ChispaError, "no coincide"):
            _cierre_entrenar({"_texto_torre_l2": "v2_sin_id"}, self.d / "s.chispa", None, tor, lambda m: None, True)
        self.assertFalse((self.d / "s.chispa").exists())

    def test_resumen_muestra_version(self):
        self.correr(l2=self.l2("v2_sin_id"), torre=self.onnx("v2_sin_id"))
        msgs = []
        resumen_capas(self.d / "s.chispa", msgs.append)
        self.assertIn("texto de torre v2_sin_id", msgs[0])

    def test_cli_flag(self):
        main(["train", "--esquema", str(self.d / "e.json"), "--salida", str(self.d / "s.chispa"), "--l1", str(self.d / "l1.bin"),
              "--l2", self.l2("v2_sin_id"), "--texto-torre", "v2_sin_id"])
        self.assertEqual(self.texto(), "v2_sin_id")
        self.assertNotEqual(main(["train", "--esquema", str(self.d / "e.json"), "--salida", str(self.d / "s2.chispa"), "--l1", str(self.d / "l1.bin"),
                  "--l2", self.l2("v2_sin_id"), "--texto-torre", "v1"]), 0)


class TestZeroShotMetaLibre(unittest.TestCase):
    """El esquema con licencias anidadas o dorado libre falla ahora con mensaje claro en vez de producir un .chispa que no carga."""

    def test_esquema_con_licencias_anidadas(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d)
        (d / "l1.bin").write_bytes(b"l1")
        (d / "e.json").write_text(json.dumps({**ESQ, "licencias": {"massive": {"licencia": "CC-BY"}}, "dorado": "dorado/v3.jsonl"}))
        with self.assertRaisesRegex(ValueError, "licencias"):
            entrenar(None, d / "e.json", d / "s.chispa", l1=d / "l1.bin", log=lambda m: None)
