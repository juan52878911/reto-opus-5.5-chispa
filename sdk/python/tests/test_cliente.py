import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from chispa import Choice, Chispa, ChispaError, ErrorSolicitud, ErrorTransporte, Noul, Score


class Falso:
    """Servidor falso con el JSON del contrato (server/README.md); `fallos` = códigos a devolver antes de responder."""

    def __init__(self, fallos=()):
        self.fallos, self.peticiones, self.retry_after, self.cuerpo_error = list(fallos), [], None, "boom"
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                if code in (503, 504) and outer.retry_after is not None:
                    self.send_header("Retry-After", outer.retry_after)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                self._json(200, {"status": "ok"})

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.peticiones.append(req)
                if outer.fallos:
                    return self._json(outer.fallos.pop(0), {"error": outer.cuerpo_error})
                qs = req["questions"]
                if any(q["kind"] == "raro" for q in qs):
                    return self._json(400, {"error": 'questions[0].kind: "raro" no válido (choice, score o noul)'})
                res = []
                for q in qs:
                    ops = [o["id"] for o in q.get("options", [])] or ["false", "true"]
                    r = {"id": q["id"], "kind": q["kind"], "answer": ops[0], "probs": {ops[0]: 0.9, ops[1]: 0.1},
                         "layer": "L0", "escalate": False, "ms": 0.012}
                    if "nonce" in q:
                        r["nonce"] = q["nonce"]
                    res.append(r)
                self._json(200, {"results": res})

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def cerrar(self):
        self.srv.shutdown()
        self.srv.server_close()


class TestCliente(unittest.TestCase):
    def setUp(self):
        self.f = Falso()
        self.addCleanup(self.f.cerrar)
        self.c = Chispa(self.f.url, dormir=lambda s: None)

    def test_contrato_de_la_peticion(self):
        q = Choice("u1", "¿Qué tan urgente es?", [("alta", "Requiere atención inmediata"), "baja"], nonce="abc-1")
        r = self.c.decidir("texto", [q])[0]
        self.assertEqual(self.f.peticiones[0], {"state": "texto", "questions": [
            {"id": "u1", "question": "¿Qué tan urgente es?", "kind": "choice",
             "options": [{"id": "alta", "description": "Requiere atención inmediata"}, {"id": "baja"}], "nonce": "abc-1"}]})
        self.assertEqual((r.id, r.answer, r.probs, r.layer, r.escalate, r.nonce), ("u1", "alta", {"alta": 0.9, "baja": 0.1}, "L0", False, "abc-1"))

    def test_tres_tipos_en_orden(self):
        rs = self.c.decidir("x", [Noul("n", "¿Es spam?"), Score("s", "¿Cuánto?", 3), Choice("c", "¿?", ["a", "b"])])
        self.assertEqual([r.kind for r in rs], ["noul", "score", "choice"])
        qs = self.f.peticiones[0]["questions"]
        self.assertNotIn("options", qs[0])
        self.assertEqual([o["id"] for o in qs[1]["options"]], ["1", "2", "3"])
        self.assertEqual(rs[0].verdadero, False)
        self.assertEqual(rs[1].nivel, 1)

    def test_nonce_automatico_estable_entre_reintentos(self):
        self.f.fallos[:] = [503, 503]
        self.c.decidir("x", [Noul("n", "¿?")])
        nonces = {p["questions"][0]["nonce"] for p in self.f.peticiones}
        self.assertEqual(len(self.f.peticiones), 3)
        self.assertEqual(len(nonces), 1)
        self.assertEqual(len(next(iter(nonces))), 32)

    def test_429_500_502_no_se_reintentan(self):
        for codigo in (429, 500, 502):
            with self.subTest(codigo=codigo):
                self.f.peticiones.clear()
                self.f.fallos[:] = [codigo, codigo]
                with self.assertRaises(ErrorSolicitud) as cm:
                    self.c.decidir("x", [Noul("n", "¿?")])
                self.assertEqual(cm.exception.status, codigo)
                self.assertEqual(len(self.f.peticiones), 1)

    def test_timeout_propio_no_se_reintenta_y_el_defecto_supera_los_30s_del_servidor(self):
        self.assertGreater(Chispa(self.f.url).timeout, 30.0)
        f = Falso()
        self.addCleanup(f.cerrar)
        orig = f.srv.RequestHandlerClass.do_POST

        def lento(h):
            time.sleep(1.0)
            try:
                orig(h)
            except OSError:
                pass
        f.srv.RequestHandlerClass.do_POST = lento
        with self.assertRaises(ErrorTransporte):
            Chispa(f.url, timeout=0.3, dormir=lambda s: None).decidir("x", [Noul("n", "¿?")])
        time.sleep(1.2)
        self.assertEqual(len(f.peticiones), 1)

    def test_nonce_vacio_se_trata_como_ausente(self):
        self.c.decidir("x", [Noul("n", "¿?", nonce="")])
        self.assertEqual(len(self.f.peticiones[0]["questions"][0]["nonce"]), 32)

    def test_503_de_proxy_sin_retry_after_se_reintenta_con_backoff(self):
        self.f.fallos[:] = [503, 503]
        esperas = []
        Chispa(self.f.url, espera=0.1, dormir=esperas.append).decidir("x", [Noul("n", "¿?")])
        self.assertEqual(len(self.f.peticiones), 3)
        self.assertEqual(esperas, [0.1, 0.2])

    def test_503_timeout_del_servidor_no_se_reintenta_aunque_traiga_retry_after(self):
        self.f.fallos[:] = [503, 503]
        self.f.retry_after = "5"
        self.f.cuerpo_error = {"code": "timeout", "message": "la petición superó el tiempo máximo"}
        esperas = []
        with self.assertRaises(ErrorSolicitud) as cm:
            Chispa(self.f.url, dormir=esperas.append).decidir("x", [Noul("n", "¿?")])
        self.assertEqual((cm.exception.status, cm.exception.codigo), (503, "timeout"))
        self.assertEqual(len(self.f.peticiones), 1)
        self.assertEqual(esperas, [])

    def test_504_no_se_reintenta(self):
        self.f.fallos[:] = [504, 504]
        with self.assertRaises(ErrorSolicitud):
            self.c.decidir("x", [Noul("n", "¿?")])
        self.assertEqual(len(self.f.peticiones), 1)

    def test_503_retry_after_se_topa_a_30s(self):
        self.f.fallos[:] = [503]
        self.f.retry_after = "999"
        esperas = []
        Chispa(self.f.url, espera=0.1, dormir=esperas.append).decidir("x", [Noul("n", "¿?")])
        self.assertEqual(esperas, [30.0])

    def test_503_con_retry_after_se_reintenta_y_lo_respeta(self):
        self.f.fallos[:] = [503]
        self.f.retry_after = "2"
        esperas = []
        Chispa(self.f.url, espera=0.1, dormir=esperas.append).decidir("x", [Noul("n", "¿?")])
        self.assertEqual(len(self.f.peticiones), 2)
        self.assertEqual(esperas, [2.0])

    def test_sin_nonce_automatico(self):
        Chispa(self.f.url, nonce_auto=False).decidir("x", [Noul("n", "¿?")])
        self.assertNotIn("nonce", self.f.peticiones[0]["questions"][0])

    def test_reintentos_agotados(self):
        self.f.fallos[:] = [503] * 10
        esperas = []
        c = Chispa(self.f.url, reintentos=2, espera=0.1, dormir=esperas.append)
        with self.assertRaises(ErrorTransporte):
            c.decidir("x", [Noul("n", "¿?")])
        self.assertEqual(len(self.f.peticiones), 3)
        self.assertEqual(esperas, [0.1, 0.2])

    def test_400_no_se_reintenta(self):
        from chispa.tipos import Pregunta
        with self.assertRaises(ErrorSolicitud) as cm:
            self.c.decidir("x", [Pregunta("q", "¿?", "raro")])
        self.assertEqual(cm.exception.status, 400)
        self.assertIn("kind", cm.exception.mensaje)
        self.assertEqual(len(self.f.peticiones), 1)

    def test_error_tipado_y_formato_viejo(self):
        from unittest import mock
        import io
        import urllib.error

        def http(cuerpo):
            return urllib.error.HTTPError("http://x", 400, "Bad", {}, io.BytesIO(cuerpo.encode()))
        c = Chispa("http://x", reintentos=0)
        tipado = '{"error":{"code":"bad_question","message":"opciones repetidas","question_id":"q1"}}'
        with mock.patch("urllib.request.urlopen", side_effect=http(tipado)):
            with self.assertRaises(ErrorSolicitud) as cm:
                c.decidir("x", [Noul("n", "¿?")])
        e = cm.exception
        self.assertEqual((e.status, e.codigo, e.mensaje, e.question_id), (400, "bad_question", "opciones repetidas", "q1"))
        self.assertIn("opciones repetidas", str(e))
        with mock.patch("urllib.request.urlopen", side_effect=http('{"error":"texto viejo"}')):
            with self.assertRaises(ErrorSolicitud) as cm:
                c.decidir("x", [Noul("n", "¿?")])
        e = cm.exception
        self.assertEqual((e.mensaje, e.codigo, e.question_id), ("texto viejo", "", None))
        with mock.patch("urllib.request.urlopen", side_effect=http("no json")):
            with self.assertRaises(ErrorSolicitud) as cm:
                c.decidir("x", [Noul("n", "¿?")])
        self.assertEqual(cm.exception.mensaje, "no json")
        self.assertEqual(ErrorSolicitud(400, {"code": "c", "message": "m"}).mensaje, "m")

    def test_servidor_caido(self):
        url = self.f.url
        self.f.cerrar()
        with self.assertRaises(ErrorTransporte):
            Chispa(url, reintentos=1, dormir=lambda s: None).decidir("x", [Noul("n", "¿?")])

    def test_validacion_local(self):
        with self.assertRaises(ValueError):
            Choice("c", "¿?", ["a"])
        with self.assertRaises(ValueError):
            Choice("c", "¿?", ["a", "a"])
        with self.assertRaises(ValueError):
            self.c.decidir("x", [Noul("n", "a"), Noul("n", "b")])
        with self.assertRaises(ValueError):
            self.c.decidir("x", [])
        self.assertTrue(issubclass(ErrorSolicitud, ChispaError))

    def test_salud(self):
        self.assertTrue(self.c.salud())


if __name__ == "__main__":
    unittest.main()
