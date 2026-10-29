"""CALIB `multi_l2@<hex>` / `multi_l2@<hex>#<id>`: la forma de las claves y el ida y vuelta con el servidor (Go, `multi_test.go`)."""
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import torch

from model.l2 import calibrar as C
from model.l2 import exportar as E
from model.l2.modelo import ModeloL2
from model.l2.tests.gen_esquemas_v2 import fila, hash_esquema2
from model.l2.tests.test_t24_exportar import CodificadorDiminuto

PREGUNTA = "¿Qué temas toca?"
OPS = ["precio", "envio", "garantia"]
DESC = {"precio": "Cuánto cuesta.", "envio": "", "garantia": "Cobertura."}
ETIQ = ["precio", "envio|garantia", "", "precio|envio", "garantia", "precio|garantia", "envio", "precio|envio|garantia"]


def filas_multi(pregunta=PREGUNTA, n=24):
    fs = []
    for i in range(n):
        r = fila(i, "multi", pregunta, OPS, DESC, ETIQ[i % len(ETIQ)])
        r["split"], r["tarea"] = "dev", "temas"
        fs.append(r)
    return fs


def esperadas(pregunta=PREGUNTA):
    h = hash_esquema2(pregunta, "multi", [(o, DESC[o]) for o in OPS]).hex()
    return "multi_l2@" + h, ["multi_l2@%s#%s" % (h, o) for o in OPS]


class ClavesMultiL2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(1)
        cls.modelo, cls.enc = ModeloL2().eval(), CodificadorDiminuto()

    def test_forma_de_las_claves(self):
        base, por_opcion = esperadas()
        tipos = C.calibrar_multi_l2(self.modelo, self.enc, filas_multi())
        self.assertEqual(sorted(tipos), sorted([base] + por_opcion))
        for k in tipos:
            self.assertRegex(k, r"^multi_l2@[0-9a-f]{32}(#[a-z]+)?$")
            self.assertEqual(set(tipos[k]), {"T", "a", "b", "theta"})
            self.assertGreater(tipos[k]["T"], 0)
            self.assertTrue(0.05 <= tipos[k]["theta"] <= 0.95)
        # a y b son del esquema: todas las opciones comparten los de la clave base
        for k in por_opcion:
            self.assertEqual((tipos[k]["a"], tipos[k]["b"]), (tipos[base]["a"], tipos[base]["b"]))

    def test_un_esquema_por_pregunta_y_etiquetas_en_lista(self):
        otras = filas_multi("¿Y de qué más?")
        for r in otras:
            r["etiqueta"] = sorted(C.etiquetas_multi(r["etiqueta"]))
        tipos = C.calibrar_multi_l2(self.modelo, self.enc, filas_multi() + otras)
        self.assertEqual(sorted(tipos), sorted(esperadas()[1] + [esperadas()[0]] + [esperadas("¿Y de qué más?")[0]]
                                               + esperadas("¿Y de qué más?")[1]))

    def test_sin_variacion_no_se_ajusta(self):
        fs = filas_multi()
        for r in fs:
            r["etiqueta"] = ""
        self.assertEqual(C.calibrar_multi_l2(self.modelo, self.enc, fs), {})
        self.assertEqual(C.calibrar_multi_l2(self.modelo, self.enc, []), {})

    def test_calibrar_las_separa_de_las_cabezas_y_va_a_calib(self):
        inf = C.calibrar(self.modelo, self.enc, filas_multi())
        self.assertNotIn("multi", inf["tipos"])
        ch = C.a_calib_chispa(inf)
        self.assertIn(esperadas()[0], ch["tipos"])
        self.assertEqual(len(ch["tipos"]), 4)

    def test_exportador_completa_lo_que_falta_y_respeta_lo_que_hay(self):
        fs = filas_multi()
        vacia = {"tipos": {}, "tau_escalate": 0.5}
        self.assertEqual(sorted(E.calib_con_multi(self.modelo, self.enc, vacia, fs)["tipos"]), sorted(esperadas()[1] + [esperadas()[0]]))
        previa = {"tipos": {esperadas()[0]: {"T": 1, "a": 7, "b": 0, "theta": 0.5}}, "tau_escalate": 0.5}
        self.assertIs(E.calib_con_multi(self.modelo, self.enc, previa, fs), previa)


class ConElServidor(unittest.TestCase):
    def test_l2_opina_en_multi_con_un_chispa_exportado(self):
        torch.manual_seed(1)
        modelo, enc = ModeloL2().eval(), CodificadorDiminuto()
        fs = filas_multi()
        calib = {"chispa": C.a_calib_chispa(C.calibrar(modelo, enc, fs))}
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            E.construir(modelo, enc, enc.enc, {}, calib, fs, d / "l2.chispa", d / "w", None, [], latencias=())
            esp = d / "esperado.json"
            base, por_opcion = esperadas()
            esp.write_text(json.dumps({"pregunta": PREGUNTA, "opciones": [{"id": o, "description": DESC[o]} for o in OPS],
                                       "claves": [base] + por_opcion}))
            env = {**os.environ, "CHISPA_MULTI": str(d / "l2.chispa"), "CHISPA_MULTI_ESPERADO": str(esp), "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
            p = subprocess.run([E.go_bin(), "test", "-count=1", "-run", "TestMultiL2Opina", "-v", "."], cwd=E.GO_DIR, env=env,
                               capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("SKIP", p.stdout)
        self.assertNotRegex(p.stdout + p.stderr, re.compile("AVISO"))


if __name__ == "__main__":
    unittest.main()
