"""Pruebas de medir.py con predicciones inventadas. Uso: python -I server/deploy/abstencion/test_medir.py"""
import json
import subprocess
import sys
import tempfile
import unittest
import xml.dom.minidom
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import medir  # noqa: E402
import validacion  # noqa: E402,F401


def escribir(ruta, filas):
    Path(ruta).write_text("".join(json.dumps(r) + "\n" for r in filas))


def pred(i, probs, escala, capa="L1"):
    return {"id": f"t{i}", "probs": probs, "layer": capa, "escalate": escala}


# 10 filas, dos clases a y b. Contestadas (6): 4 bien, 2 mal. Escaladas (3): la mejor respuesta acierta en 2. Una con error del cliente.
VERDAD = {f"t{i}": e for i, e in enumerate("aaaaabbbbb")}
PREDS = [
    pred(0, {"a": .95, "b": .05}, False), pred(1, {"a": .90, "b": .10}, False), pred(2, {"a": .85, "b": .15}, False),
    pred(3, {"a": .20, "b": .80}, False),                                # contestada y mal (verdad a)
    pred(4, {"a": .55, "b": .45}, True, "escalar"),                           # escalada, mejor respuesta bien
    pred(5, {"a": .10, "b": .90}, False), pred(6, {"a": .08, "b": .92}, False),
    pred(7, {"a": .70, "b": .30}, False),                                # contestada y mal (verdad b)
    pred(8, {"a": .40, "b": .60}, True, "escalar"),                           # escalada, bien
    pred(9, {"escalate": 1.0}, True, "error") | {"error": "OSError: x"},
]


class TestMedir(unittest.TestCase):
    def test_metricas(self):
        t = medir.medir(PREDS, VERDAD)
        self.assertEqual((t["n"], t["escalan"], t["errores_cliente"], t["contestadas"]), (10, 3, 1, 7))
        self.assertAlmostEqual(t["escala"], 0.3)
        self.assertAlmostEqual(t["precision_contestada"], 5 / 7)   # t0,t1,t2,t5,t6 bien; t3,t7 mal
        # contestadas: verdad a: t0 t1 t2 (bien) t3 (pred b); verdad b: t5 t6 (bien) t7 (pred a)
        # a: tp3 fp1 fn1 -> 6/8; b: tp2 fp1 fn1 -> 4/6
        self.assertAlmostEqual(t["macro_f1_contestada"], (0.75 + 2 / 3) / 2)
        # escalado como fallo: a: tp3 fp1 fn2 (t3,t4) -> 6/9; b: tp2 fp1 fn3 (t7,t8,t9) -> 4/8
        self.assertAlmostEqual(t["macro_f1_escala_fallo"], (6 / 9 + 0.5) / 2)
        # mejor respuesta de las 9 sin error: a: tp 4 (t0-t2,t4) fp1 fn1; b: tp3 (t5,t6,t8) fp1 fn1 -> 8/10 y 6/8
        self.assertAlmostEqual(t["macro_f1_mejor_respuesta"], (0.8 + 0.75) / 2)
        self.assertEqual(t["capas"], {"L1": 7, "escalar": 2, "error": 1})

    def test_escalar_todo_o_nada(self):
        todas = [pred(i, {"a": 1.0, "b": 0.0}, True) for i in range(10)]
        t = medir.medir(todas, VERDAD)
        self.assertEqual((t["escala"], t["contestadas"], t["precision_contestada"], t["macro_f1_contestada"]), (1.0, 0, None, None))
        self.assertEqual(t["macro_f1_escala_fallo"], 0.0)
        ninguna = [pred(i, {"a": 1.0, "b": 0.0}, False) for i in range(10)]
        t = medir.medir(ninguna, VERDAD)
        self.assertEqual((t["escala"], t["precision_contestada"]), (0.0, 0.5))

    def test_curva_y_tabla(self):
        t = medir.medir(PREDS, VERDAD)
        pts = t["puntos"]   # 9 filas usables, sin la del error
        self.assertEqual(pts[-1][0], 0.0)                       # aceptarlo todo: abstención 0
        self.assertAlmostEqual(pts[-1][1], 7 / 9)               # precisión sin abstener = aciertos de la mejor respuesta (t3 y t7 fallan)
        absts = [p[0] for p in pts]
        self.assertEqual(absts, sorted(absts, reverse=True))
        # por confianza: .95 .92 .90 .90 .85 (5 aciertos), .80 (fallo), .70 (fallo), .60 .55 (aciertos)
        f = {a: (ab, p, tau) for a, ab, p, tau in t["tabla"]}
        self.assertEqual(f[0][0], 0.0)
        self.assertLessEqual(f[50][0], 0.5)
        self.assertAlmostEqual(f[50][0], 4 / 9)
        self.assertEqual(f[50][1], 1.0)                         # con 4/9 de abstención solo quedan los 5 primeros
        self.assertAlmostEqual(f[40][0], 3 / 9)                 # 4/9 = 44 % > 40 %: el punto con ≤ 40 % acepta 6 de 9
        self.assertAlmostEqual(f[40][1], 5 / 6)
        self.assertTrue(all(ab <= a / 100 + 1e-9 for a, (ab, _, _) in f.items()))

    def test_empates_no_se_parten(self):
        preds = [pred(i, {"a": .9, "b": .1}, False) for i in range(10)]
        t = medir.medir(preds, VERDAD)
        self.assertEqual(len(t["puntos"]), 1)   # un solo τ: o se contesta todo o nada
        self.assertEqual({f[1] for f in t["tabla"]}, {0.0})     # todas las filas caen en ese punto, con abstención real 0

    def test_h1_h2(self):
        t = medir.medir(PREDS, VERDAD)
        self.assertIsNone(medir.veredicto_h1(t))   # F1 de la mejor respuesta 0,775 < 0,85
        buena = [pred(i, {VERDAD[f"t{i}"]: .99, "x": .01}, i < 2) for i in range(10)]
        t = medir.medir(buena, VERDAD)
        self.assertEqual(medir.veredicto_h1(t), (True, True))
        fila = medir.fila_h2(t, 0.2)
        self.assertLessEqual(fila[1], 0.2)

    def test_cli_escribe_todo(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            escribir(d / "p.jsonl", PREDS)
            escribir(d / "v.jsonl", [{"id": k, "etiqueta": v, "split": "test"} for k, v in VERDAD.items()])
            r = subprocess.run([sys.executable, "-I", str(AQUI / "medir.py"), "--pred", f"demo={d / 'p.jsonl'}",
                                "--verdad", f"demo={d / 'v.jsonl'}", "--salida", str(d / "s")], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            for f in ("demo.md", "demo.svg", "informe.md", "abstencion.json"):
                self.assertTrue((d / "s" / f).is_file(), f)
            xml.dom.minidom.parse(str(d / "s" / "demo.svg"))
            j = json.loads((d / "s" / "abstencion.json").read_text())
            self.assertAlmostEqual(j["demo"]["escala"], 0.3)
            self.assertIn("| demo | 10 | 30.0 % |", (d / "s" / "informe.md").read_text())

    def test_tareas_distintas_fallan(self):
        r = subprocess.run([sys.executable, "-I", str(AQUI / "medir.py"), "--pred", "a=x", "--verdad", "b=y", "--salida", "/tmp/nada-medir"],
                           capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


class TestValidacion(unittest.TestCase):
    def preparar(self, dev=None):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, d)
        escribir(d / "ejemplos.jsonl", [{"texto": f"t{i}", "etiqueta": "ab"[i % 2]} for i in range(50)])
        (d / "esquema.json").write_text(json.dumps({"id": "tarea_x"}))
        args = ["--dir", str(d), "--esquema", str(d / "esquema.json")]
        if dev:
            escribir(d / "dev.jsonl", dev)
            args += ["--dev", str(d / "dev.jsonl")]
        return d, args

    def test_reserva_el_20_por_ciento_estratificado_sin_solaparse(self):
        import validacion
        d, args = self.preparar()
        validacion.main(args)
        ent, val = medir.leer(d / "ejemplos-entrenar.jsonl"), medir.leer(d / "validacion.jsonl")
        self.assertEqual((len(ent), len(val)), (40, 10))
        self.assertFalse({r["texto"] for r in ent} & {r["texto"] for r in val})
        self.assertEqual({r["etiqueta"] for r in val}, {"a", "b"})

    def test_con_dev_de_la_tarea_no_toca_el_train(self):
        import validacion
        d, args = self.preparar([{"tarea": "tarea_x", "texto": "u", "etiqueta": "a"}, {"tarea": "otra", "texto": "v", "etiqueta": "b"}])
        validacion.main(args)
        self.assertEqual(medir.leer(d / "validacion.jsonl"), [{"texto": "u", "etiqueta": "a"}])
        self.assertFalse((d / "ejemplos-entrenar.jsonl").exists())


class TestColumnaEstimada(unittest.TestCase):
    def test_celdas(self):
        self.assertEqual(medir.columna_estimada({"precision_contestada": 0.859}, 0.95), "0.950 | -0.091 |")
        self.assertEqual(medir.columna_estimada({"precision_contestada": 0.9}, None), "— | — |")


if __name__ == "__main__":
    unittest.main()
