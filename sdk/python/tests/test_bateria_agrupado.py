import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from chispa import bateria as B
from chispa.cli import main

_ej = os.path.join(os.path.dirname(__file__), "..", "ejemplos", "bateria_textos_largos.py")
_spec = importlib.util.spec_from_file_location("bateria_textos_largos", _ej)
LARGOS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(LARGOS)

METRICAS = '# x\nchispa_calib_defecto_total{capa="L1",tipo="choice"} %d\n'


class Servidor:
    """/v1/decide con presupuesto: rechaza (400) una petición con más de `max_preguntas` preguntas sobre un texto largo; cuenta peticiones y /metrics."""

    def __init__(self, max_preguntas=100, defecto=0):
        self.pedidos, self.defecto, self.max_preguntas = [], defecto, max_preguntas
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _responder(self, code, cuerpo):
                b = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.pedidos.append(req)
                if len(req["questions"]) > outer.max_preguntas:
                    return self._responder(400, {"error": "presupuesto excedido"})
                outer.defecto += len(req["questions"])  # cada decisión usa la CALIB por defecto
                rs = [{"id": q["id"], "kind": q["kind"], "layer": "L1", "escalate": False, "ms": 0.5, "answer": q["options"][0]["id"],
                       "probs": {q["options"][0]["id"]: 0.9, q["options"][1]["id"]: 0.1}} for q in req["questions"]]
                self._responder(200, {"results": rs})

            def do_GET(self):
                self._responder(200, (METRICAS % outer.defecto).encode())

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def cerrar(self):
        self.srv.shutdown()
        self.srv.server_close()


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.man = LARGOS.escribir(self.d.name, textos=3, preguntas=3, kb=8)

    def servidor(self, **k):
        s = Servidor(**k)
        self.addCleanup(s.cerrar)
        return s


class TestLatenciaPorMuestras(unittest.TestCase):
    def _m(self, n, n_lat, p99, **k):
        return dict({"n": n, "n_latencia": n_lat, "p99_ms": p99, "p50_ms": p99}, **k)

    def test_errores_no_cuentan_como_muestras(self):
        base, act = {"global": self._m(45, 5, 10.0)}, {"global": self._m(45, 5, 60.0)}
        c = B.comparar(act, base, {"p99_ms": 1.0, "p50_ms": 1.0})
        self.assertTrue(c["ok"], c["fallos"])
        self.assertTrue(any("menos de 30 muestras" in a for a in c["avisos"]))

    def test_agregar_cuenta_muestras(self):
        rs = [{"id": str(i), "esquema": "e", "tipo": "choice", "opciones": ["a", "b"], "etiqueta": "a", "answer": "a", "answers": None, "probs": {"a": 0.9, "b": 0.1},
               "escalate": False, "error": "" if i < 5 else "x", "cliente_ms": 1.0 if i < 5 else None} for i in range(45)]
        m = B.agregar(rs)
        self.assertEqual((m["n"], m["n_latencia"]), (45, 5))

    def test_base_antigua_sin_n_latencia_usa_n(self):
        base, act = {"global": {"n": 45, "p99_ms": 10.0}}, {"global": self._m(45, 40, 60.0)}
        self.assertFalse(B.comparar(act, base, {"p99_ms": 1.0})["ok"])  # n=45 ≥ 30: se juzga


class TestCalibPorCorrida(Base):
    def test_defecto_es_la_diferencia(self):
        s = self.servidor(defecto=1000)  # tráfico previo de otros clientes
        rep = B.bateria(self.man, url=s.url, concurrencia=1)
        self.assertEqual(rep["calib_servidor"]["defecto"], {"L1/choice": 9.0})  # 3 textos × 3 preguntas, no 1009
        self.assertIn("durante la corrida", rep["informe"])

    def test_sin_trafico_de_la_corrida_no_hay_aviso(self):
        antes, despues = {"capas": {}, "defecto": {"L1/choice": 7.0}}, {"capas": {}, "defecto": {"L1/choice": 7.0}}
        self.assertEqual(B._calib_corrida(antes, despues)["defecto"], {})

    def test_la_lectura_final_incluye_la_robustez(self):
        s = self.servidor()
        lecturas = []
        orig = B.calib_servidor
        B.calib_servidor = lambda *a, **k: (lecturas.append(len(s.pedidos)), orig(*a, **k))[1]
        self.addCleanup(setattr, B, "calib_servidor", orig)
        rep = B.bateria(self.man, url=s.url, concurrencia=1, robustez=True, robustez_max=3)
        self.assertIn("global", rep)
        self.assertEqual(lecturas[0], 0)
        self.assertEqual(lecturas[-1], len(s.pedidos))  # la última lectura va tras todas las peticiones
        self.assertGreater(len(s.pedidos), 9)


class TestAgrupar(Base):
    def test_una_peticion_por_texto(self):
        s = self.servidor()
        rep = B.bateria(self.man, url=s.url, concurrencia=2, agrupar=True)
        self.assertEqual(len(s.pedidos), 3)
        self.assertEqual({len(p["questions"]) for p in s.pedidos}, {3})
        self.assertEqual(rep["global"]["n"], 9)
        self.assertEqual(rep["global"]["errores"], 0)

    def test_sin_agrupar_sigue_una_pregunta_por_peticion(self):
        s = self.servidor()
        B.bateria(self.man, url=s.url, concurrencia=2)
        self.assertEqual(len(s.pedidos), 9)

    def test_detecta_un_presupuesto_por_peticion(self):
        s = self.servidor(max_preguntas=2)  # el servidor no admite 3 preguntas sobre un texto largo
        self.assertEqual(B.bateria(self.man, url=s.url, concurrencia=2)["global"]["errores"], 0)  # sin agrupar la batería no lo ve
        with self.assertRaisesRegex(B.ErrorBateria, "presupuesto excedido"):
            B.bateria(self.man, url=s.url, concurrencia=2, agrupar=True)

    def test_filas_repetidas_en_un_texto_van_juntas(self):
        s = self.servidor()
        fs = B.cargar_filas(os.path.join(self.d.name, "largos.jsonl"))
        tareas = [(fs[0], None), (fs[0], None), (fs[3], None)]
        res = B._correr_agrupado(B.Chispa(s.url), tareas, 1)
        self.assertEqual([r["id"] for r in res], [fs[0].id, fs[0].id, fs[3].id])
        self.assertEqual(sorted(len(p["questions"]) for p in s.pedidos), [1, 2])
        self.assertEqual(len({q["id"] for q in s.pedidos[0]["questions"]}), len(s.pedidos[0]["questions"]))

    def _filas(self):
        return B.cargar_filas(os.path.join(self.d.name, "largos.jsonl"))

    def test_mas_de_256_filas_sobre_un_texto_se_trocean(self):
        s = self.servidor(max_preguntas=256)
        f = self._filas()[0]
        res = B._correr_agrupado(B.Chispa(s.url), [(f, None, "c")] * 300, 2)
        self.assertEqual(len(res), 300)
        self.assertFalse([r for r in res if r["error"]])
        self.assertEqual(sorted(len(p["questions"]) for p in s.pedidos), [44, 256])

    def test_se_corta_por_tamano_de_cuerpo(self):
        s = self.servidor()
        f = self._filas()[0]
        una = len(json.dumps(f.q.a_json()).encode())
        tope = len(json.dumps({"state": f.texto}).encode()) + int(2.5 * (una + 64))  # caben 2 preguntas, no 3
        res = B._correr_agrupado(B.Chispa(s.url), [(f, None, "c")] * 10, 1, max_cuerpo=tope)
        self.assertFalse([r for r in res if r["error"]])
        self.assertEqual(sorted(len(p["questions"]) for p in s.pedidos), [2] * 5)
        for p in s.pedidos:
            self.assertLess(len(json.dumps(p).encode()), tope)

    def test_conjuntos_distintos_con_el_mismo_texto_no_comparten_peticion(self):
        s = self.servidor()
        f = self._filas()[0]
        B._correr_agrupado(B.Chispa(s.url), [(f, None, "a"), (f, None, "b"), (f, None, "a")], 1)
        self.assertEqual(sorted(len(p["questions"]) for p in s.pedidos), [1, 2])

    def test_n_latencia_cuenta_peticiones(self):
        s = self.servidor()
        f = self._filas()[0]
        res = B._correr_agrupado(B.Chispa(s.url), [(f, None, "c")] * 40, 1)
        m = B.agregar(res)
        self.assertEqual((m["n"], m["n_latencia"]), (40, 1))

    def test_linea_base_guarda_agrupado_y_no_compara_latencia_si_el_modo_difiere(self):
        s = self.servidor()
        rep = B.bateria(self.man, url=s.url, concurrencia=1, agrupar=True)
        self.assertTrue(B.linea_base(rep)["agrupado"])
        m = lambda p99: {"n": 100, "n_latencia": 100, "p50_ms": p99, "p99_ms": p99}
        base = {"global": m(10.0), "agrupado": False}
        act = {"global": m(500.0), "agrupado": True}
        c = B.comparar(act, base, {"p99_ms": 0.1, "p50_ms": 0.1})
        self.assertTrue(c["ok"], c["fallos"])
        self.assertTrue(any("modo de envío distinto" in a for a in c["avisos"]))
        act["agrupado"] = False  # mismo modo: sí se compara
        self.assertFalse(B.comparar(act, base, {"p99_ms": 0.1, "p50_ms": 0.1})["ok"])

    def test_cli_agrupar(self):
        s = self.servidor()
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["evaluar", "--bateria", self.man, "--url", s.url, "--agrupar"]), 0)
        self.assertEqual(len(s.pedidos), 3)


class TestGuardarLineaBase(Base):
    def cli(self, *a):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = main(["evaluar", "--bateria", self.man, "--url", self.s.url, *a])
        return rc, err.getvalue()

    def setUp(self):
        super().setUp()
        self.s = self.servidor()

    def test_ruta_invalida_falla_antes_de_correr(self):
        rc, err = self.cli("--guardar-linea-base", os.path.join(self.d.name, "no_existe", "b.json"))
        self.assertEqual(rc, 2)
        self.assertEqual(self.s.pedidos, [])
        rc, _ = self.cli("--guardar-linea-base", self.d.name)  # un directorio
        self.assertEqual(rc, 2)
        self.assertEqual(self.s.pedidos, [])

    def test_fichero_corrupto_se_ignora_y_se_regenera(self):
        ruta = os.path.join(self.d.name, "base.json")
        with open(ruta, "w") as f:
            f.write("{no es json")
        rc, err = self.cli("--guardar-linea-base", ruta)
        self.assertEqual(rc, 0, err)
        self.assertIn("se ignora", err)
        with open(ruta) as f:
            self.assertEqual(json.load(f)["version"], B.VERSION)
        with open(ruta, "w") as f:
            f.write("[1]")  # JSON válido pero no una línea base
        self.assertEqual(self.cli("--guardar-linea-base", ruta)[0], 0)


if __name__ == "__main__":
    unittest.main()
