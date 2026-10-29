import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from chispa import ChispaError
from chispa.cli import main
from chispa.evaluar import evaluar, barrido

# texto → (respuesta, confianza, capa, escala) por esquema
CHOICE = {"hola": ("a", 0.95, "L0", False), "adios": ("b", 0.9, "L1", False), "dudo": ("a", 0.6, "escalar", True),
          "mal": ("a", 0.8, "L1", False)}  # "mal" tiene etiqueta b: error de la cascada


class Servidor:
    def __init__(self, tabla, errores=None):
        self.tabla, self.errores, self.n = tabla, errores or {}, 0
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.n += 1
                q = req["questions"][0]
                if req["state"] in outer.errores:
                    code, err = outer.errores[req["state"]]
                    b = json.dumps({"error": err}).encode()
                    self.send_response(code)
                else:
                    ans, c, capa, esc = outer.tabla[req["state"]]
                    ops = [o["id"] for o in q.get("options", [])] or ["false", "true"]
                    probs = {o: (1 - c) / (len(ops) - 1) for o in ops}
                    probs[ans] = c
                    b = json.dumps({"results": [{"id": q["id"], "kind": q["kind"], "answer": "" if esc else ans, "probs": probs,
                                                 "layer": capa, "escalate": esc, "ms": 0.5}]}).encode()
                    self.send_response(200)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def cerrar(self):
        self.srv.shutdown()
        self.srv.server_close()


class TestEvaluar(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)

    def f(self, nombre, txt):
        p = os.path.join(self.d.name, nombre)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(txt)
        return p

    def srv(self, *a, **k):
        s = Servidor(*a, **k)
        self.addCleanup(s.cerrar)
        return s

    def test_choice(self):
        s = self.srv(CHOICE)
        esq = self.f("e.json", json.dumps({"id": "q", "pregunta": "¿?", "tipo": "choice", "opciones": {"a": "x", "b": "y"}}))
        dat = self.f("d.csv", "texto,etiqueta\nhola,a\nadios,b\ndudo,a\nmal,b\n")
        r = evaluar(s.url, esq, dat, concurrencia=2)
        m = r["metricas"]
        self.assertEqual(s.n, 4)
        self.assertEqual(m["n"], 4)
        self.assertAlmostEqual(m["exactitud"], 0.75)       # dudo cuenta con su mejor respuesta (argmax de probs)
        self.assertAlmostEqual(m["tasa_escalado"], 0.25)
        self.assertAlmostEqual(m["cobertura"], 0.75)
        self.assertAlmostEqual(m["precision_aceptadas"], 2 / 3)
        self.assertEqual(m["matriz_confusion"]["filas"]["b"], [1, 1, 0])
        self.assertEqual(m["por_capa"]["L1"]["n"], 2)
        self.assertAlmostEqual(m["f1_macro_mejor"], (0.8 + 2 / 3) / 2)
        self.assertAlmostEqual(m["f1_macro_escala_fallo"], (0.5 + 2 / 3) / 2)
        self.assertEqual(m["confusiones_frecuentes"][0]["filas"], [4])
        self.assertIn("## Matriz de confusión", r["informe"])
        self.assertIsNotNone(m["latencia_cliente_ms"]["p99"])

    def test_barrido_precision_objetivo(self):
        filas = [{"etiqueta": "a", "answer": "a", "probs": {"a": c}, "error": "", "escalate": False} for c in (0.99, 0.9)]
        filas += [{"etiqueta": "b", "answer": "a", "probs": {"a": 0.8}, "error": "", "escalate": False}]
        filas += [{"etiqueta": "a", "answer": "a", "probs": {"a": 0.7}, "error": "", "escalate": False}]
        b = barrido(filas, 0.95)
        self.assertEqual(b["mejor"]["aceptadas"], 2)
        self.assertAlmostEqual(b["mejor"]["cobertura"], 0.5)
        b = barrido(filas, 0.7)
        self.assertEqual(b["mejor"]["aceptadas"], 4)       # 3/4 ≥ 0,7
        self.assertFalse(barrido([dict(filas[2])], 0.95)["alcanzable"])

    def test_noul_jsonl(self):
        s = self.srv({"queja": ("true", 0.9, "L0", False), "ok": ("false", 0.8, "L0", False), "x": ("true", 0.6, "L1", False)})
        esq = self.f("e.json", json.dumps({"id": "n1", "pregunta": "¿Hay queja?", "tipo": "noul"}))
        dat = self.f("d.jsonl", "\n".join(json.dumps({"text": t, "label": l}) for t, l in [("queja", "sí"), ("ok", "no"), ("x", "false")]))
        m = evaluar(s.url, esq, dat)["metricas"]
        self.assertAlmostEqual(m["exactitud"], 2 / 3)
        self.assertEqual(m["por_opcion"], {"false": 2, "true": 1})

    def test_score_mae(self):
        s = self.srv({"a": ("3", 0.7, "L1", False), "b": ("1", 0.6, "L1", False), "c": ("2", 0.5, "escalar", True)})
        esq = self.f("e.json", json.dumps({"id": "s1", "pregunta": "¿Urgencia?", "tipo": "score", "opciones": 3}))
        dat = self.f("d.csv", "texto,etiqueta\na,3\nb,3\nc,1\n")
        m = evaluar(s.url, esq, dat)["metricas"]
        self.assertAlmostEqual(m["score"]["mae_aceptadas"]["mae"], 1.0)   # |3-3|, |1-3|
        self.assertEqual(m["score"]["mae_aceptadas"]["n"], 2)
        self.assertAlmostEqual(m["score"]["mae_mejor"]["mae"], 1.0)       # + |2-1|: (0+2+1)/3

    def test_error_de_fila_no_aborta(self):
        s = self.srv({"hola": ("a", 0.9, "L0", False)}, {"largo": (400, {"code": "state_too_long", "message": "x", "question_id": "q"})})
        esq = self.f("e.json", json.dumps({"id": "q", "pregunta": "¿?", "opciones": ["a", "b"]}))
        dat = self.f("d.csv", "texto,etiqueta\nhola,a\nlargo,b\n")
        m = evaluar(s.url, esq, dat, concurrencia=1)["metricas"]
        self.assertEqual(m["errores"], 1)
        self.assertEqual(m["errores_por_codigo"], {"state_too_long": 1})
        self.assertAlmostEqual(m["exactitud"], 0.5)

    def test_error_tipado_del_esquema_aborta(self):
        s = self.srv({}, {"hola": (400, {"code": "invalid_options", "message": "opciones mal"}), "adios": (400, {"code": "invalid_options", "message": "m"})})
        esq = self.f("e.json", json.dumps({"id": "q", "pregunta": "¿?", "opciones": ["a", "b"]}))
        dat = self.f("d.csv", "texto,etiqueta\nhola,a\nadios,b\nhola,a\n")
        with self.assertRaisesRegex(ChispaError, r"\[invalid_options\]"):
            evaluar(s.url, esq, dat)
        self.assertEqual(s.n, 1)                            # paró a la primera

    def test_etiqueta_desconocida(self):
        esq = self.f("e.json", json.dumps({"id": "q", "pregunta": "¿?", "opciones": ["a", "b"]}))
        dat = self.f("d.csv", "texto,etiqueta\nhola,zzz\n")
        with self.assertRaisesRegex(ChispaError, "no son opciones"):
            evaluar("http://127.0.0.1:1", esq, dat)

    def test_cli_salida_md_y_json(self):
        s = self.srv(CHOICE)
        esq = self.f("e.json", json.dumps({"id": "q", "pregunta": "¿?", "opciones": ["a", "b"]}))
        dat = self.f("d.csv", "texto,etiqueta\nhola,a\nadios,b\n")
        base = os.path.join(self.d.name, "inf")
        self.assertEqual(main(["evaluar", "--url", s.url, "--esquema", esq, "--datos", dat, "--salida", base, "--filas"]), 0)
        j = json.load(open(base + ".json", encoding="utf-8"))
        self.assertEqual(j["exactitud"], 1.0)
        self.assertEqual(len(j["filas"]), 2)
        self.assertIn("# Evaluación de Chispa", open(base + ".md", encoding="utf-8").read())
        self.assertEqual(main(["evaluar", "--url", s.url, "--esquema", esq, "--datos", self.f("v.csv", "texto,etiqueta\nhola,zz\n")]), 1)


if __name__ == "__main__":
    unittest.main()
