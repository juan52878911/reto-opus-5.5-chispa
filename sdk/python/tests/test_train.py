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

    def test_esquema_con_separadores(self):
        for c in "\x1d\x1e\x1f":
            for d in (dict(ESQ, pregunta="¿a" + c + "b?"), dict(ESQ, id="x" + c), dict(ESQ, opciones=["a" + c, "b"]),
                      dict(ESQ, opciones={"a": "d" + c, "b": ""})):
                with self.assertRaisesRegex(ChispaError, "U\\+001D–U\\+001F"):
                    cargar_esquema(self.esq(d))

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

    def test_perfil_servidor_por_defecto_sin_poda_por_esquema(self):
        e = comandos_l2("ck", Path("/t/f.jsonl"), Path("/t"), python="py")[1]
        self.assertEqual(e[e.index("--perfil") + 1], "servidor")
        self.assertNotIn("--vocab-ampliar", e)
        self.assertNotIn("--vocab-podado", e)

    def test_perfil_movil_amplia_el_vocabulario_con_el_esquema(self):
        e = comandos_l2("ck", Path("/t/f.jsonl"), Path("/t"), python="py", perfil="movil")[1]
        self.assertEqual(e[e.index("--perfil") + 1], "movil")
        self.assertEqual(e[e.index("--vocab-ampliar") + 1], "/t/f.jsonl")
        self.assertNotIn("--sin-poda", e)

    def test_perfil_movil_int8(self):
        e = comandos_l2("ck", Path("/t/f.jsonl"), Path("/t"), python="py", perfil="movil-int8")[1]
        self.assertEqual(e[e.index("--perfil") + 1], "movil-int8")
        self.assertEqual(e[e.index("--vocab-ampliar") + 1], "/t/f.jsonl")

    def _ckpt_sin_l2(self, calib_l2):
        """`entrenar` zero-shot con `--ckpt` y un exportador falso que escribe `calib_l2` (None = sin CALIB) en l2.chispa."""
        from unittest import mock
        d = Path(tempfile.mkdtemp())
        (d / "e.json").write_text(json.dumps({"id": "t", "pregunta": "q", "tipo": "choice", "opciones": [{"id": "a", "description": "A"}, {"id": "b", "description": "B"}]}))
        secs = {formato.L2: b"x", formato.ESQUEMAS: b"y"}
        if calib_l2 is not None:
            secs[formato.CALIB] = calib_l2
        logs = []

        def falso(cmd, **kw):
            if cmd[2] == "model.l2.exportar":
                Path(cmd[cmd.index("--salida") + 1]).write_bytes(formato.escribir(secs))
            return mock.Mock(returncode=0, stderr="")
        with mock.patch("chispa.train.subprocess.run", falso):
            entrenar(None, d / "e.json", d / "o.chispa", ckpt="ck", repo=str(d), log=logs.append)
        return json.loads(formato.leer((d / "o.chispa").read_bytes())[formato.CALIB]), logs

    def test_ckpt_copia_la_calib_entera_del_l2_generado(self):
        tipos = {"choice": {"T": 0.7, "a": 1.0, "b": 0.0, "theta": 0.5}, "noul": {"T": 1.0, "a": 1.0, "b": 0.0},
                 "score4": {"T": 1.0}, "score5": {"T": 1.1}, "score4#0": {"T": 1.2}, "score4#3": {"T": 1.3}, "score5#4": {"T": 1.4},
                 "multi_l2@choice": {"T": 0.9}}
        c, logs = self._ckpt_sin_l2(formato.calib(tipos, 0.35, tau_l2c=0.5))
        self.assertEqual(c["tipos_l2"], tipos)
        self.assertEqual((c["tau_escalate_l2"], c["tau_l2c"]), (0.35, 0.5))
        self.assertEqual((c["tipos"], c["tau_escalate"]), ({}, 0.6))  # la CALIB de L1 se conserva
        self.assertEqual([m for m in logs if "AVISO" in m and "no trae CALIB" in m], [])

    def test_ckpt_sin_calib_en_el_l2_generado_avisa(self):
        c, logs = self._ckpt_sin_l2(None)
        self.assertNotIn("tipos_l2", c)
        self.assertEqual((c["tipos"], c["tau_escalate"]), ({}, 0.6))
        self.assertTrue(any("AVISO" in m and "no trae CALIB" in m for m in logs), logs)

    def test_perfil_desconocido(self):
        with self.assertRaises(ChispaError):
            comandos_l2("ck", Path("/t/f.jsonl"), Path("/t"), perfil="gpu")

    def test_calib_de_l2_pasa_a_tipos_l2(self):
        """La CALIB de L1 del `.chispa` final es la del esquema (zero-shot: sin calibrar, τ 0,6); la que escribe el exportador en l2.chispa
        pasa a `tipos_l2`, `tau_escalate_l2` y `tau_l2c`, que son los que leen L2 y L2c."""
        from unittest import mock
        from chispa import formato
        d = Path(tempfile.mkdtemp())
        (d / "e.json").write_text(json.dumps({"id": "t", "pregunta": "q", "tipo": "choice", "opciones": [{"id": "a", "description": "A"}, {"id": "b", "description": "B"}]}))
        l2 = formato.escribir({formato.L2: b"x", formato.ESQUEMAS: b"y", formato.CALIB: formato.calib({"choice": {"T": 9.0}, "score3": {"T": 1.0}}, 0.123, tau_l2c=0.31)})
        llamadas = []

        def falso(cmd, **kw):
            llamadas.append(cmd)
            if cmd[2] == "model.l2.exportar":
                Path(cmd[cmd.index("--salida") + 1]).write_bytes(l2)
            return mock.Mock(returncode=0, stderr="")
        with mock.patch("chispa.train.subprocess.run", falso):
            entrenar(None, d / "e.json", d / "o.chispa", ckpt="ck", repo=str(d), log=lambda m: None, perfil="movil")
        self.assertEqual(llamadas[0][2], "model.l2.exportar")
        self.assertIn("movil", llamadas[0])
        secs = formato.leer((d / "o.chispa").read_bytes())
        self.assertEqual(json.loads(secs[formato.CALIB]), json.loads(formato.calib(
            {}, 0.6, tau_l2c=0.31, tipos_l2={"choice": {"T": 9.0}, "score3": {"T": 1.0}}, tau_escalate_l2=0.123)))
        self.assertEqual(secs[formato.L2], b"x")

    def test_calib_de_l2_con_l2_y_sin_calib(self):
        """`--l2 x.chispa` deja en tipos_l2/tau_escalate_l2/tau_l2c exactamente lo de x; si x no trae CALIB, no añade nada."""
        d = Path(tempfile.mkdtemp())
        (d / "e.json").write_text(json.dumps({"id": "t", "pregunta": "q", "tipo": "choice", "opciones": [{"id": "a"}, {"id": "b"}]}))
        tipos = {"choice": {"T": 0.7, "a": 1.0, "b": 0.0, "theta": 0.5}, "multi_l2@ab": {"T": 1.0, "a": 2.0, "b": -1.0, "theta": 0.4}}
        for nombre, calib in (("con", formato.calib(tipos, 0.35, tau_l2c=0.5)), ("sin_l2c", formato.calib(tipos, 0.35)), ("sin", None)):
            secs = {formato.L2: b"x", formato.ESQUEMAS: b"y"}
            if calib:
                secs[formato.CALIB] = calib
            (d / f"{nombre}.chispa").write_bytes(formato.escribir(secs))
            entrenar(None, d / "e.json", d / f"{nombre}.out", l2=str(d / f"{nombre}.chispa"), log=lambda m: None)
            c = json.loads(formato.leer((d / f"{nombre}.out").read_bytes())[formato.CALIB])
            self.assertEqual((c["tipos"], c["tau_escalate"]), ({}, 0.6))  # lo de L1 no cambia
            if nombre == "sin":
                self.assertEqual(set(c), {"tipos", "tau_escalate"})
                continue
            self.assertEqual((c["tipos_l2"], c["tau_escalate_l2"]), (tipos, 0.35))
            self.assertEqual(c.get("tau_l2c"), 0.5 if nombre == "con" else None)


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
    def test_few_shot_copia_la_calib_de_l2_a_tipos_l2(self):
        """Con el entrenador de Go, `--l2 x.chispa` deja en tipos_l2/tau_escalate_l2/tau_l2c lo de x, y tipos/tau_escalate son los de siempre."""
        tipos = {"choice": {"T": 0.7, "a": 1.0, "b": 0.0, "theta": 0.5}, "score3#1": {"T": 1.0, "a": 0.5, "b": 0.0, "theta": 0.5}}
        sec = formato.leer((self.d / "l2.chispa").read_bytes())
        sec[formato.CALIB] = formato.calib(tipos, 0.35, tau_l2c=0.5)
        (self.d / "l2c.chispa").write_bytes(formato.escribir(sec))
        self.correr(self.jsonl(5), "base.chispa", l2=str(self.d / "l2.chispa"))
        self.correr(self.jsonl(5), "con.chispa", l2=str(self.d / "l2c.chispa"))
        base = json.loads(formato.leer((self.d / "base.chispa").read_bytes())[formato.CALIB])
        con = json.loads(formato.leer((self.d / "con.chispa").read_bytes())[formato.CALIB])
        self.assertEqual((con["tipos"], con["tau_escalate"]), (base["tipos"], base["tau_escalate"]))
        self.assertEqual((con["tipos_l2"], con["tau_escalate_l2"], con["tau_l2c"]), (tipos, 0.35, 0.5))

    @unittest.skipUnless(encontrar_go() and encontrar_repo(), "sin Go o sin repositorio")
    def test_ckpt_con_l2_copia_la_calib_de_l2_entera(self):
        """Con `--ckpt` y `--l2`, tipos_l2/tau_escalate_l2 son los del `--l2` (noul, score4, score5…), no solo el tipo del esquema calibrado."""
        from unittest import mock
        repo = Path(__file__).resolve().parents[3]
        fuente = formato.leer((repo / "server/decide/testdata/calib-score.chispa").read_bytes())
        cf = json.loads(fuente[formato.CALIB])
        l2 = {formato.L2: b"onnx", formato.ESQUEMAS: b"esq", formato.CALIB: fuente[formato.CALIB]}
        (self.d / "fuente.chispa").write_bytes(formato.escribir(l2))
        solo = formato.escribir({**l2, formato.CALIB: formato.calib({"choice": {"T": 9.0}}, 0.123)})
        real, logs, con_l2 = subprocess.run, [], True

        def falso(cmd, **kw):
            if cmd[1:3] != ["-m", cmd[2]] or not cmd[2].startswith("model.l2."):
                return real(cmd, **kw)
            if cmd[2] == "model.l2.exportar":
                Path(cmd[cmd.index("--salida") + 1]).write_bytes(solo if con_l2 else formato.escribir(l2))
            return mock.Mock(returncode=0, stderr="")
        with mock.patch("chispa.train.subprocess.run", falso):
            self.correr(self.jsonl(5), "ck.chispa", ckpt="ck", repo=str(repo), l2=str(self.d / "fuente.chispa"), log=logs.append)
            con_l2, logs[:] = False, []
            self.correr(self.jsonl(5), "sinl2.chispa", ckpt="ck", repo=str(repo), log=logs.append)
        c = json.loads(formato.leer((self.d / "ck.chispa").read_bytes())[formato.CALIB])
        self.assertEqual(c["tipos_l2"], cf["tipos"])
        self.assertEqual(c["tau_escalate_l2"], cf["tau_escalate"])
        for k in ("noul", "score4", "score5"):
            self.assertIn(k, c["tipos_l2"])
        c = json.loads(formato.leer((self.d / "sinl2.chispa").read_bytes())[formato.CALIB])
        self.assertEqual((c["tipos_l2"], c["tau_escalate_l2"]), (cf["tipos"], cf["tau_escalate"]))
        self.assertEqual([m for m in logs if "AVISO" in m and "no trae CALIB" in m], [])

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


class TestCalibL2YaEntrenada(unittest.TestCase):
    def test_calib_de_l2_prefiere_tipos_l2(self):
        from chispa import formato
        from chispa.train import calib_de_l2
        c = formato.calib({"choice": {"T": 0.05}}, 0.9, tipos_l2={"choice": {"T": 0.7}}, tau_escalate_l2=0.6)
        r = calib_de_l2({formato.CALIB: c})
        self.assertEqual(r["tipos_l2"], {"choice": {"T": 0.7}})
        self.assertEqual(r["tau_escalate_l2"], 0.6)

    def test_calib_de_l2_casos_cruzados_con_go(self):
        """Mismos casos que `TestCopiarCalibL2CasosCruzadosConPython` (entrenador Go): nulos y ausentes dan lo mismo."""
        from chispa import formato
        from chispa.train import calib_de_l2
        casos = json.loads((Path(__file__).parent / "calib_l2_casos.json").read_text())
        for k in casos:
            r = calib_de_l2({formato.CALIB: json.dumps(k["calib"]).encode()})
            self.assertEqual(r, k["esperado"], k["nombre"])

    def test_aviso_l2_sin_calib(self):
        from chispa import formato
        d = Path(tempfile.mkdtemp())
        (d / "e.json").write_text(json.dumps({"id": "t", "pregunta": "q", "tipo": "choice", "opciones": [{"id": "a"}, {"id": "b"}]}))
        (d / "l2.chispa").write_bytes(formato.escribir({formato.L2: b"x", formato.ESQUEMAS: b"y"}))
        msgs = []
        entrenar(None, d / "e.json", d / "o.chispa", l2=str(d / "l2.chispa"), log=msgs.append)
        self.assertTrue(any("--l2 sin CALIB" in m for m in msgs))
