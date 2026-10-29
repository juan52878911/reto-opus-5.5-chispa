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
        kw.setdefault("embeber", embeber_falso)
        return entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / salida, usar_go=False, **kw)

    def test_sin_soporte_el_fichero_es_el_de_siempre(self):
        inf = self.correr("a.chispa", sin_soporte=True)
        self.assertNotIn("SOPL1", inf["secciones"])
        self.assertNotIn(formato.SOPL1, formato.leer((self.d / "a.chispa").read_bytes()))
        with self.assertRaises(ChispaError):  # --sin-soporte y --shrinkage-lambda se excluyen
            self.correr("x.chispa", sin_soporte=True, shrinkage_lambda=2.0)

    def test_por_defecto_escribe_sopl1_con_lambda_sugerida_4(self):
        inf = self.correr("p.chispa")
        self.assertEqual(inf["secciones"][-1], "SOPL1")
        self.assertEqual(inf["soporte"]["lambda_sugerida"], 4.0)
        # mismo fichero que con --shrinkage-lambda explícito salvo l1_lambda_calib de CALIB
        self.correr("q.chispa", shrinkage_lambda=1.0)
        p, q = (formato.leer((self.d / n).read_bytes()) for n in ("p.chispa", "q.chispa"))
        self.assertEqual({t: v for t, v in p.items() if t != formato.CALIB}, {t: v for t, v in q.items() if t != formato.CALIB})
        self.assertEqual(json.loads(p[formato.CALIB])["l1_lambda_calib"], 4.0)
        self.assertEqual(json.loads(q[formato.CALIB])["l1_lambda_calib"], 1.0)
        # sin --l1 o sin ejemplos, el default no escribe nada ni avisa
        logs = []
        inf = self.correr("n.chispa", l1=None, log=logs.append)
        self.assertNotIn("SOPL1", inf["secciones"])
        self.assertFalse(any("SOPL1" in m for m in logs), logs)

    def test_con_flag_escribe_k_y_media(self):
        logs = []
        base = self.correr("a.chispa", sin_soporte=True)
        inf = self.correr("b.chispa", shrinkage_lambda=2.0, log=logs.append)
        self.assertEqual(inf["secciones"][-1], "SOPL1")
        self.assertFalse(inf["soporte"]["tau_con_encogimiento_l1"])  # usar_go=False: el τ no lo calibró el entrenador
        self.assertTrue(any("l1_lambda_calib=2" in a for a in inf["avisos"]), inf["avisos"])
        self.assertEqual(inf["soporte"]["k"], {"alta": 4, "baja": 2})  # «vacio» no lo ve L1: no cuenta
        self.assertTrue(any("l1_shrinkage_lambda" in m for m in logs), logs)
        a, b = formato.leer((self.d / "a.chispa").read_bytes()), formato.leer((self.d / "b.chispa").read_bytes())
        self.assertEqual({t: v for t, v in b.items() if t not in (formato.SOPL1, formato.CALIB)}, {t: v for t, v in a.items() if t != formato.CALIB})
        self.assertEqual(json.loads(b[formato.CALIB]), {**json.loads(a[formato.CALIB]), "l1_lambda_calib": 2.0})  # las demás secciones, byte a byte
        sec = formato.leer_sopl1(b[formato.SOPL1])
        e = sec["entradas"][0]
        self.assertEqual((sec["dim"], e["ids"], e["k"].tolist()), (4, ["alta", "baja"], [4, 2]))
        self.assertEqual(e["hash"], formato.clave_conj(ESQ["pregunta"], ["baja", "alta"]))
        media = e["media"].astype(np.float32) * e["escala"][:, None]
        E, _ = embeber_falso(["urgente ya 0", "urgente ya 1", "urgente ya 2", "urgente luego"])
        np.testing.assert_allclose(media[0], E.mean(axis=0), atol=0.005)
        np.testing.assert_allclose(media[1], embeber_falso(["luego caso 0"])[0][0], atol=0.005)

    def test_fallo_al_embeber_degrada_en_el_default_y_aborta_si_explicito(self):
        def roto(textos):
            raise ChispaError("embeber falló:\nx")
        inf = entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / "r.chispa", usar_go=False, embeber=roto, l1=self.d / "l1.bin", log=lambda m: None)
        self.assertNotIn("SOPL1", inf["secciones"])
        self.assertIn("SOPL1", inf["omitidas"])
        with self.assertRaises(ChispaError):
            entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / "r2.chispa", usar_go=False, embeber=roto, l1=self.d / "l1.bin",
                     shrinkage_lambda=4.0, log=lambda m: None)

    def test_lambda_cero_e_infinito_escriben_y_sin_soporte_apaga(self):
        # --sin-soporte = apagado; 0 (solo ejemplos) e inf (solo descripción) son valores de la fórmula: escriben la misma SOPL1.
        for nombre, lam in (("c.chispa", math.inf), ("c0.chispa", 0.0)):
            inf = self.correr(nombre, shrinkage_lambda=lam)
            self.assertIn("SOPL1", inf["secciones"])
            self.assertEqual(inf["soporte"]["lambda_sugerida"], "inf" if lam == math.inf else 0.0)
            json.dumps(inf)  # el informe sigue siendo JSON estricto
        a, b = (formato.leer((self.d / n).read_bytes())[formato.SOPL1] for n in ("c.chispa", "c0.chispa"))
        self.assertEqual(a, b)
        self.correr("a.chispa", sin_soporte=True)  # --sin-soporte: sin SOPL1
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

    def test_con_n_del_soporte_de_conjunta_escribe_v3_con_n_l2(self):
        from chispa.train import seccion_sopl1
        import chispa.train as tr
        q, _ = tr.cargar_esquema(self.d / "e.json", None)
        ex = [("urgente ya 0", "alta"), ("urgente ya 1", "alta"), ("urgente ya 2", "alta"), ("luego caso 0", "baja")]
        # L1 ve 3 ejemplos de «alta»; el soporte de CONJ solo 2 (k ≠ n_l2). «baja» no está en CONJ ⇒ 0 (sin dato).
        cj = {"clases": ["alta"], "normas": np.array([[0.5, 1.0]], np.float32), "n": np.array([2], np.uint32)}
        b, ks, _ = seccion_sopl1(q, ex, embeber_falso, cj)
        self.assertEqual(b[:4].hex(), "03000000")
        e = formato.leer_sopl1(b)["entradas"][0]
        self.assertEqual(e["k"].tolist(), [3, 1])
        self.assertEqual(e["n_l2"].tolist(), [2, 0])
        sin_n = {k: v for k, v in cj.items() if k != "n"}
        self.assertEqual(seccion_sopl1(q, ex, embeber_falso, sin_n)[0][:4].hex(), "02000000")

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

    # R6-2: CALIB lleva el λ de L1 del soporte; los fallos al embeber sin λ explícito degradan a aviso.

    def calib(self, nombre):
        return json.loads(formato.leer((self.d / nombre).read_bytes())[formato.CALIB])

    def test_sin_soporte_o_lambda_infinito_no_llevan_el_campo(self):
        self.correr("a.chispa", sin_soporte=True)
        self.assertNotIn("l1_lambda_calib", self.calib("a.chispa"))
        self.correr("b.chispa", shrinkage_lambda=float("inf"))
        self.assertNotIn("l1_lambda_calib", self.calib("b.chispa"))  # json.dumps(inf) no sería JSON válido para Go

    def test_fallo_no_chispaerror_sin_lambda_explicito_degrada_a_aviso(self):
        for exc in (FileNotFoundError("go"), KeyError("x"), ValueError("reshape"), json.JSONDecodeError("m", "d", 0)):
            with self.subTest(exc=type(exc).__name__):
                def roto(textos, exc=exc):
                    raise exc
                logs = []
                inf = self.correr("r.chispa", embeber=roto, log=logs.append)
                self.assertNotIn("SOPL1", inf["secciones"])
                self.assertIn("SOPL1", inf["omitidas"])
                self.assertTrue(any("sin SOPL1" in m for m in logs), logs)
                self.assertNotIn("l1_lambda_calib", self.calib("r.chispa"))

    def test_fallo_con_lambda_explicito_sigue_abortando(self):
        def roto(textos):
            raise FileNotFoundError("go")
        with self.assertRaises(FileNotFoundError):
            self.correr("r.chispa", embeber=roto, shrinkage_lambda=2.0)

    def test_si_el_entrenador_calibro_con_encogimiento_y_no_hay_sopl1_se_quita_el_campo_y_avisa(self):
        from chispa.train import anadir_sopl1
        sal = self.d / "g.chispa"
        sal.write_bytes(formato.escribir({formato.META: formato.meta(["urg"], {}, ""), formato.CALIB: formato.calib({}, 0.5, l1_lambda_calib=4.0)}))
        inf = {"calib": {"l1_lambda_calib": 4.0}}
        def roto(textos):
            raise OSError("go")
        anadir_sopl1(sal, None, [], "l1", 4.0, inf, lambda m: None)  # sin ejemplos: no escribe SOPL1
        self.assertNotIn("l1_lambda_calib", json.loads(formato.leer(sal.read_bytes())[formato.CALIB]))
        self.assertTrue(any("descalibrado" in a for a in inf["avisos"]), inf)
