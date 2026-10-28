import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from chispa import formato
from chispa.train import encontrar_go, encontrar_repo, entrenar
from tests import fixture_conjunta as fx
from tests.test_train import ESQ, ejemplos

REPO = encontrar_repo()


class TestFormatoConj(unittest.TestCase):
    def test_leer_ida_y_vuelta(self):
        secs = {formato.META: b"{}", formato.CONJ: b"abc"}
        self.assertEqual(formato.leer(formato.escribir(secs)), secs)

    def test_leer_rechaza_corrupcion(self):
        b = bytearray(formato.escribir({formato.META: b"{}"}))
        b[-1] ^= 1
        with self.assertRaises(ValueError):
            formato.leer(bytes(b))

    def test_hash_esquema_como_go(self):
        # Mismo hash que chispa3.HashEsquema("¿p?", ["a", "b"]) (lo comprueba el test de paridad de Go con la clave del fixture).
        self.assertEqual(len(formato.hash_esquema("¿p?", ["a", "b"])), 32)
        self.assertNotEqual(formato.hash_esquema("q", ["a", "b"]), formato.hash_esquema("q", ["b", "a"]))

    def test_cuantizar_protos(self):
        P = np.random.RandomState(1).randn(3, 4, 8)
        P /= np.linalg.norm(P, axis=-1, keepdims=True)
        esc, q = formato.cuantizar_protos(P)
        self.assertEqual(q.dtype, np.int8)
        self.assertLess(np.abs(q * esc[..., None] - P).max(), 0.5 * esc.max() + 1e-9)
        z = formato.cuantizar_protos(np.zeros((1, 1, 4)))[1]
        self.assertFalse(z.any())

    def test_tamano_150_clases(self):
        """Una tarea de 150 clases, 16 ranuras de 256: cabe en < 1 MB (int8 + una escala por ranura)."""
        C, K, D = 150, 16, 256
        P = np.random.RandomState(0).randn(C, K, D)
        P /= np.linalg.norm(P, axis=-1, keepdims=True)
        esc, q = formato.cuantizar_protos(P)
        b = formato.conj([{"hash": b"\0" * 32, "T": 0.05, "beta": 1.0, "esc": [1, 1, 1], "w": [1, 1, 1, 0, 0, 0],
                           "clases": [f"clase_{i:03d}" for i in range(C)], "escala": esc, "proto": q}])
        self.assertLess(len(b), 1 << 20)
        self.assertGreater(len(b), C * K * D)


@unittest.skipUnless(REPO, "sin repositorio")
class TestFixtureParidad(unittest.TestCase):
    def test_el_fixture_guardado_es_el_que_genera_conjunta_py(self):
        guardado = json.loads(fx.RUTA.read_text(encoding="utf-8"))
        nuevo = json.loads(json.dumps(fx.generar()))
        self.assertEqual(guardado["conj_b64"], nuevo["conj_b64"])
        for a, b in zip(guardado["casos"], nuevo["casos"]):
            np.testing.assert_allclose(a["probs"], b["probs"], atol=1e-9)
            np.testing.assert_allclose(a["sims"], b["sims"], atol=0)


class TestTauL2c(unittest.TestCase):
    def test_menor_tau_que_cumple_el_objetivo(self):
        from chispa.conjunta import tau_l2c
        n = 100  # conf 0,99..0,50; acierta el 100 % de las 60 más seguras y el 0 % del resto
        conf = np.linspace(0.99, 0.5, n)
        p = np.stack([conf, 1 - conf], 1)
        y = np.array([0] * 60 + [1] * 40)
        tau, prec, cob = tau_l2c(p, y, 0.95)
        self.assertGreaterEqual(prec, 0.95)
        self.assertAlmostEqual(tau, conf[62], places=9)  # el prefijo más largo con precisión >= 0,95 es 63 filas (60/63)
        self.assertAlmostEqual(cob, 63 / n)
        self.assertEqual(tau_l2c(p, 1 - y, 0.95)[0], None)  # todo mal: sin τ

    def test_objetivo_mas_exigente_da_tau_mayor(self):
        from chispa.conjunta import tau_l2c
        rng = np.random.default_rng(0)
        conf = rng.uniform(0.5, 1, 500)
        p = np.stack([conf, 1 - conf], 1)
        y = np.where(rng.uniform(size=500) < conf, 0, 1)
        t90, t99 = tau_l2c(p, y, 0.90)[0], tau_l2c(p, y, 0.99)[0]
        self.assertTrue(t90 is not None and (t99 is None or t99 >= t90))

    def test_calib_con_y_sin_tau(self):
        self.assertNotIn("tau_l2c", json.loads(formato.calib({}, 0.7)))
        self.assertEqual(json.loads(formato.calib({}, 0.7, 0.3))["tau_l2c"], 0.3)


@unittest.skipUnless(encontrar_go() and REPO, "sin Go o sin repositorio")
class TestTrainConjunta(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        with open(self.d / "ej.jsonl", "w") as f:
            for t, e in ejemplos():
                f.write(json.dumps({"texto": t, "etiqueta": e}) + "\n")
        # L2 falso: el entrenador solo copia las secciones L2 y ESQUEMAS.
        (self.d / "l2.chispa").write_bytes(formato.escribir({formato.L2: b"onnx", formato.ESQUEMAS: b"esq"}))
        from model.l2.modelo import ModeloL2
        from model.l2.tests.falso import CodificadorFalso
        import torch
        torch.manual_seed(0)
        self.modelo_enc = (ModeloL2(), CodificadorFalso())

    def correr(self, salida, **kw):
        kw.setdefault("log", lambda m: None)
        return entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / salida, l2=str(self.d / "l2.chispa"), **kw)

    def test_conjunta_escribe_conj_y_sin_ella_el_fichero_no_cambia(self):
        sin = self.correr("sin.chispa")
        self.assertNotIn("CONJ", sin["secciones"])
        con = self.correr("con.chispa", conjunta=True, ckpt="falso", modelo_l2=self.modelo_enc)
        self.assertIn("CONJ", con["secciones"])
        self.assertEqual(con["conjunta"]["clases"], 2)
        a = formato.leer((self.d / "sin.chispa").read_bytes())
        b = formato.leer((self.d / "con.chispa").read_bytes())
        self.assertEqual(sorted(b), sorted([*a, formato.CONJ, formato.L0TF]))
        self.assertEqual(con["conjunta"]["l0tf"]["max_features"], None)
        for t in a:
            if t != formato.CALIB:  # CALIB lleva la validación de L0, que no cambia; se compara igualmente abajo
                self.assertEqual(a[t], b[t], t)
        self.assertEqual(a[formato.CALIB], b[formato.CALIB])
        self.assertLess(len(b[formato.CONJ]), 1 << 20)
        self.assertEqual(struct.unpack("<IIII", b[formato.L0TF][:16])[::3], (1, 1))  # versión 1, f32
        # La sección es la de esta pregunta: hash de pregunta y opciones ordenadas.
        self.assertIn(formato.hash_esquema(ESQ["pregunta"], sorted(ESQ["opciones"])), [b[formato.CONJ][8:40]])

    def test_pocas_filas_usa_el_tau_de_calib_y_avisa(self):
        avisos = []
        self.correr("poco.chispa", conjunta=True, ckpt="falso", modelo_l2=self.modelo_enc, log=avisos.append)
        self.assertTrue(any("τ de L2c de CALIB" in a for a in avisos), avisos)
        c = json.loads(formato.leer((self.d / "poco.chispa").read_bytes())[formato.CALIB])
        self.assertNotIn("tau_l2c", c)

    def test_con_filas_suficientes_escribe_tau_l2c_en_calib(self):
        rng = np.random.default_rng(1)
        o1, o2 = list(ESQ["opciones"])
        pal = {o1: ["rojo", "fuego", "cálido"], o2: ["azul", "mar", "frío"]}
        with open(self.d / "ej.jsonl", "w") as f:
            for i in range(400):
                e = (o1, o2)[i % 2]
                t = " ".join(rng.choice(pal[e], 2)) + f" {i % 7}" + (" " + rng.choice(pal[(o2, o1)[i % 2]]) if i % 5 == 0 else "")
                f.write(json.dumps({"texto": t, "etiqueta": e}) + "\n")
        logs = []
        inf = self.correr("mucho.chispa", conjunta=True, ckpt="falso", modelo_l2=self.modelo_enc, log=logs.append,
                          precision_objetivo=0.9)
        cj = inf["conjunta"]
        self.assertGreaterEqual(cj["filas_oof"], 200)
        self.assertEqual(cj["precision_objetivo"], 0.9)
        c = json.loads(formato.leer((self.d / "mucho.chispa").read_bytes())[formato.CALIB])
        if cj["tau_l2c"] is None:
            self.assertNotIn("tau_l2c", c)
        else:
            self.assertEqual(c["tau_l2c"], cj["tau_l2c"])
            self.assertGreaterEqual(cj["precision_oof"], 0.9)
            self.assertTrue(any("cobertura esperada" in m for m in logs), logs)

    def test_l0tf_podado_y_f16(self):
        con = self.correr("p.chispa", conjunta=True, ckpt="falso", modelo_l2=self.modelo_enc, l0tf_f16=True, l0tf_max_mb=0.002)
        inf = con["conjunta"]["l0tf"]
        self.assertTrue(inf["f16"])
        self.assertEqual(inf["max_features"], int(0.002e6 // (2 * 2)))  # 2 clases × 2 bytes
        self.assertEqual(inf["ngramas"], inf["max_features"])
        b = formato.leer((self.d / "p.chispa").read_bytes())[formato.L0TF]
        v, c, dt = struct.unpack("<III", b[4:16])
        self.assertEqual((v, c, dt), (inf["ngramas"], 2, 2))

    def test_conjunta_pide_checkpoint_y_l2(self):
        from chispa.cliente import ChispaError
        with self.assertRaisesRegex(ChispaError, "--ckpt"):
            self.correr("x.chispa", conjunta=True)
        with self.assertRaisesRegex(ChispaError, "L2"):
            entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / "x.chispa", conjunta=True, modelo_l2=self.modelo_enc,
                     log=lambda m: None)
        self.assertFalse((self.d / "x.chispa").exists())


if __name__ == "__main__":
    unittest.main()
