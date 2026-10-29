import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from chispa import ChispaError
from chispa.cli import main
from chispa.evaluar import evaluar

# texto → (probs por opción, capa, escala); las activas son las de p ≥ 0,5 (en el orden de la pregunta)
TABLA = {
    "uno": ({"a": 0.9, "b": 0.8, "c": 0.1}, "L1", False),     # real a|b: exacta
    "dos": ({"a": 0.9, "b": 0.2, "c": 0.7}, "L1", False),     # real a: sobra c
    "tres": ({"a": 0.1, "b": 0.2, "c": 0.3}, "L2", False),    # real ninguna: exacta con []
    "cuatro": ({}, "escalar", True),                          # real b|c: escala sin probs, sin predicción
}
CSV = "texto,etiqueta\nuno,a|b\ndos,a\ntres,\ncuatro,b|c\n"
ESQ = {"id": "t", "pregunta": "¿Temas?", "tipo": "multi", "opciones": {"a": "x", "b": "y", "c": "z"}}


class Servidor:
    def __init__(self):
        self.pedidas = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                q = req["questions"][0]
                outer.pedidas.append(q["kind"])
                probs, capa, esc = TABLA[req["state"]]
                ops = [o["id"] for o in q["options"]]
                act = [o for o in ops if probs.get(o, 0) >= 0.5]
                r = {"id": q["id"], "kind": "multi", "answer": max(act, key=probs.get) if act else "", "answers": act, "probs": probs,
                     "layer": capa, "escalate": esc, "ms": 0.5}
                b = json.dumps({"results": [r]}).encode()
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


class TestEvaluarMulti(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.s = Servidor()
        self.addCleanup(self.s.cerrar)
        self.esq = self.f("e.json", json.dumps(ESQ))

    def f(self, nombre, txt):
        p = os.path.join(self.d.name, nombre)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(txt)
        return p

    def test_metricas(self):
        r = evaluar(self.s.url, self.esq, self.f("d.csv", CSV), concurrencia=2)
        m = r["metricas"]
        self.assertEqual(set(self.s.pedidas), {"multi"})
        self.assertEqual((m["n"], m["n_con_prediccion"], m["n_sin_etiquetas"]), (4, 3, 1))
        self.assertAlmostEqual(m["exactitud_subconjunto"], 0.5)      # sobre las 4 filas: la escalada sin probs es fallo
        self.assertAlmostEqual(m["hamming"], 1 / 9)                  # una decisión errada de 3 filas × 3 opciones
        self.assertAlmostEqual(m["f1_micro"], 6 / 7)                 # tp 3, fp 1, fn 0
        self.assertAlmostEqual(m["f1_macro"], 2 / 3)                 # a 1, b 1, c 0 (c tiene soporte por la fila sin predicción)
        pe = m["por_etiqueta"]
        self.assertEqual((pe["a"]["tp"], pe["a"]["fp"], pe["a"]["fn"], pe["a"]["soporte"]), (2, 0, 0, 2))
        self.assertEqual((pe["c"]["tp"], pe["c"]["fp"], pe["c"]["soporte"]), (0, 1, 1))
        self.assertEqual(m["por_opcion"], {"a": 2, "b": 2, "c": 1})
        self.assertAlmostEqual(m["tasa_escalado"], 0.25)
        self.assertAlmostEqual(m["cobertura"], 0.75)
        self.assertAlmostEqual(m["precision_aceptadas"], 2 / 3)
        self.assertEqual(m["por_capa"]["L2"]["correctas"], 1)

    def test_cobertura_a_precision_por_etiqueta(self):
        m = evaluar(self.s.url, self.esq, self.f("d.csv", CSV), objetivo=0.95)["metricas"]
        a, c = m["por_etiqueta"]["a"]["barrido"], m["por_etiqueta"]["c"]["barrido"]
        self.assertAlmostEqual(a["mejor"]["cobertura"], 0.75)        # 3 decisiones sobre «a», todas bien, de 4 filas
        self.assertAlmostEqual(c["mejor"]["cobertura"], 0.25)        # solo la de conf. 0,9: las de 0,7 empatan y una falla
        self.assertAlmostEqual(c["mejor"]["umbral"], 0.9)
        self.assertFalse(evaluar(self.s.url, self.esq, self.f("d2.csv", "texto,etiqueta\ndos,b\n"), objetivo=0.95)["metricas"]["por_etiqueta"]["b"]["barrido"]["alcanzable"])

    def test_informe_y_cli(self):
        r = evaluar(self.s.url, self.esq, self.f("d.csv", CSV))
        self.assertIn("## Por etiqueta", r["informe"])
        self.assertIn("Exactitud por subconjunto", r["informe"])
        base = os.path.join(self.d.name, "inf")
        self.assertEqual(main(["evaluar", "--url", self.s.url, "--esquema", self.esq, "--datos", self.f("d3.csv", CSV), "--salida", base, "--filas"]), 0)
        j = json.load(open(base + ".json", encoding="utf-8"))
        self.assertAlmostEqual(j["exactitud_subconjunto"], 0.5)
        self.assertEqual(j["filas"][0]["etiqueta"], ["a", "b"])
        self.assertEqual(j["filas"][0]["answers"], ["a", "b"])

    def test_jsonl_con_listas(self):
        dat = self.f("d.jsonl", "\n".join(json.dumps({"text": t, "label": l}) for t, l in [("uno", ["a", "b"]), ("tres", [])]))
        self.assertAlmostEqual(evaluar(self.s.url, self.esq, dat)["metricas"]["exactitud_subconjunto"], 1.0)

    def test_etiqueta_desconocida(self):
        with self.assertRaisesRegex(ChispaError, "no son opciones"):
            evaluar("http://127.0.0.1:1", self.esq, self.f("d.csv", "texto,etiqueta\nuno,a|zzz\n"))


if __name__ == "__main__":
    unittest.main()
