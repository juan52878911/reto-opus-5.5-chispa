"""W6: texto de torre v2 (sin id cuando hay descripción), contrato-torre.md."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import torch

from model.l2 import entrenar, evaluar
from model.l2 import exportar as E
from model.l2 import robustez as R
from model.l2.modelo import SEP, ModeloL2, niveles_score, texto_consulta, texto_opcion
from model.l2.tests.falso import CodificadorFalso, fila
from model.l2.tests.test_entrenar import escribir
from model.l2.tests.test_t24_exportar import CodificadorDiminuto

FIX = Path(__file__).parent / "fixtures" / "texto_torre_v2.json"


def v1_anterior(fila_, opcion):
    """La implementación anterior de `texto_opcion`, tal cual."""
    return "passage: %s%s%s%s%s" % (fila_["pregunta"], SEP, opcion, SEP, fila_["descripciones"].get(opcion, ""))


def consulta_anterior(f):
    ops = f["opciones"]
    if f["tipo"] == "noul":
        return v1_anterior(f, "true")
    if f["tipo"] == "score":
        return v1_anterior(f, niveles_score(ops)[-1])
    return v1_anterior(f, ops[-1])


def renombrar(f):
    """Misma fila con ids opacos (opciones, descripciones y etiqueta)."""
    m = {o: "op_%02x" % (7 * i + 3) for i, o in enumerate(f["opciones"])}
    g = copy.deepcopy(f)
    g.update(opciones=[m[o] for o in f["opciones"]], descripciones={m[o]: d for o, d in f["descripciones"].items()}, etiqueta=m[f["etiqueta"]])
    return g


class Paridad(unittest.TestCase):
    def test_fixture(self):
        casos = json.loads(FIX.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(casos), 10)
        self.assertTrue(any(not c["descripcion"] for c in casos))
        self.assertTrue(any(c["descripcion"] and not c["descripcion"].strip() for c in casos))
        for c in casos:
            self.assertEqual(set(c), {"pregunta", "opcion", "descripcion", "v1", "v2"})
            f = {"pregunta": c["pregunta"], "descripciones": {c["opcion"]: c["descripcion"]}}
            self.assertEqual(texto_opcion(f, c["opcion"]), c["v1"], c)
            self.assertEqual(texto_opcion(f, c["opcion"], "v1"), c["v1"], c)
            self.assertEqual(texto_opcion(f, c["opcion"], "v2_sin_id"), c["v2"], c)

    def test_version_desconocida(self):
        with self.assertRaises(ValueError):
            texto_opcion({"pregunta": "p", "descripciones": {}}, "a", "v3")

    def test_descripcion_sin_normalizar(self):
        f = {"pregunta": "p", "descripciones": {"a": "  con espacios \n"}}
        self.assertEqual(texto_opcion(f, "a", "v2_sin_id"), "passage: p · " + "  con espacios \n")


class V1SinCambios(unittest.TestCase):
    def test_igual_que_la_implementacion_anterior(self):
        filas = [fila(i, t, 4, "a", k=4) for i, t in enumerate(["choice", "noul", "score", "choice"])]
        filas.append({**fila(9), "descripciones": {"op0": "", "op1": "   ", "op2": "Año ñandú"}})
        filas.append({**fila(10, "noul", tarea="z"), "opciones": ["true", "false"]})
        for f in filas:
            for o in f["opciones"]:
                self.assertEqual(texto_opcion(f, o), v1_anterior(f, o))
            self.assertEqual(texto_consulta(f), consulta_anterior(f))
            self.assertEqual(texto_consulta(f, "v1"), consulta_anterior(f))

    def test_modelo_por_defecto_es_v1(self):
        self.assertEqual(ModeloL2().texto_torre, "v1")


class V2RenombrarIds(unittest.TestCase):
    def filas(self):
        return [fila(0, "choice", 4, "a"), fila(1, "noul", tarea="b"), fila(2, "score", tarea="c", k=4)]

    def test_textos_no_cambian_con_descripciones(self):
        for f in self.filas():
            g = renombrar(f) if f["tipo"] == "choice" else f
            tf = [texto_opcion(f, o, "v2_sin_id") for o in f["opciones"]]
            tg = [texto_opcion(g, o, "v2_sin_id") for o in g["opciones"]]
            self.assertEqual(tf, tg)
            self.assertNotEqual(tf, [texto_opcion(f, o) for o in f["opciones"]])

    def test_sin_descripcion_sigue_el_id(self):
        f = {**fila(0), "descripciones": {}}
        self.assertEqual([texto_opcion(f, o, "v2_sin_id") for o in f["opciones"]], [texto_opcion(f, o) for o in f["opciones"]])

    def test_consulta_noul_y_score(self):
        for f in self.filas()[1:]:
            ultimo = "true" if f["tipo"] == "noul" else niveles_score(f["opciones"])[-1]
            self.assertEqual(texto_consulta(f, "v2_sin_id"), texto_opcion(f, ultimo, "v2_sin_id"))

    def test_forward_no_depende_de_los_ids(self):
        torch.manual_seed(0)
        enc = CodificadorFalso()
        f = fila(0, "choice", 4, "a")
        pr = {}
        for v in ("v1", "v2_sin_id"):
            m = ModeloL2(texto_torre=v).eval()
            torch.manual_seed(1)
            m.load_state_dict(ModeloL2().state_dict())
            m.asegurar_cabeza("choice")
            with torch.no_grad():
                pr[v] = (m([f], enc, entrenar=False)[0][0], m([renombrar(f)], enc, entrenar=False)[0][0])
        a, b = pr["v2_sin_id"]
        self.assertTrue(torch.allclose(a, b, atol=1e-6))


class Checkpoint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        escribir(self.dir / "d.jsonl", [fila(i, "choice", 4, "a") for i in range(30)] + [fila(100 + i, "noul", tarea="b") for i in range(20)])

    def tearDown(self):
        self.tmp.cleanup()

    def correr(self, salida, extra=()):
        enc = CodificadorFalso()
        with mock.patch.object(entrenar, "Codificador", lambda **kw: enc):
            return entrenar.main(["--salida", str(self.dir / salida), "--datos", str(self.dir / "d.jsonl"), "--pasos", "4", "--lote", "8",
                                  "--device", "cpu", "--ckpt-cada", "0", *extra])

    def test_desde_g8_con_flag_y_herencia(self):
        self.assertEqual(self.correr("g8"), 0)
        g8 = torch.load(self.dir / "g8" / "ultimo.pt", weights_only=False)
        self.assertEqual(g8["texto_torre"], "v1")
        del g8["texto_torre"]  # un checkpoint de G.8 no lo traía
        torch.save(g8, self.dir / "g8.pt")
        self.assertEqual(evaluar.cargar_modelo(self.dir / "g8.pt")[0].texto_torre, "v1")
        self.assertEqual(self.correr("v2", ["--desde", str(self.dir / "g8.pt"), "--texto-torre", "v2_sin_id"]), 0)
        for n in ("ultimo.pt", "mejor.pt"):
            ck = torch.load(self.dir / "v2" / n, weights_only=False)
            self.assertEqual(ck["texto_torre"], "v2_sin_id", n)
        self.assertEqual(evaluar.cargar_modelo(self.dir / "v2" / "ultimo.pt")[0].texto_torre, "v2_sin_id")
        # sin flag, un nuevo ajuste desde el v2 lo hereda; reanudar también
        self.assertEqual(self.correr("v2b", ["--desde", str(self.dir / "v2" / "mejor.pt")]), 0)
        self.assertEqual(torch.load(self.dir / "v2b" / "ultimo.pt", weights_only=False)["texto_torre"], "v2_sin_id")
        self.assertEqual(self.correr("g8b", ["--desde", str(self.dir / "g8.pt")]), 0)
        self.assertEqual(torch.load(self.dir / "g8b" / "ultimo.pt", weights_only=False)["texto_torre"], "v1")


class Exportador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.manual_seed(1)
        cls.enc = CodificadorDiminuto()
        cls.base = ModeloL2().eval()
        cls.filas = [fila(0, "choice", 3, "a"), fila(1, "noul", tarea="b"), fila(2, "score", tarea="c", k=3),
                     {**fila(3, "choice", 3, "d"), "descripciones": {"op0": "", "op1": "  ", "op2": "con descripción"}}]

    def modelo(self, v):
        m = ModeloL2(texto_torre=v).eval()
        m.load_state_dict(self.base.state_dict())
        return m

    def test_meta_escribe_texto_torre(self):
        self.assertEqual(E.meta_de(self.filas, texto_torre="v2_sin_id")["texto_torre"], "v2_sin_id")
        self.assertNotIn("texto_torre", E.meta_de(self.filas))  # falta = v1: los .chispa v1 no cambian
        self.assertEqual(E.meta_de(self.filas), E.meta_de(self.filas, texto_torre="v1"))

    def test_torres_v2(self):
        m2 = self.modelo("v2_sin_id")
        torres = E.entradas_torres(m2, self.enc, self.filas)
        torres1 = E.entradas_torres(self.modelo("v1"), self.enc, self.filas)
        self.assertEqual([t[:3] for t in torres], [t[:3] for t in torres1])  # las claves no cambian
        for r in self.filas:
            ops = r["opciones"] if r["tipo"] == "choice" else [E.opcion_consulta(r)]
            for o in ops:
                with torch.no_grad():
                    h = m2.torre(self.enc.pasaje([texto_opcion(r, o, "v2_sin_id")]))[0].numpy()
                q, esc = E.cuantizar_vec(h)
                hallada = [t for t in torres if t[0] == r["pregunta"] and t[1] == r["tipo"] and (o in [x[0] for x in t[2]])]
                self.assertTrue(hallada)
                np.testing.assert_array_equal(hallada[0][3], q)
        self.assertTrue(any(not np.array_equal(a[3], b[3]) for a, b in zip(torres, torres1)))

    def test_torres_v2_no_dependen_de_los_ids(self):
        m2 = self.modelo("v2_sin_id")
        f = self.filas[0]
        a = E.entradas_torres(m2, self.enc, [f])
        b = E.entradas_torres(m2, self.enc, [renombrar(f)])
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x[3], y[3])

    def test_chispa_lleva_texto_torre(self):
        m2 = self.modelo("v2_sin_id")
        torres = E.entradas_torres(m2, self.enc, self.filas[:1])
        dim = int(torres[0][3].shape[0])
        calib = {"tipos": {"choice": {"T": 0.05, "a": 0, "b": 0, "theta": 0.5}}, "tau_escalate": 0.6}
        with tempfile.TemporaryDirectory() as t:
            onnx = Path(t) / "l2.onnx"
            onnx.write_bytes(b"ONNX-falso")
            for v, esperado in (("v2_sin_id", "v2_sin_id"), ("v1", None)):
                out = Path(t) / (v + ".chispa")
                E.empaquetar(E.meta_de(self.filas[:1], texto_torre=v), onnx, E.esquemas_json(torres, dim), calib, out)
                import sys
                sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
                from chispa import formato
                meta = json.loads(formato.leer(out.read_bytes())[formato.META])
                self.assertEqual(meta.get("texto_torre"), esperado)
                self.assertEqual(meta["version"], 1)


class TodoMayusculas(unittest.TestCase):
    def test_variante(self):
        f = {**fila(0), "texto": "reserva un vuelo a Málaga, por favor ñandú"}
        v = R.variantes_de(f, "todo_mayusculas", 0, None)
        self.assertEqual(v["texto"], f["texto"].upper())
        self.assertEqual(v["texto"], "RESERVA UN VUELO A MÁLAGA, POR FAVOR ÑANDÚ")
        self.assertEqual((v["pregunta"], v["opciones"], v["descripciones"], v["etiqueta"]), (f["pregunta"], f["opciones"], f["descripciones"], f["etiqueta"]))
        self.assertEqual(v["mapa"], {o: o for o in f["opciones"]})
        self.assertIsNone(R.variantes_de({**f, "texto": "1234 !!"}, "todo_mayusculas", 0, None))  # sin letras: no es una variante

    def test_aplica_a_noul_y_la_normalizacion_la_deshace(self):
        from model.l2.modelo import normalizar_mayusculas
        f = {**fila(0, "noul"), "texto": "mensaje bastante normal"}
        v = R.variantes_de(f, "todo_mayusculas", 0, None)
        self.assertEqual(normalizar_mayusculas(v["texto"]), f["texto"])

    def test_criterio_del_5_por_ciento(self):
        self.assertIn("todo_mayusculas", R.TIPOS)
        self.assertNotIn("todo_mayusculas", R.SIN_CRITERIO)
        res = {"max_tok": 1, "max_filas": 1, "semilla": 0, "modelos": ["L2"], "tipos": ["mayusculas", "todo_mayusculas"],
               "global": {"L2": {t: {"n": 10, "pct_cambia": 0.5, "pct_cambia_ic95": [0.2, 0.8], "acc_orig": 0.9, "delta_acc": 0.0,
                                     "delta_acc_ic95": [0.0, 0.0]} for t in ("mayusculas", "todo_mayusculas")}},
               "no_medido": {}, "arreglos": [{"modelo": "L2", "tipo": "todo_mayusculas", "pct_cambia": 0.5, "arreglo": "x", "coste": "y"}]}
        md = R.informe_md(res)
        self.assertIn("| mezcla de mayúsculas |", md)
        self.assertIn("| todo_mayusculas |", md)
        self.assertEqual(md.count("**> 5 %**"), 1)
        self.assertIn("sin criterio del 5 %", md)


if __name__ == "__main__":
    unittest.main()
