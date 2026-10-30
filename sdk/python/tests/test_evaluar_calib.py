import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from chispa.evaluar import calib_md, calib_servidor, evaluar, parsear_calib
from tests.test_evaluar import CHOICE, Servidor

METRICAS = '''# HELP chispa_calib x
# TYPE chispa_calib gauge
chispa_calib{capa="L1",tipo="choice",origen="fichero",param="T"} 0.05
chispa_calib{capa="L1",tipo="choice",origen="fichero",param="a"} 4
chispa_calib{capa="L1",tipo="choice",origen="fichero",param="b"} -2
chispa_calib{capa="L1",tipo="choice",origen="fichero",param="theta"} 0.5
chispa_calib{capa="L2",tipo="noul",origen="default",param="T"} 0.05
chispa_calib{capa="L2",tipo="noul",origen="default",param="a"} 4
chispa_calib_tau{capa="L1",clave="tau_escalate",origen="fichero"} 0.8
chispa_calib_tau{capa="L2",clave="tau_l2c",origen="fichero"} 0.9
chispa_calib_sin_tipo{capa="L2",tipo="multi"} 1
chispa_calib_defecto_total{capa="L2",tipo="noul"} 7
chispa_preguntas_total 3
'''


class Metricas:
    """Servidor con solo /metrics (opcionalmente protegido con un token)."""

    def __init__(self, texto, token=None):
        outer = self
        self.visto = None

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.visto = self.headers.get("Authorization")
                if token and outer.visto != "Bearer " + token:
                    self.send_response(401)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                b = texto.encode()
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


class TestCalibEvaluar(unittest.TestCase):
    def test_parsear(self):
        c = parsear_calib(METRICAS)
        self.assertEqual(c["capas"]["L1"]["tipos"]["choice"], {"origen": "fichero", "T": 0.05, "a": 4.0, "b": -2.0, "theta": 0.5})
        self.assertEqual(c["capas"]["L2"]["tipos"]["noul"]["origen"], "default")
        self.assertEqual(c["capas"]["L1"]["taus"]["tau_escalate"]["valor"], 0.8)
        self.assertEqual(c["capas"]["L2"]["sin_calib"], ["multi"])
        self.assertEqual(c["defecto"], {"L2/noul": 7.0})
        self.assertEqual(parsear_calib("chispa_preguntas_total 1\n"), {"capas": {}, "defecto": {}})

    def test_md(self):
        md = calib_md(parsear_calib(METRICAS))
        self.assertIn("| L2 | noul | default |", md)
        self.assertIn("AVISO: la CALIB de L2 no trae multi", md)
        self.assertIn("L2/noul = 7", md)
        self.assertIn("anterior a la CALIB visible", calib_md({"capas": {}, "defecto": {}}))

    def test_servidor_protegido(self):
        s = Metricas(METRICAS, token="sec")
        self.addCleanup(s.cerrar)
        self.assertIn("error", calib_servidor(s.url))
        self.assertEqual(calib_servidor(s.url, token="sec")["capas"]["L1"]["taus"]["tau_escalate"]["valor"], 0.8)
        os.environ["CHISPA_TOKEN_METRICAS"] = "sec"
        self.addCleanup(os.environ.pop, "CHISPA_TOKEN_METRICAS", None)
        self.assertNotIn("error", calib_servidor(s.url))

    def test_evaluar_incluye_calib_y_no_falla_sin_metrics(self):
        s = Servidor(CHOICE)  # sin /metrics (501): la medición sigue
        self.addCleanup(s.cerrar)
        with tempfile.TemporaryDirectory() as d:
            esq, dat = os.path.join(d, "e.json"), os.path.join(d, "d.csv")
            with open(esq, "w", encoding="utf-8") as f:
                json.dump({"id": "q", "pregunta": "¿?", "tipo": "choice", "opciones": {"a": "x", "b": "y"}}, f)
            with open(dat, "w", encoding="utf-8") as f:
                f.write("texto,etiqueta\nhola,a\nadios,b\n")
            r = evaluar(s.url, esq, dat)
            self.assertIn("error", r["calib"])
            self.assertIn("## CALIB del servidor", r["informe"])
            self.assertIn("calib_servidor", r["metricas"])
            self.assertNotIn("calib_servidor", evaluar(s.url, esq, dat, calib=False)["metricas"])


if __name__ == "__main__":
    unittest.main()
