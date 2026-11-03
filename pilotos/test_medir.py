"""Tests de medir.py contra un servidor falso en proceso (sin Go). Corre con: python3 -m unittest discover -s pilotos -p 'test_medir.py'
o, desde pilotos/, `python3 -m unittest test_medir`."""
import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import medir

# estado -> (answer, probs, layer, escalate, reason)
RESPUESTAS = {
    "pago": ("reclamo", {"peticion": 0.02, "queja": 0.03, "reclamo": 0.95}, "L0", False, ""),
    "trato": ("queja", {"peticion": 0.1, "queja": 0.8, "reclamo": 0.1}, "L1", False, ""),
    "cita": ("peticion", {"peticion": 0.9, "queja": 0.05, "reclamo": 0.05}, "L0", False, ""),
    "confuso": ("queja", {"peticion": 0.3, "queja": 0.4, "reclamo": 0.3}, "escalar", True, "baja_confianza"),
    "malo": ("peticion", {"peticion": 0.85, "queja": 0.1, "reclamo": 0.05}, "L2", False, ""),   # se equivoca
}


class Falso(BaseHTTPRequestHandler):
    vistas = []
    fallos_503 = 0

    def log_message(self, *a):
        pass

    def _json(self, codigo, obj, extra=None):
        b = json.dumps(obj).encode()
        self.send_response(codigo)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Falso.vistas.append((dict(self.headers), cuerpo))
        if self.path != "/v1/decide":
            return self._json(404, {"error": {"code": "not_found", "message": "x"}})
        if os.environ.get("FALSO_CLAVE") and self.headers.get("Authorization") != "Bearer " + os.environ["FALSO_CLAVE"]:
            return self._json(401, {"error": {"code": "unauthorized", "message": "clave"}})
        estado, q = cuerpo["state"], cuerpo["questions"][0]
        if estado == "invalido":
            return self._json(400, {"error": {"code": "invalid_options", "message": "opciones"}})
        if estado == "intermitente" and Falso.fallos_503 > 0:
            Falso.fallos_503 -= 1
            return self._json(503, {"error": {"code": "overloaded", "message": "x"}}, {"Retry-After": "0"})
        a, probs, capa, esc, motivo = RESPUESTAS.get(estado.split()[0], RESPUESTAS["cita"])
        r = {"id": q["id"], "kind": q["kind"], "answer": a, "probs": probs, "layer": capa, "escalate": esc, "ms": 0.5}
        if esc:
            r["escalate_reason"] = motivo
        self._json(200, {"results": [r]})


def caso(estado, gold, **kw):
    return {"id": estado, "state": estado, "question": "¿Qué tipo?", "kind": "choice",
            "options": [{"id": "peticion"}, {"id": "queja"}, {"id": "reclamo"}], "gold": gold, **kw}


class ConServidor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
        cls.url = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        Falso.vistas.clear()
        Falso.fallos_503 = 0
        os.environ.pop("FALSO_CLAVE", None)

    def escribir(self, casos):
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(d, ignore_errors=True))
        p = os.path.join(d, "casos.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for c in casos:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        return p, d

    def test_metricas_con_cifras_a_mano(self):
        # 6 casos: pago ok (L0), trato ok (L1), cita ok (L0), confuso escalado (mejor resp. queja = gold), malo mal (L2), cita mal (gold queja)
        casos = [caso("pago 1", "reclamo"), caso("trato 1", "queja"), caso("cita 1", "peticion"),
                 caso("confuso 1", "queja"), caso("malo 1", "queja"), caso("cita 2", "queja")]
        res, dur = medir.correr(self.url, casos, concurrencia=3)
        m = medir.metricas(res, 0.95, dur, precio_hora=0.2)
        self.assertEqual((m["n_casos"], m["n_medidos"], m["errores"]), (6, 6, 0))
        self.assertAlmostEqual(m["exactitud"], 4 / 6)                 # el escalado acierta como mejor respuesta
        self.assertAlmostEqual(m["exactitud_escala_es_fallo"], 3 / 6)
        self.assertAlmostEqual(m["escalado"], 1 / 6)
        self.assertAlmostEqual(m["precision_de_lo_contestado"], 3 / 5)
        self.assertEqual({c: d["n"] for c, d in m["por_capa"].items()}, {"L0": 3, "L1": 1, "L2": 1, "escalar": 1})
        self.assertEqual(m["escalados_por_motivo"], {"baja_confianza": 1})
        # F1 mejor respuesta: reclamo 1.0; queja tp2 fp0 fn2... (trato, confuso ok; malo y cita2 fallan) -> 2*2/(4+0+2)=2/3;
        # peticion tp1 fp2 fn0 -> 2/(2+2)=0.5; macro = (1 + 2/3 + 0.5)/3
        self.assertAlmostEqual(m["f1_macro_mejor_respuesta"], (1 + 2 / 3 + 0.5) / 3)
        # escala = fallo: queja tp1 fp0 fn3 -> 2/(2+3)=0.4; el resto igual
        self.assertAlmostEqual(m["f1_macro_escala_es_fallo"], (1 + 0.4 + 0.5) / 3)
        self.assertEqual(m["confusiones"][0], {"gold": "queja", "pred": "peticion", "n": 2})
        self.assertEqual(m["latencia_servidor_ms"]["p50"], 0.5)
        self.assertGreater(m["latencia_cliente_ms"]["p99"], 0)
        self.assertGreater(m["decisiones_por_s"], 0)
        self.assertGreater(m["coste_por_1000"], 0)
        self.assertEqual(m["por_opcion"], {"peticion": 1, "queja": 4, "reclamo": 1})

    def test_tabla_markdown(self):
        res, dur = medir.correr(self.url, [caso("pago 1", "reclamo"), caso("confuso 1", "queja")])
        md = medir.tabla_markdown(medir.metricas(res, 0.95, dur))
        for s in ("| Exactitud (mejor respuesta) | 1,000 |", "| Tasa de escalado | 50,0 % |", "| L0 | 1 |", "baja_confianza",
                  "p50 / p95 / p99", "| queja | 1 |"):
            self.assertIn(s, md)

    def test_clave_por_entorno_y_cabecera(self):
        os.environ["FALSO_CLAVE"] = "secreta"
        p, d = self.escribir([caso("pago 1", "reclamo"), caso("cita 1", "peticion")])
        os.environ["MI_CLAVE"] = "secreta"
        self.addCleanup(os.environ.pop, "MI_CLAVE", None)
        out = os.path.join(d, "inf")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(medir.main(["--url", self.url, "--casos", p, "--clave-env", "MI_CLAVE", "--salida", out]), 0)
        self.assertTrue(all(h.get("Authorization") == "Bearer secreta" for h, _ in Falso.vistas))
        self.assertEqual(json.load(open(out + ".json", encoding="utf-8"))["n_medidos"], 2)
        self.assertIn("Exactitud", open(out + ".md", encoding="utf-8").read())

    def test_clave_mala_detiene_en_el_primer_caso(self):
        os.environ["FALSO_CLAVE"] = "secreta"
        p, _ = self.escribir([caso("pago %d" % i, "reclamo") for i in range(5)])
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(medir.main(["--url", self.url, "--casos", p]), 2)
        self.assertIn("unauthorized", err.getvalue())
        self.assertEqual(len(Falso.vistas), 1)            # no mandó el resto

    def test_error_de_un_caso_no_detiene_y_se_cuenta(self):
        res, dur = medir.correr(self.url, [caso("pago 1", "reclamo"), caso("invalido", "queja"), caso("cita 1", "peticion")])
        m = medir.metricas(res, 0.95, dur)
        self.assertEqual((m["n_casos"], m["n_medidos"], m["errores"]), (3, 2, 1))
        self.assertIn("invalid_options", list(m["errores_por_causa"])[0])

    def test_reintenta_503_no_fatal(self):
        Falso.fallos_503 = 1
        res, _ = medir.correr(self.url, [caso("intermitente", "peticion")], reintentos=2)
        self.assertIsNotNone(res[0][1])
        self.assertEqual(len(Falso.vistas), 2)

    def test_servidor_caido(self):
        res, _ = medir.correr("http://127.0.0.1:1", [caso("pago 1", "reclamo")], reintentos=0, timeout=1)
        self.assertIsNone(res[0][1])
        self.assertIn("URLError", str(res[0][2]))
        self.assertEqual(medir.metricas(res)["n_medidos"], 0)
        self.assertIn("Sin casos medidos", medir.tabla_markdown(medir.metricas(res)))

    def test_peticion_lleva_esquema_del_caso(self):
        medir.correr(self.url, [caso("pago 1", "reclamo")])
        q = Falso.vistas[0][1]["questions"][0]
        self.assertEqual((q["question"], q["kind"], [o["id"] for o in q["options"]]), ("¿Qué tipo?", "choice", ["peticion", "queja", "reclamo"]))

    def test_defaults_de_linea_de_comandos(self):
        p, d = self.escribir([{"state": "pago 1", "gold": "reclamo"}])
        with redirect_stdout(io.StringIO()) as o, redirect_stderr(io.StringIO()):
            rc = medir.main(["--url", self.url, "--casos", p, "--pregunta", "¿Qué?", "--opciones", "peticion", "queja", "reclamo"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(o.getvalue())["exactitud"], 1.0)


class SinServidor(unittest.TestCase):
    def test_percentil(self):
        self.assertEqual(medir.percentil(list(range(1, 101)), 50), 50)
        self.assertEqual(medir.percentil(list(range(1, 101)), 95), 95)
        self.assertEqual(medir.percentil(list(range(1, 101)), 99), 99)
        self.assertEqual(medir.percentil([7], 99), 7)
        self.assertIsNone(medir.percentil([], 50))

    def test_f1_macro(self):
        self.assertEqual(medir.f1_macro(["a", "b"], ["a", "b"]), 1.0)
        self.assertEqual(medir.f1_macro(["a", "b"], ["", ""]), 0.0)

    def test_cobertura_a_precision(self):
        conf = [0.9, 0.8, 0.7, 0.6, 0.5]
        # aciertos en las 3 más confiadas, fallos en las 2 últimas: precisión 1.0 hasta k=3, luego baja
        self.assertEqual(medir.cobertura_a_precision(conf, [1, 1, 1, 0, 0], 0.95), (0.6, 0.7))
        self.assertEqual(medir.cobertura_a_precision(conf, [0, 1, 1, 1, 1], 0.95), (0.0, None))
        # empates: un umbral no separa a los iguales
        self.assertEqual(medir.cobertura_a_precision([0.9, 0.9], [1, 0], 0.95), (0.0, None))

    def test_leer_casos_valida(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "c.jsonl")

        def escribir(txt):
            with open(p, "w") as f:
                f.write(txt + "\n")
        escribir(json.dumps({"state": "x", "question": "q", "options": ["a", "b"], "gold": "c"}))
        with self.assertRaises(ValueError):
            medir.leer_casos(p)
        escribir("{no es json}")
        with self.assertRaises(ValueError):
            medir.leer_casos(p)
        escribir(json.dumps({"state": "x", "question": "q", "kind": "noul", "options": ["true", "false"], "gold": True}))
        self.assertEqual(medir.leer_casos(p)[0]["gold"], "true")


if __name__ == "__main__":
    unittest.main()
