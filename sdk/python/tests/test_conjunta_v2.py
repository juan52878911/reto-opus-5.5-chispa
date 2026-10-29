"""`--conjunta` escribe CONJ con la versión del ESQUEMAS del `.chispa` (v2 → HashEsquema2; v1 → v1).

Con CHISPA_REGENERAR=1 el test de v2 deja el fichero en server/decide/testdata/conj-v2.chispa (lo lee conj_v2_test.go).
Usa el modelo y el codificador falsos de model/l2/tests: necesita torch (CPU) y el repo en PYTHONPATH."""
import json
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from chispa import formato
from chispa.train import encontrar_repo, entrenar
from tests.test_train import ESQ, ejemplos

REPO = Path(encontrar_repo())
TESTDATA = REPO / "server" / "decide" / "testdata"
DIM = 256


class TestConjuntaVersion(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        with open(self.d / "ej.jsonl", "w") as f:
            for t, e in ejemplos():
                f.write(json.dumps({"texto": t, "etiqueta": e}) + "\n")
        from model.l2.modelo import ModeloL2
        from model.l2.tests.falso import CodificadorFalso
        import torch
        torch.manual_seed(0)
        self.modelo_enc = (ModeloL2(), CodificadorFalso())
        self.opciones = [(i, d) for i, d in ESQ["opciones"].items()]
        self.clave2 = formato.hash_esquema2(ESQ["pregunta"], ESQ["tipo"], self.opciones)

    def l2(self, version):
        h = self.clave2 if version == 2 else formato.hash_esquema(ESQ["pregunta"], sorted(ESQ["opciones"]))
        esq = formato.esquemas(DIM, [{"hash": h, "escala": 1.0, "vec": np.arange(DIM, dtype=np.int8)}], version=version)
        onnx = (TESTDATA / "l2_sintetico_ml256.onnx").read_bytes()
        (self.d / "l2.chispa").write_bytes(formato.escribir({formato.L2: onnx, formato.ESQUEMAS: esq}))

    def correr(self, salida):
        return entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / salida, l2=str(self.d / "l2.chispa"),
                        conjunta=True, ckpt="falso", modelo_l2=self.modelo_enc, log=lambda m: None)

    def test_esquemas_v2_da_conj_v2_con_la_misma_clave(self):
        self.l2(2)
        self.correr("v2.chispa")
        s = formato.leer((self.d / "v2.chispa").read_bytes())
        self.assertEqual(formato.version_esquemas(s[formato.ESQUEMAS]), 2)
        self.assertEqual(struct.unpack_from("<II", s[formato.CONJ]), (formato.CONJ_VERSION2, 1))
        self.assertEqual(s[formato.CONJ][8:24], self.clave2)  # 16 bytes: HashEsquema2 de la pregunta
        self.assertEqual(s[formato.ESQUEMAS][8:24], self.clave2)  # la misma que la entrada de ESQUEMAS
        if os.environ.get("CHISPA_REGENERAR") == "1":
            shutil.copy(self.d / "v2.chispa", TESTDATA / "conj-v2.chispa")

    def test_esquemas_v1_sigue_dando_conj_v1(self):
        self.l2(1)
        self.correr("v1.chispa")
        s = formato.leer((self.d / "v1.chispa").read_bytes())
        self.assertEqual(formato.version_esquemas(s[formato.ESQUEMAS]), 1)
        self.assertEqual(struct.unpack_from("<II", s[formato.CONJ]), (formato.CONJ_VERSION, 1))
        self.assertEqual(s[formato.CONJ][8:40], formato.hash_esquema(ESQ["pregunta"], sorted(ESQ["opciones"])))

    def test_version_esquemas(self):
        self.assertEqual(formato.version_esquemas(b"esq"), 1)
        self.assertEqual(formato.version_esquemas(b""), 1)


if __name__ == "__main__":
    unittest.main()
