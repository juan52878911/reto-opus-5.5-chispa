import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from chispa import formato
from chispa.cli import main
from chispa.cliente import ChispaError
from chispa.train import entrenar

ESQ = {"id": "urg", "pregunta": "¿Qué tan urgente es?", "tipo": "choice",
       "opciones": {"alta": "Requiere atención inmediata", "baja": "Puede esperar"}}


def embeber_falso(textos):
    """L1 falso de dim 4: «urgente» → eje 0, «luego» → eje 1 y mezcla si trae las dos; «vacio» no se tokeniza."""
    E, ok = np.zeros((len(textos), 4), np.float32), np.ones(len(textos), bool)
    for i, t in enumerate(textos):
        E[i] = [("urgente" in t) * 1.0 + 0.5 * ("luego" in t) * ("urgente" in t), ("luego" in t) * 1.0, 0, 0]
        ok[i] = "vacio" not in t and E[i].any()
        E[i] /= np.linalg.norm(E[i]) or 1
    return E, ok


class TestSOPL1EnTrain(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        (self.d / "l1.bin").write_bytes(b"l1-falso")
        with open(self.d / "ej.jsonl", "w") as f:
            for i in range(3):
                f.write(json.dumps({"texto": f"urgente ya {i}", "etiqueta": "alta"}) + "\n")
            f.write(json.dumps({"texto": "urgente luego", "etiqueta": "alta"}) + "\n")
            for i in range(2):
                f.write(json.dumps({"texto": f"luego caso {i}", "etiqueta": "baja"}) + "\n")
            f.write(json.dumps({"texto": "vacio", "etiqueta": "baja"}) + "\n")

    def correr(self, salida, **kw):
        kw.setdefault("log", lambda m: None)
        kw.setdefault("l1", self.d / "l1.bin")
        return entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / salida, usar_go=False, embeber=embeber_falso, **kw)

    def test_sin_flag_el_fichero_es_el_de_siempre(self):
        inf = self.correr("a.chispa")
        self.assertNotIn("SOPL1", inf["secciones"])
        self.assertNotIn(formato.SOPL1, formato.leer((self.d / "a.chispa").read_bytes()))

    def test_con_flag_escribe_k_y_media(self):
        logs = []
        base = self.correr("a.chispa")
        inf = self.correr("b.chispa", shrinkage_lambda=2.0, log=logs.append)
        self.assertEqual(inf["secciones"][-1], "SOPL1")
        self.assertTrue(inf["soporte"]["tau_sin_encogimiento"])
        self.assertTrue(any("sin el encogimiento" in a for a in inf["avisos"]))
        self.assertEqual(inf["soporte"]["k"], {"alta": 4, "baja": 2})  # «vacio» no lo ve L1: no cuenta
        self.assertTrue(any("l1_shrinkage_lambda" in m for m in logs), logs)
        a, b = formato.leer((self.d / "a.chispa").read_bytes()), formato.leer((self.d / "b.chispa").read_bytes())
        self.assertEqual({t: v for t, v in b.items() if t != formato.SOPL1}, a)  # las demás secciones, byte a byte
        sec = formato.leer_sopl1(b[formato.SOPL1])
        e = sec["entradas"][0]
        self.assertEqual((sec["dim"], e["ids"], e["k"].tolist()), (4, ["alta", "baja"], [4, 2]))
        self.assertEqual(e["hash"], formato.clave_conj(ESQ["pregunta"], ["baja", "alta"]))
        media = e["media"].astype(np.float32) * e["escala"][:, None]
        E, _ = embeber_falso(["urgente ya 0", "urgente ya 1", "urgente ya 2", "urgente luego"])
        np.testing.assert_allclose(media[0], E.mean(axis=0), atol=0.005)
        np.testing.assert_allclose(media[1], embeber_falso(["luego caso 0"])[0][0], atol=0.005)

    def test_lambda_cero_e_infinito_escriben_y_nil_apaga(self):
        # nil = apagado; 0 (solo ejemplos) e inf (solo descripción) son valores de la fórmula: escriben la misma SOPL1.
        for nombre, lam in (("c.chispa", math.inf), ("c0.chispa", 0.0)):
            inf = self.correr(nombre, shrinkage_lambda=lam)
            self.assertIn("SOPL1", inf["secciones"])
            self.assertEqual(inf["soporte"]["lambda_sugerida"], "inf" if lam == math.inf else 0.0)
            json.dumps(inf)  # el informe sigue siendo JSON estricto
        a, b = (formato.leer((self.d / n).read_bytes())[formato.SOPL1] for n in ("c.chispa", "c0.chispa"))
        self.assertEqual(a, b)
        self.correr("a.chispa")  # sin la opción: apagado, sin SOPL1
        self.assertNotIn(formato.SOPL1, formato.leer((self.d / "a.chispa").read_bytes()))
        for mal in (-1.0, math.nan):
            with self.assertRaises(ChispaError):
                self.correr("d.chispa", shrinkage_lambda=mal)

    def test_con_normas_de_conjunta_escribe_v2(self):
        from chispa.train import seccion_sopl1
        from chispa import conjunta as cj
        # n = 3, K = 2: ranura 0 = (1,0),(1,0),(0,1) ⇒ ‖media‖ = √5/3; ranura 1 = (1,0)×3 ⇒ 1. Una clase con solo L2c («alta» en CONJ).
        suma = np.array([[[2.0, 1.0], [3.0, 0.0]]])
        normas = cj.normas_de_suma(suma, [3])
        np.testing.assert_allclose(normas, [[5 ** 0.5 / 3, 1.0]], atol=1e-7)
        import chispa.train as tr
        q, _ = tr.cargar_esquema(self.d / "e.json", None)
        ex = [("urgente ya 0", "alta"), ("luego caso 0", "baja")]
        b, ks, dim = seccion_sopl1(q, ex, embeber_falso, {"clases": ["alta"], "normas": normas})
        self.assertEqual(b[:4].hex(), "02000000")
        e = formato.leer_sopl1(b)["entradas"][0]
        np.testing.assert_allclose(e["normas"], [[5 ** 0.5 / 3, 1.0], [0.0, 0.0]], atol=1e-7)  # «baja» no está en CONJ: ceros
        self.assertEqual(seccion_sopl1(q, ex, embeber_falso)[0][:4].hex(), "01000000")

    def test_sin_l1_no_hay_con_que_embeber(self):
        logs = []
        inf = self.correr("e.chispa", l1=None, shrinkage_lambda=1.0, log=logs.append)
        self.assertEqual(inf["omitidas"]["SOPL1"], "sin --l1")
        self.assertNotIn(formato.SOPL1, formato.leer((self.d / "e.chispa").read_bytes()))

    def test_cli_acepta_la_opcion(self):
        visto = {}
        import chispa.train as train
        orig, train.entrenar = train.entrenar, lambda *a, **kw: visto.update(kw)
        try:
            self.assertEqual(main(["train", "--esquema", str(self.d / "e.json"), "--salida", str(self.d / "x.chispa"),
                                   "--ejemplos", str(self.d / "ej.jsonl"), "--l1", str(self.d / "l1.bin"), "--shrinkage-lambda", "3"]), 0)
        finally:
            train.entrenar = orig
        self.assertEqual(visto["shrinkage_lambda"], 3.0)
        with self.assertRaises(SystemExit):
            main(["train", "--esquema", "x", "--salida", "y", "--shrinkage-lambda", "mucho"])


if __name__ == "__main__":
    unittest.main()
