import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from chispa import bateria as B
from chispa.cli import main

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
JEV = os.path.join(RAIZ, "model", "evaluacion", "tests", "fixtures", "jevbench")
HERR = os.path.join(RAIZ, "model", "herramientas", "test.jsonl")


class Servidor:
    """/v1/decide falso: `regla(state, pregunta)` → dict con answer, probs, layer, escalate (y answers en multi)."""

    def __init__(self, regla):
        self.regla, self.pedidos, self.metrics = regla, [], None
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                q = req["questions"][0]
                outer.pedidos.append(req)
                r = dict(layer="L1", escalate=False, ms=0.5, answer="", probs={}, id=q["id"], kind=q["kind"])
                try:
                    r.update(outer.regla(req["state"], q))
                    b, code = json.dumps({"results": [r]}).encode(), 200
                except KeyError:
                    b, code = json.dumps({"error": "boom"}).encode(), 400
                self.send_response(code)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                b = (outer.metrics or "").encode()
                self.send_response(200 if outer.metrics is not None else 404)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def cerrar(self):
        self.srv.shutdown()
        self.srv.server_close()


def probs(q, ans, c):
    ops = [o["id"] for o in q["options"]]
    return {o: (c if o == ans else (1 - c) / (len(ops) - 1)) for o in ops}


# estado → (respuesta, confianza, escala)
TABLA = {"hola": ("a", 0.95, False), "adios": ("b", 0.9, False), "dudo": ("a", 0.6, True), "mal": ("a", 0.8, False),
         "si1": ("true", 0.9, False), "si2": ("false", 0.7, False), "n1": ("1", 0.9, False), "n2": ("3", 0.8, False)}


def regla(state, q):
    if q["kind"] == "multi":
        if state == "m1":
            return {"answer": "a", "answers": ["a", "b"], "probs": {"a": 0.9, "b": 0.8, "c": 0.1}}
        return {"answer": "a", "answers": ["a"], "probs": {"a": 0.7, "b": 0.2, "c": 0.3}}
    ans, c, esc = TABLA[state]
    return {"answer": "" if esc else ans, "probs": probs(q, ans, c), "escalate": esc, "layer": "escalar" if esc else "L1"}


def fila(i, tipo, texto, etiqueta, ops=None, **k):
    ops = ops or {"choice": ["a", "b"], "noul": ["false", "true"], "score": ["1", "2", "3"], "multi": ["a", "b", "c"]}[tipo]
    d = dict(id=i, tarea="t", tipo=tipo, pregunta="¿?", texto=texto, opciones=ops, descripciones={o: f"def {o}" for o in ops}, etiqueta=etiqueta,
             idioma="es", split="test", fuente="x", licencia="MIT", uso_comercial=True)
    d.update(k)
    return d


DATOS = {
    "choice": [fila("c1", "choice", "hola", "a"), fila("c2", "choice", "adios", "b"), fila("c3", "choice", "dudo", "a"), fila("c4", "choice", "mal", "b"),
               fila("c5", "choice", "hola", "a", split="train")],  # el de train no se mide
    "noul": [fila("n1", "noul", "si1", "true"), fila("n2", "noul", "si2", "true")],
    "score": [fila("s1", "score", "n1", "1"), fila("s2", "score", "n2", "2")],
    "multi": [fila("m1", "multi", "m1", ["a", "b"]), fila("m2", "multi", "m2", "c")],
}


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.srv = Servidor(regla)
        self.addCleanup(self.srv.cerrar)
        for k, v in DATOS.items():
            self.jsonl(f"{k}.jsonl", v)
        self.man = self.manifiesto([{"nombre": k, "ruta": f"{k}.jsonl", "tipo": k, "grupo": "prueba"} for k in DATOS])

    def ruta(self, n):
        return os.path.join(self.d.name, n)

    def jsonl(self, n, filas):
        with open(self.ruta(n), "w", encoding="utf-8") as f:
            f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in filas))

    def jsn(self, n, obj):
        with open(self.ruta(n), "w", encoding="utf-8") as f:
            json.dump(obj, f)
        return self.ruta(n)

    def manifiesto(self, conjuntos, **k):
        k.setdefault("umbrales", {"p50_ms": None, "p99_ms": None})  # la latencia de un servidor falso en hilos es ruido; se prueba aparte
        return self.jsn("man.json", dict(nombre="t", conjuntos=conjuntos, **k))

    def correr(self, **k):
        return B.bateria(self.man, url=self.srv.url, concurrencia=2, **k)

    def cli(self, *a):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = main(["evaluar", "--bateria", self.man, "--url", self.srv.url, *a])
        return rc, err.getvalue()


class TestMetricas(unittest.TestCase):
    def test_ece_a_mano(self):
        # cubo (0,9; 1]: confianzas 0,95 0,92 0,91 (media 0,92667), aciertos 2/3 → |0,66667 − 0,92667| = 0,26, peso 3/4 → 0,195
        # cubo (0,5; 0,6]: 0,55 acertada → 0,45, peso 1/4 → 0,1125; ECE = 0,3075
        self.assertAlmostEqual(B.ece([(0.95, 1), (0.92, 1), (0.91, 0), (0.55, 1)]), 0.3075)
        self.assertIsNone(B.ece([(None, 1)]))
        self.assertAlmostEqual(B.ece([(1.0, 1), (0.0, 0)]), 0.0)  # conf 0 va al primer cubo; conf 1 al último

    def test_cobertura_a_mano(self):
        # ordenadas: 0,99 ✓ 0,98 ✓ 0,97 ✓ 0,96 ✓ 0,60 ✗ 0,55 ✓ → precisión acumulada 1,1,1,1,0,8333; el mayor prefijo con ≥ 0,95 son 4 de 6
        pares = [(0.99, 1), (0.98, 1), (0.97, 1), (0.96, 1), (0.60, 0), (0.55, 1)]
        self.assertAlmostEqual(B.cobertura(pares, 6, 0.95), 4 / 6)
        self.assertAlmostEqual(B.cobertura(pares, 6, 0.80), 1.0)  # 5/6 = 0,8333 ≥ 0,8 al aceptar todo
        self.assertEqual(B.cobertura([(0.9, 0), (0.8, 1)], 2, 0.95), 0.0)
        self.assertAlmostEqual(B.cobertura(pares, 8, 0.95), 4 / 8)  # dos filas sin confianza (error) cuentan en el total
        self.assertAlmostEqual(B.cobertura([(0.9, 1), (0.9, 0), (0.5, 1)], 3, 0.95), 0.0)  # el empate deja pasar los dos


class TestBateria(Base):
    def test_metricas_por_tipo_y_conjunto(self):
        r = self.correr()
        c = r["conjuntos"]["choice"]
        self.assertEqual(c["n"], 4)  # la fila de split train no entra
        self.assertAlmostEqual(c["exactitud"], 0.75)      # «dudo» escala sin respuesta: cuenta su argmax
        self.assertAlmostEqual(c["f1_macro"], (0.8 + 2 / 3) / 2)
        self.assertAlmostEqual(c["ece"], 0.3375)           # |1−0,95| + |1−0,9| + |1−0,6| + |0−0,8| = 1,35 / 4
        self.assertAlmostEqual(c["cobertura"], 0.5)        # 0,95 ✓ 0,9 ✓ 0,8 ✗: acepta 2 de 4
        self.assertAlmostEqual(c["escalado"], 0.25)
        self.assertEqual(c["errores"], 0)
        self.assertIsNotNone(c["p99_ms"])
        self.assertAlmostEqual(r["conjuntos"]["noul"]["exactitud"], 0.5)
        s = r["conjuntos"]["score"]
        self.assertAlmostEqual(s["exactitud"], 0.5)
        self.assertAlmostEqual(s["mae"], 0.5)              # |1−1| y |3−2|
        m = r["conjuntos"]["multi"]
        self.assertAlmostEqual(m["exactitud"], 0.5)        # subconjunto exacto
        self.assertAlmostEqual(m["f1_macro"], (2 / 3 + 1 + 0) / 3)
        self.assertEqual(set(r["tipos"]), {"choice", "noul", "score", "multi"})
        self.assertEqual(r["tipos"]["choice"]["n"], 4)
        self.assertEqual(r["global"]["n"], 10)
        self.assertEqual(r["grupos"]["prueba"]["n"], 10)
        self.assertIn("# Batería de regresión", r["informe"])
        self.assertTrue(r["ok"])
        json.dumps(B.json_reporte(r))

    def test_cuerpo_con_descripciones_de_todas_las_opciones(self):
        self.correr()
        q = next(p["questions"][0] for p in self.srv.pedidos if p["state"] == "si1")
        self.assertEqual(q["kind"], "noul")
        self.assertEqual(q["options"], [{"id": "false", "description": "def false"}, {"id": "true", "description": "def true"}])
        q = next(p["questions"][0] for p in self.srv.pedidos if p["state"] == "n1")
        self.assertEqual([o["description"] for o in q["options"]], ["def 1", "def 2", "def 3"])

    def test_error_de_fila_cuenta_como_fallo(self):
        self.srv.regla = lambda s, q: (_ for _ in ()).throw(KeyError()) if s == "mal" else regla(s, q)
        # el servidor falso devuelve 500 con la excepción: una fila errónea no tira la batería
        r = self.correr()
        c = r["conjuntos"]["choice"]
        self.assertAlmostEqual(c["errores"], 0.25)
        self.assertAlmostEqual(c["exactitud"], 0.75)  # hola, adios, dudo ✓; el error es un fallo (y «mal» ya era fallo): sin cambio
        self.assertAlmostEqual(c["cobertura"], 3 / 4)  # 0,95 ✓ 0,9 ✓ 0,6 ✓: el error no tiene confianza y no se acepta

    def test_linea_base_pasa_y_falla_por_umbral(self):
        r0 = self.correr()
        base = self.jsn("base.json", B.linea_base(r0))
        self.assertTrue(self.correr(linea_base=base)["ok"])
        # la línea base era mejor: exactitud de choice 0,75 → 0,85 (−0,10 > umbral 0,01) falla; con el umbral a 0,2 pasa
        peor = json.loads(json.dumps(B.linea_base(r0)))
        peor["conjuntos"]["choice"]["exactitud"] = 0.85
        ruta = self.jsn("base2.json", peor)
        r = self.correr(linea_base=ruta)
        self.assertFalse(r["ok"])
        fs = [(x["seccion"], x["nombre"], x["metrica"]) for x in r["comparacion"]["fallos"]]
        self.assertIn(("conjuntos", "choice", "exactitud"), fs)
        self.assertIn("FALLA", r["informe"])
        u = self.jsn("u.json", {"exactitud": 0.2})
        self.assertTrue(self.correr(linea_base=ruta, umbrales=u)["ok"])
        # umbral solo para ese conjunto; el de los demás sigue siendo el de por defecto
        u = self.jsn("u2.json", {"por_conjunto": {"choice": {"exactitud": 0.2}}})
        r = self.correr(linea_base=ruta, umbrales=u)
        self.assertEqual([x for x in r["comparacion"]["fallos"] if x["nombre"] == "choice" and x["metrica"] == "exactitud"], [])

    def test_cada_direccion_de_metrica(self):
        r0 = self.correr()
        for met, cambio in (("ece", -0.1), ("escalado", -0.1), ("cobertura", 0.1), ("f1_macro", 0.1), ("p99_ms", None), ("errores", -0.1)):
            b = json.loads(json.dumps(B.linea_base(r0)))
            r0 = json.loads(json.dumps(r0))
            r0["conjuntos"]["choice"]["p99_ms"] = 500.0
            r0["conjuntos"]["choice"]["n"] = 100
            c = b["conjuntos"]["choice"]
            c["n"] = 100
            c[met] = c[met] * 0.1 if cambio is None else c[met] + cambio  # base mejor que lo actual
            if met == "errores":
                c[met] = -0.1
            fs = [x["metrica"] for x in B.comparar(r0, b, B._fusionar(B.UMBRALES, {}))["fallos"] if x["nombre"] == "choice"]
            self.assertIn(met, fs, met)
        # la latencia: relativa y con holgura de 5 ms (y con muestra suficiente)
        for base_ms, ahora_ms, ok in ((50.0, 120.0, False), (50.0, 70.0, True), (2.0, 6.0, True), (5.0, 1.0, True), (2.0, 12.0, False)):
            a = {"conjuntos": {"x": {"n": 100, "p99_ms": ahora_ms}}}
            b = {"conjuntos": {"x": {"n": 100, "p99_ms": base_ms}}}
            self.assertEqual(B.comparar(a, b, B.UMBRALES)["ok"], ok, (base_ms, ahora_ms))
        # mejorar no falla
        b = json.loads(json.dumps(B.linea_base(r0)))
        b["conjuntos"]["choice"]["exactitud"] = 0.5
        b["conjuntos"]["choice"]["ece"] = 0.9
        self.assertTrue(B.comparar(r0, b, B.UMBRALES)["ok"])

    def test_falta_conjunto_y_umbral_desconocido(self):
        r0 = self.correr()
        b = json.loads(json.dumps(B.linea_base(r0)))
        b["conjuntos"]["otro"] = dict(b["conjuntos"]["choice"])
        self.assertFalse(B.comparar(r0, b, B.UMBRALES)["ok"])
        self.assertTrue(B.comparar(r0, b, B.UMBRALES, parcial=True)["ok"])
        with self.assertRaises(B.ErrorBateria):
            self.correr(umbrales=self.jsn("u.json", {"exactitud_": 0.1}))

    def test_solo_y_opcionales(self):
        self.man = self.manifiesto([{"nombre": "choice", "ruta": "choice.jsonl"}, {"nombre": "fuera", "ruta": "${NO_EXISTE_CHISPA_X}/f.jsonl", "opcional": True}])
        avisos = []
        r = self.correr(aviso=avisos.append)
        self.assertEqual(list(r["conjuntos"]), ["choice"])
        self.assertIn("fuera", r["omitidos"])
        self.assertTrue(avisos)
        self.man = self.manifiesto([{"nombre": "fuera", "ruta": "${NO_EXISTE_CHISPA_X}/f.jsonl"}])
        with self.assertRaises(B.ErrorBateria):
            self.correr()

    def test_ruta_por_variable_de_entorno(self):
        self.man = self.manifiesto([{"nombre": "choice", "ruta": "${CHISPA_TEST_DIR}/choice.jsonl", "tipo": "choice"}])
        with mock.patch.dict(os.environ, {"CHISPA_TEST_DIR": self.d.name}):
            self.assertEqual(self.correr()["conjuntos"]["choice"]["n"], 4)

    def test_tipo_declarado_distinto(self):
        self.man = self.manifiesto([{"nombre": "x", "ruta": "noul.jsonl", "tipo": "choice"}])
        with self.assertRaises(B.ErrorBateria):
            self.correr()

    def test_jevbench_crudo(self):
        casos = [{"id": "e-1", "family": "f", "state": "hola", "question": {"type": "choice", "instructions": "¿?", "criteria": {"a": "x", "b": "y"}}, "labels": ["a", "b"], "expected": "a"},
                 {"id": "e-2", "family": "f", "state": {"k": "si1"}, "question": {"type": "noul", "instructions": "¿?"}, "labels": ["no", "yes"], "expected": "yes"},
                 {"id": "e-3", "family": "f", "state": "n2", "question": {"type": "score", "instructions": "¿?", "criteria": ["bajo", "medio", "alto"]}, "labels": ["0", "1", "2"], "expected": 1}]
        self.jsonl("jev.jsonl", casos)
        fs = B.cargar_filas(self.ruta("jev.jsonl"))
        self.assertEqual([f.tipo for f in fs], ["choice", "noul", "score"])
        self.assertEqual([f.etiqueta for f in fs], ["a", "true", "2"])  # noul no→false, yes→true; score nivel + 1
        self.assertEqual(fs[1].texto, '{"k": "si1"}')
        self.srv.regla = lambda s, q: regla("si1" if "si1" in s else s, q)
        self.man = self.manifiesto([{"nombre": "jev", "ruta": "jev.jsonl", "formato": "jevbench", "grupo": "jevbench"}])
        r = self.correr()
        self.assertEqual(r["conjuntos"]["jev"]["n"], 3)
        self.assertAlmostEqual(r["conjuntos"]["jev"]["exactitud"], 1 / 3 + 1 / 3 * 0 + 2 / 3 - 1 / 3)  # a ✓, true ✓, 3 ≠ 2 ✗

    def test_fila_mal_formada(self):
        self.jsonl("m.jsonl", [fila("x", "choice", "hola", "z")])
        with self.assertRaises(B.ErrorBateria) as cm:
            B.cargar_filas(self.ruta("m.jsonl"))
        self.assertIn("m.jsonl:1", str(cm.exception))


class TestCli(Base):
    def test_codigos_y_guardar_linea_base(self):
        base = self.ruta("base.json")
        rc, _ = self.cli("--guardar-linea-base", base)
        self.assertEqual(rc, 0)
        rc, _ = self.cli("--linea-base", base)
        self.assertEqual(rc, 0)
        with open(base) as f:
            b = json.load(f)
        self.assertNotIn("filas", b)
        self.assertEqual(b["version"], B.VERSION)
        b["global"]["exactitud"] = 1.0
        mala = self.jsn("mala.json", b)
        otra = self.ruta("otra.json")
        rc, err = self.cli("--linea-base", mala, "--guardar-linea-base", otra)
        self.assertEqual(rc, 1)
        self.assertIn("REGRESIÓN global/global: exactitud", err)
        self.assertFalse(os.path.exists(otra))  # una corrida que falla no pisa la línea base
        # el informe de --salida vale como línea base
        rc, _ = self.cli("--salida", self.ruta("inf"))
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(self.ruta("inf.md")))
        self.assertEqual(self.cli("--linea-base", self.ruta("inf.json"))[0], 0)

    def test_error_de_uso_sale_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(["evaluar", "--bateria", self.man]), 2)  # ni --url ni --modelo
            self.assertEqual(main(["evaluar", "--bateria", self.ruta("no_hay.json"), "--url", self.srv.url]), 2)
        self.assertIn("--url", err.getvalue())

    def test_evaluar_sin_bateria_sigue_pidiendo_sus_argumentos(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["evaluar", "--url", self.srv.url]), 1)


def _por_descripcion(state, q):
    """Estable: decide por lo que dice la descripción de la opción, no por su id ni su posición (choice y multi; noul/score, por texto)."""
    ops = q["options"]
    if q["kind"] == "multi":
        act = [o["id"] for o in ops if o.get("description") in ("def a", "def b")]
        return {"answer": act[0], "answers": act, "probs": {o["id"]: (0.9 if o["id"] in act else 0.1) for o in ops}}
    ans = next((o["id"] for o in ops if o.get("description") == "def a"), ops[0]["id"])
    return {"answer": ans, "probs": probs(q, ans, 0.9)}


def _por_posicion(state, q):
    """Inestable: contesta la primera opción de la lista, así que una permutación le cambia la decisión."""
    ops = q["options"]
    if q["kind"] == "multi":
        return _por_descripcion(state, q)
    return {"answer": ops[0]["id"], "probs": probs(q, ops[0]["id"], 0.7)}


OPS4 = ["a", "b", "c", "d"]
CASOS_ROB = {"choice": [fila(f"r{i}", "choice", f"Hola cuenta número {i}, necesito ayuda con mi pago", "a", ops=OPS4) for i in range(8)],
             "noul": [fila("rn", "noul", "mi tarjeta es urgente", "false")], "score": [fila("rs", "score", "quiero mi dinero", "1")],
             "multi": [fila("rm", "multi", "hola banco", ["a", "b"], ops=OPS4)]}


class TestRobustez(Base):
    def correr_con(self, regla_fn, **k):
        srv = Servidor(regla_fn)
        self.addCleanup(srv.cerrar)
        for n, v in CASOS_ROB.items():
            self.jsonl(f"{n}.jsonl", v)
        self.man = self.manifiesto([{"nombre": n, "ruta": f"{n}.jsonl", "tipo": n, "grupo": "rob"} for n in CASOS_ROB])
        self.srv = srv
        return self.correr(robustez=True, **k)

    def test_servidor_estable(self):
        r = self.correr_con(_por_descripcion)
        g = r["global"]
        self.assertEqual(g["estabilidad"], 1.0)
        self.assertEqual(g["delta_conf"], 0.0)
        self.assertEqual(g["delta_conf_p95"], 0.0)
        # se mandaron casos completos: opciones con descripción y pregunta parafraseada
        self.assertTrue(any(x["questions"][0]["question"].startswith(("Dime", "Necesito", "Por favor", "Sobre", "Con base")) for x in self.srv.pedidos))
        self.assertTrue(all("description" in o for x in self.srv.pedidos for o in x["questions"][0]["options"]))
        for t in ("renombrar", "permutar", "parafrasear", "erratas", "largo", "mezcla"):
            self.assertIn(t, r["conjuntos"]["choice"]["transformaciones"])
        self.assertIn("Robustez por transformación", r["informe"])

    def test_renombrar_y_permutar_solo_en_choice_y_multi(self):
        r = self.correr_con(_por_descripcion)
        for n in ("noul", "score"):
            ts = r["conjuntos"][n]["transformaciones"]
            self.assertNotIn("permutar", ts)
            self.assertNotIn("renombrar", ts)
        self.assertIn("renombrar", r["conjuntos"]["multi"]["transformaciones"])
        self.assertEqual(r["conjuntos"]["multi"]["estabilidad"], 1.0)  # el conjunto activo se compara con los ids traducidos

    def test_servidor_que_cambia_con_la_permutacion(self):
        r = self.correr_con(_por_posicion)
        ts = r["conjuntos"]["choice"]["transformaciones"]
        self.assertLess(ts["permutar"]["estabilidad"], 1.0)
        self.assertEqual(ts["renombrar"]["estabilidad"], 1.0)  # mismo orden, ids nuevos traducidos con el mapa
        self.assertEqual(ts["parafrasear"]["estabilidad"], 1.0)
        self.assertLess(r["global"]["estabilidad"], 1.0)
        self.assertGreater(ts["permutar"]["delta_conf_p95"], -1)

    def test_delta_de_confianza(self):
        def regla_conf(state, q):
            ops = q["options"]
            ans = next((o["id"] for o in ops if o.get("description") == "def a"), ops[0]["id"])
            return {"answer": ans, "probs": probs(q, ans, 0.6 if state.isupper() else 0.9)}
        r = self.correr_con(regla_conf)
        m = r["conjuntos"]["choice"]["transformaciones"]["mayusculas"]
        self.assertEqual(m["estabilidad"], 1.0)
        self.assertGreater(m["delta_conf"], 0.0)
        self.assertGreaterEqual(m["delta_conf_p95"], m["delta_conf"])
        self.assertAlmostEqual(m["delta_conf_p95"], 0.3)

    def test_robustez_max_limita_casos(self):
        r1 = self.correr_con(_por_descripcion, robustez_max=2)
        r2 = self.correr_con(_por_descripcion)
        self.assertLess(r1["conjuntos"]["choice"]["n_variantes"], r2["conjuntos"]["choice"]["n_variantes"])
        self.assertLessEqual(r1["conjuntos"]["choice"]["n_variantes"], 2 * 7)

    def test_sin_modulo_avisa(self):
        avisos = []
        with mock.patch.object(B, "MODULO_VARIANTES", "chispa.no_existe_variantes"):
            r = self.correr(robustez=True, aviso=avisos.append)
        self.assertNotIn("estabilidad", r["global"])
        self.assertTrue(any("variantes" in a for a in avisos))

    def test_estabilidad_entra_en_la_comparacion(self):
        r = {"global": {"n": 1, "estabilidad": 0.7}, "conjuntos": {}, "tipos": {}, "grupos": {}}
        b = {"global": {"n": 1, "estabilidad": 0.9}, "conjuntos": {}, "tipos": {}, "grupos": {}}
        self.assertFalse(B.comparar(r, b, B.UMBRALES)["ok"])

    def test_estabilidad_min(self):
        r = {"global": {"n": 1, "estabilidad": 0.85}, "conjuntos": {"c": {"n": 1, "estabilidad": 0.85}}, "tipos": {}, "grupos": {}}
        b = {"global": {"n": 1, "estabilidad": 0.85}, "conjuntos": {"c": {"n": 1, "estabilidad": 0.85}}, "tipos": {}, "grupos": {}}
        self.assertTrue(B.comparar(r, b, B.UMBRALES)["ok"])
        b["estabilidad_min"] = 0.9  # mínimo absoluto, aunque la base no haya empeorado
        c = B.comparar(r, b, B.UMBRALES)
        self.assertFalse(c["ok"])
        self.assertTrue(all(f["metrica"] == "estabilidad_min" for f in c["fallos"]))
        b["estabilidad_min"] = 0.8
        self.assertTrue(B.comparar(r, b, B.UMBRALES)["ok"])
        r["global"].pop("estabilidad")  # sin medir con mínimo: falla
        self.assertFalse(B.comparar(r, b, B.UMBRALES)["ok"])


class TestServidorLocal(unittest.TestCase):
    def test_arranca_y_apaga(self):
        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "falso.py")
            with open(fake, "w") as f:
                f.write('import sys, json\nfrom http.server import BaseHTTPRequestHandler, HTTPServer\n'
                        'a = sys.argv[sys.argv.index("-addr") + 1]; assert "-modelo" in sys.argv\n'
                        'class H(BaseHTTPRequestHandler):\n'
                        '    def log_message(self, *x): pass\n'
                        '    def do_GET(self):\n'
                        '        b = json.dumps({"status": "ok"}).encode(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)\n'
                        'HTTPServer((a.split(":")[0], int(a.split(":")[1])), H).serve_forever()\n')
            exe = os.path.join(d, "chispa-server")
            with open(exe, "w") as f:
                f.write(f'#!/bin/sh\nexec {sys.executable} {fake} "$@"\n')
            os.chmod(exe, os.stat(exe).st_mode | stat.S_IXUSR)
            with B.servidor_local("m.chispa", servidor=exe, espera=20) as url:
                from chispa import Chispa
                self.assertTrue(Chispa(url).salud())
            from chispa import Chispa
            self.assertFalse(Chispa(url, reintentos=0, timeout=1).salud())

    def test_servidor_que_muere(self):
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "chispa-server")
            with open(exe, "w") as f:
                f.write("#!/bin/sh\necho modelo roto >&2\nexit 3\n")
            os.chmod(exe, 0o755)
            with self.assertRaises(B.ErrorBateria) as cm:
                with B.servidor_local("m.chispa", servidor=exe, espera=20):
                    pass
            self.assertIn("modelo roto", str(cm.exception))


@unittest.skipUnless(os.path.isdir(JEV), "falta el fixture de JevBench del repo")
class TestFixturesDelRepo(unittest.TestCase):
    def test_jevbench(self):
        fs = B.cargar_filas(JEV, "jevbench")
        self.assertEqual(len(fs), 13)
        self.assertTrue({f.tipo for f in fs} <= {"choice", "noul", "score"})

    @unittest.skipUnless(os.path.isfile(HERR), "falta model/herramientas/test.jsonl")
    def test_herramientas(self):
        fs = B.cargar_filas(HERR, "filas", "choice")
        self.assertEqual(len(fs), 368)
        self.assertEqual(len(fs[0].q.options), 32)


if __name__ == "__main__":
    unittest.main()
