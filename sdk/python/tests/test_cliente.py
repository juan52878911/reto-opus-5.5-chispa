import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from chispa import Choice, Chispa, ChispaError, ErrorSolicitud, ErrorTransporte, Noul, Score


class Falso:
    """Servidor falso con el JSON del contrato (server/README.md); `fallos` = códigos a devolver antes de responder."""

    def __init__(self, fallos=()):
        self.fallos, self.peticiones = list(fallos), []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                self._json(200, {"status": "ok"})

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.peticiones.append(req)
                if outer.fallos:
                    return self._json(outer.fallos.pop(0), {"error": "boom"})
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
        self.f.fallos[:] = [503, 502]
        self.c.decidir("x", [Noul("n", "¿?")])
        nonces = {p["questions"][0]["nonce"] for p in self.f.peticiones}
        self.assertEqual(len(self.f.peticiones), 3)
        self.assertEqual(len(nonces), 1)
        self.assertEqual(len(next(iter(nonces))), 32)

    def test_sin_nonce_automatico(self):
        Chispa(self.f.url, nonce_auto=False).decidir("x", [Noul("n", "¿?")])
        self.assertNotIn("nonce", self.f.peticiones[0]["questions"][0])

    def test_reintentos_agotados(self):
        self.f.fallos[:] = [500] * 10
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
