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


if __name__ == "__main__":
    unittest.main()
