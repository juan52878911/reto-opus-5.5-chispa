"""ZB-8: `entrenar_multi` con --ckpt propaga la versión del texto de torre del l2.chispa generado (`_texto_torre_l2`)."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from chispa import formato
from chispa.cliente import ChispaError
from chispa.multi import entrenar_multi
from chispa.train import entrenar

from tests.fixture_torre import onnx_torre

ESQ = {"id": "temas", "pregunta": "¿Qué temas?", "tipo": "multi",
       "opciones": [{"id": "a", "description": "A"}, {"id": "b", "description": "B"}]}


class TestMultiTextoTorreCkpt(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        (self.d / "t.onnx").write_bytes(onnx_torre())  # torre autodetectada v1

    def exportador_v2(self):
        meta = json.dumps({"version": 1, "tareas": ["x"], "licencias": {}, "dorado": "", "texto_torre": "v2_sin_id"}).encode()
        secs = {formato.L2: b"x", formato.ESQUEMAS: b"y", formato.META: meta}

        def falso(cmd, **kw):
            if cmd[2] == "model.l2.exportar":
                Path(cmd[cmd.index("--salida") + 1]).write_bytes(formato.escribir(secs))
            return mock.Mock(returncode=0, stderr="")
        return mock.patch("chispa.train.subprocess.run", falso)

    def test_entrenar_multi_devuelve_texto_torre_l2(self):
        from chispa.datos import cargar_esquema
        q, extra = cargar_esquema(self.d / "e.json", None)
        with self.exportador_v2():
            inf = entrenar_multi(None, q, extra, self.d / "o.chispa", ckpt="ck", repo=str(self.d), log=lambda m: None)
        self.assertEqual(inf.get("_texto_torre_l2"), "v2_sin_id")

    def test_discrepancia_con_la_torre_se_detecta_en_multi(self):
        with self.exportador_v2(), self.assertRaisesRegex(ChispaError, "no coincide"):
            entrenar(None, self.d / "e.json", self.d / "o.chispa", ckpt="ck", repo=str(self.d), torre=self.d / "t.onnx", log=lambda m: None)
        self.assertFalse((self.d / "o.chispa").exists())
