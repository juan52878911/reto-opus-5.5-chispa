import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from chispa import formato
from chispa.cliente import ChispaError
from chispa.datos import cargar_ejemplos, cargar_esquema, validar
from chispa.train import GO_DIR, comandos_l2, encontrar_go, encontrar_repo, entrenar

ESQ = {"id": "urg", "pregunta": "¿Qué tan urgente es?", "tipo": "choice",
       "opciones": {"alta": "Requiere atención inmediata", "baja": "Puede esperar"}}
PAL = {"alta": "urgente ahora ya inmediato emergencia crítico", "baja": "luego cuando pueda tranquilo semana próxima"}


def ejemplos(n=40):
    return [(f"{PAL[c]} {i % 7} caso{i}", c) for c in ("alta", "baja") for i in range(n)]


class TestDatos(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)

    def esq(self, d, nombre="e.json"):
        (self.d / nombre).write_text(json.dumps(d))
        return self.d / nombre

    def test_csv_y_jsonl(self):
        (self.d / "a.csv").write_text("texto,etiqueta\n\"hola, qué tal\",alta\nadiós,baja\n", encoding="utf-8")
        (self.d / "b.jsonl").write_text('{"text": "hola", "label": "alta"}\n\n{"text": "chao", "label": "baja"}\n')
        self.assertEqual(cargar_ejemplos(self.d / "a.csv"), [("hola, qué tal", "alta"), ("adiós", "baja")])
        self.assertEqual(cargar_ejemplos(self.d / "b.jsonl"), [("hola", "alta"), ("chao", "baja")])

    def test_columna_que_falta(self):
        (self.d / "a.csv").write_text("x,y\n1,2\n")
        with self.assertRaisesRegex(ChispaError, "falta la columna"):
            cargar_ejemplos(self.d / "a.csv")

    def test_esquema_json_mapa_y_lista(self):
        q, _ = cargar_esquema(self.esq(ESQ))
        self.assertEqual([(o.id, o.description) for o in q.options], [("alta", "Requiere atención inmediata"), ("baja", "Puede esperar")])
        q, _ = cargar_esquema(self.esq(dict(ESQ, opciones=["a", {"id": "b", "descripcion": "bé"}])))
        self.assertEqual([(o.id, o.description) for o in q.options], [("a", ""), ("b", "bé")])

    def test_esquema_yaml(self):
        try:
            import yaml  # noqa: F401
        except ImportError:
            self.skipTest("sin PyYAML")
        (self.d / "e.yaml").write_text("id: urg\npregunta: ¿Urgente?\ntipo: noul\nlicencias: {x: mit}\n")
        q, extra = cargar_esquema(self.d / "e.yaml")
        self.assertEqual((q.kind, [o.id for o in q.options], extra["licencias"]), ("noul", ["false", "true"], {"x": "mit"}))

    def test_esquema_invalido(self):
        for d, msg in [(dict(ESQ, tipo="raro"), "tipo"), (dict(ESQ, opciones=["a"]), "≥ 2"), ({"id": "x"}, "pregunta"),
                       (dict(ESQ, tipo="noul", opciones=["a", "b"]), "false y true"),
                       ({"preguntas": [ESQ, dict(ESQ, id="otra")]}, "varias preguntas")]:
            with self.assertRaisesRegex(ChispaError, msg):
                cargar_esquema(self.esq(d))
        q, _ = cargar_esquema(self.esq({"preguntas": [ESQ, dict(ESQ, id="otra")]}), "otra")
        self.assertEqual(q.id, "otra")

    def test_validar_etiquetas(self):
        q, _ = cargar_esquema(self.esq(ESQ))
        with self.assertRaisesRegex(ChispaError, "no son opciones"):
            validar([("a", "alta"), ("b", "rara")], q)
        with self.assertRaisesRegex(ChispaError, "sin ningún ejemplo"):
            validar([("a", "alta")], q)


class TestFormato(unittest.TestCase):
    def test_crc32c_estandar(self):
        self.assertEqual(formato.crc32c(b"123456789"), 0xE3069283)

    def test_estructura(self):
        b = formato.escribir({formato.CALIB: b"{}", formato.META: b"abc"})
        self.assertEqual(b[:8], formato.MAGIA)
        self.assertEqual(int.from_bytes(b[16:24], "little"), len(b))
        self.assertEqual(len(b), 32 + 2 * 56 + 16 + 2)


class TestComandosL2(unittest.TestCase):
    def test_comandos(self):
        c = comandos_l2("ck", Path("/t/f.jsonl"), Path("/t"), python="py")
        self.assertEqual(c[0][:4], ["py", "-m", "model.l2.calibrar", "--ckpt"])
        self.assertEqual(c[1][2], "model.l2.exportar")
        self.assertIn("/t/l2.chispa", c[1])


class TestEntrenar(unittest.TestCase):
    """Sin L1 (el potion pesa 155 MB y no va a git): L0 + CALIB con el entrenador de Go; sin Go, el respaldo."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        with open(self.d / "ej.jsonl", "w") as f:
            for t, e in ejemplos():
                f.write(json.dumps({"texto": t, "etiqueta": e}) + "\n")

    def test_sin_go_deja_fuera_l0_y_lo_dice(self):
        logs = []
        inf = entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / "s.chispa", usar_go=False, log=logs.append)
        self.assertEqual(inf["secciones"], ["META", "CALIB"])
        self.assertIn("L0", inf["omitidas"])
        self.assertTrue(any("sin L0" in m for m in logs))
        self.assertTrue((self.d / "s.chispa").is_file())

    @unittest.skipUnless(encontrar_go() and encontrar_repo(), "sin Go o sin repositorio")
    def test_con_go(self):
        inf = entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / "s.chispa", log=lambda m: None)
        self.assertEqual(inf["secciones"], ["META", "L0", "CALIB"])
        self.assertGreater(inf["l0_valid_acc"], 0.9)
        self.assertIn("L1", inf["omitidas"])
        self.assertIn("L2", inf["omitidas"])

    @unittest.skipUnless(encontrar_go() and encontrar_repo(), "sin Go o sin repositorio")
    def test_l0_de_muchas_clases_cabe_en_el_tope(self):
        """151 clases sintéticas: con el tope por defecto (48 MB) los buckets bajan a 2^17; con 0,1 MB, a 2^8."""
        def pal(c, k):  # palabra inventada y distinta por clase y posición: solo letras
            return "".join(chr(97 + (c * 7 + k * 3 + i * (c % 11 + 1)) % 26) for i in range(5)) + "abcdefghij"[k % 10] * 2

        ops = ["c%d" % i for i in range(151)]
        (self.d / "e151.json").write_text(json.dumps({"id": "muchas", "pregunta": "¿Cuál?", "tipo": "choice", "opciones": ops}))
        with open(self.d / "e151.jsonl", "w") as f:
            for c in range(151):
                for j in range(10):
                    f.write(json.dumps({"texto": f"{pal(c, 0)} {pal(c, 1)} {pal(c, 2 + j % 3)} comun", "etiqueta": ops[c]}) + "\n")
        for mb, buckets in ((None, 1 << 17), (0.1, 1 << 8)):
            kw = {} if mb is None else {"l0_max_mb": mb}
            inf = entrenar(self.d / "e151.jsonl", self.d / "e151.json", self.d / "m.chispa", log=lambda m: None, **kw)
            self.assertEqual(inf["l0_buckets"], buckets)
            self.assertLessEqual(inf["l0_buckets"] * 151 * 2, (mb or 48) * 1e6)
            self.assertGreater(inf["l0_valid_acc"], 0.5 if mb is None else 0.0)

    @unittest.skipUnless(encontrar_go() and encontrar_repo(), "sin Go o sin repositorio")
    def test_el_cargador_de_go_abre_el_respaldo_python(self):
        """chispa3.Abrir + Verificar (CRC y sha256) aceptan lo que escribe formato.py; luego `evaluar` se queja de L0."""
        entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / "s.chispa", usar_go=False, log=lambda m: None)
        plan = {"salida": str(self.d / "s.chispa"), "prueba": str(self.d / "p.jsonl"),
                "pregunta": {"id": "urg", "texto": "¿?", "kind": "choice", "opciones": [{"id": "alta"}, {"id": "baja"}]}}
        (self.d / "p.jsonl").write_text('{"text": "a", "label": "alta"}\n')
        (self.d / "plan.json").write_text(json.dumps(plan))
        env = dict(os.environ, GOFLAGS="-mod=mod", GOPROXY="off")
        r = subprocess.run([encontrar_go(), "run", ".", "evaluar", str(self.d / "plan.json")], cwd=GO_DIR, env=env,
                           capture_output=True, text=True)
        self.assertIn("el modelo no tiene L0", r.stderr)

    @unittest.skipUnless(encontrar_go() and encontrar_repo(), "sin Go o sin repositorio")
    def test_etiqueta_desconocida_no_escribe(self):
        with open(self.d / "ej.jsonl", "a") as f:
            f.write(json.dumps({"texto": "x", "etiqueta": "rara"}) + "\n")
        with self.assertRaises(ChispaError):
            entrenar(self.d / "ej.jsonl", self.d / "e.json", self.d / "s.chispa", log=lambda m: None)
        self.assertFalse((self.d / "s.chispa").exists())


class TestModos(unittest.TestCase):
    """Zero-shot (sin ejemplos), few-shot (k por opción) y --conjunta con train escaso. Sin torch: L1 y L2 son bytes falsos."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d)
        (self.d / "e.json").write_text(json.dumps(ESQ))
        (self.d / "l1.bin").write_bytes(b"l1-falso")
        (self.d / "l2.chispa").write_bytes(formato.escribir({formato.L2: b"onnx", formato.ESQUEMAS: b"esq"}))

    def jsonl(self, k, nombre="ej.jsonl"):
        with open(self.d / nombre, "w") as f:
            for c in ("alta", "baja"):
                for i in range(k):
                    f.write(json.dumps({"texto": f"{PAL[c]} caso{i}", "etiqueta": c}) + "\n")
        return self.d / nombre

    def correr(self, ej, salida="s.chispa", **kw):
        kw.setdefault("log", lambda m: None)
        return entrenar(ej, self.d / "e.json", self.d / salida, **kw)

    def test_zero_shot_sin_ejemplos(self):
        logs = []
        inf = self.correr(None, l1=self.d / "l1.bin", l2=str(self.d / "l2.chispa"), log=logs.append)
        self.assertEqual(inf["modo"], "zero-shot")
        self.assertEqual(inf["secciones"], ["META", "L1", "L2", "ESQUEMAS", "CALIB"])
        self.assertIn("L0", inf["omitidas"])
        sec = formato.leer((self.d / "s.chispa").read_bytes())
        self.assertEqual((sec[formato.L1], sec[formato.L2], sec[formato.ESQUEMAS]), (b"l1-falso", b"onnx", b"esq"))
        self.assertNotIn(formato.L0, sec)
        calib = json.loads(sec[formato.CALIB])
        self.assertEqual((calib["tipos"], calib["tau_escalate"]), ({}, 0.6))
        self.assertTrue(any("sin calibrar" in m for m in logs))

    def test_zero_shot_solo_l1(self):
        inf = self.correr(None, l1=self.d / "l1.bin")
        self.assertEqual(inf["secciones"], ["META", "L1", "CALIB"])
        self.assertIn("L2", inf["omitidas"])

    def test_zero_shot_sin_ninguna_capa_o_con_conjunta_falla(self):
        with self.assertRaisesRegex(ChispaError, "--l1 o --l2"):
            self.correr(None)
        with self.assertRaisesRegex(ChispaError, "train etiquetado"):
            self.correr(None, l1=self.d / "l1.bin", conjunta=True)

    def test_zero_shot_l2_sin_esquemas(self):
        (self.d / "roto.chispa").write_bytes(formato.escribir({formato.L2: b"onnx"}))
        with self.assertRaisesRegex(ChispaError, "ESQUEMAS"):
            self.correr(None, l2=str(self.d / "roto.chispa"))

    @unittest.skipUnless(encontrar_go() and encontrar_repo(), "sin Go o sin repositorio")
    def test_few_shot_k1_y_k5(self):
        for k in (1, 5):
            logs = []
            inf = self.correr(self.jsonl(k), f"k{k}.chispa", l2=str(self.d / "l2.chispa"), log=logs.append)
            self.assertEqual(inf["secciones"], ["META", "L2", "ESQUEMAS", "CALIB"], k)
            self.assertIn("L0", inf["omitidas"])
            self.assertEqual(inf["n_valid"], 2 * k)
            self.assertTrue(any("few-shot" in m for m in logs), logs)
            self.assertNotIn(formato.L0, formato.leer((self.d / f"k{k}.chispa").read_bytes()))

    @unittest.skipUnless(encontrar_go() and encontrar_repo(), "sin Go o sin repositorio")
    def test_con_diez_por_opcion_sigue_entrenando_l0(self):
        inf = self.correr(self.jsonl(10))
        self.assertEqual(inf["secciones"], ["META", "L0", "CALIB"])

    @unittest.skipUnless(encontrar_go() and encontrar_repo(), "sin Go o sin repositorio")
    def test_conjunta_con_train_escaso_cae_a_few_shot(self):
        logs = []
        inf = self.correr(self.jsonl(5), "c.chispa", l2=str(self.d / "l2.chispa"), conjunta=True, log=logs.append)
        self.assertTrue(any("--conjunta necesita al menos 20" in m for m in logs), logs)
        self.assertNotIn("CONJ", inf["secciones"])
        self.assertNotIn("L0TF", inf["secciones"])
        self.assertEqual(inf["modo"], "few-shot")
        self.assertTrue((self.d / "c.chispa").is_file())


if __name__ == "__main__":
    unittest.main()
