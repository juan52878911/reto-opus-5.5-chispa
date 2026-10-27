import json
import os
import random
import tempfile
import unittest
from pathlib import Path

import numpy as np

from model.evaluacion import chispa_eval as CE
from model.evaluacion import metricas as M
from model.evaluacion.adaptador_arena import asr_desde_ledger
from model.evaluacion.jevbench import cargar_jevbench

AQUI = Path(__file__).parent
RAIZ = AQUI.parents[2]


def fila(i, etiqueta, opciones=("a", "b"), tarea="t"):
    return {"id": i, "tarea": tarea, "opciones": list(opciones), "etiqueta": etiqueta}


def pred(i, probs, ms=None):
    p = {"id": i, "probs": probs}
    if ms is not None:
        p["ms"] = ms
    return p


class TestMetricas(unittest.TestCase):
    def test_exactitud_y_macro_f1(self):
        y = ["a", "a", "b", "b", "c"]
        p = ["a", "b", "b", "b", "a"]
        self.assertAlmostEqual(M.exactitud(y, p), 3 / 5)
        # a: tp1 fp1 fn1 -> 2/4; b: tp2 fp1 -> 4/5; c: 0  => (0.5+0.8+0)/3
        self.assertAlmostEqual(M.macro_f1(y, p), 1.3 / 3)

    def test_ece_cubos_distintos(self):
        # cubos 14, 12, 9, 5: |1-.95|,|1-.85|,|0-.65|,|0-.35| = .05,.15,.65,.35 -> media .3
        self.assertAlmostEqual(M.ece([0.95, 0.85, 0.65, 0.35], [1, 1, 0, 0]), 0.3)

    def test_ece_cubo_compartido(self):
        # los cuatro caen en (13/15, 14/15]: acierto 0.75, conf 0.9 -> 0.15
        self.assertAlmostEqual(M.ece([0.9, 0.9, 0.9, 0.9], [1, 1, 1, 0]), 0.15)

    def test_ece_mezcla_y_extremos(self):
        # conf 1.0 al último cubo; 0.1 y 0.12 comparten (1/15, 2/15]: acierto medio .5, conf .11 -> 2/4*.39
        conf, ok = [1.0, 1.0, 0.1, 0.12], [1, 1, 1, 0]
        self.assertAlmostEqual(M.ece(conf, ok), 0.5 * 0.0 + 0.5 * abs(0.5 - 0.11))

    def test_brier(self):
        P = [[0.7, 0.3], [0.6, 0.4]]
        Y = [[1, 0], [0, 1]]
        # .09+.09=.18 ; .36+.36=.72 -> .45
        self.assertAlmostEqual(M.brier(P, Y), 0.45)

    def test_cobertura(self):
        conf = [0.99, 0.98, 0.97, 0.96, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4]
        ok = [1, 1, 1, 1, 1, 0, 1, 0, 0, 0]
        # precisión acumulada: k=5 1.0, k=6 .833, k=7 .857, k=8 .75, k=10 .5
        for obj, cob, umbral in [(0.95, 0.5, 0.9), (0.99, 0.5, 0.9), (0.8, 0.7, 0.7)]:
            r = M.cobertura_a_precision(conf, ok, obj)
            self.assertAlmostEqual(r["cobertura"], cob)
            self.assertAlmostEqual(r["umbral"], umbral)

    def test_cobertura_inalcanzable_y_empates(self):
        r = M.cobertura_a_precision([0.9, 0.8, 0.7], [0, 1, 1], 0.95)
        self.assertEqual(r, {"cobertura": 0.0, "umbral": None})
        # empate en 0.8: se acepta o rechaza junto (1 acierto, 1 fallo)
        r = M.cobertura_a_precision([0.9, 0.8, 0.8], [1, 1, 0], 0.95)
        self.assertAlmostEqual(r["cobertura"], 1 / 3)

    def test_auroc(self):
        # pos .9 gana 3 pares; pos .4 gana 2 de 3 -> 5/6
        self.assertAlmostEqual(M.auroc([1, 1, 0, 0, 0], [0.9, 0.4, 0.5, 0.3, 0.2]), 5 / 6)
        # empate cuenta medio: (1 + .5)/2
        self.assertAlmostEqual(M.auroc([1, 0, 0], [0.5, 0.5, 0.1]), 0.75)
        self.assertIsNone(M.auroc([0, 0], [0.1, 0.2]))

    def test_latencia(self):
        r = M.latencia([10, 20, 30, 40])
        self.assertAlmostEqual(r["p50_ms"], 25.0)
        self.assertAlmostEqual(r["p99_ms"], 39.7)
        self.assertIsNone(M.latencia([None]))

    def test_deriva(self):
        A = [{"a": 0.8, "b": 0.2}, {"a": 0.6, "b": 0.4}]
        B = [{"a": 0.3, "b": 0.7}, {"a": 0.5, "b": 0.5}]
        d = M.deriva(A, B)
        self.assertAlmostEqual(d["tasa_cambio_top1"], 0.5)
        self.assertAlmostEqual(d["variacion_total_media"], (0.5 + 0.1) / 2)

    def test_contra_sklearn(self):
        try:
            from sklearn.metrics import f1_score, roc_auc_score
        except ImportError:
            self.skipTest("sin sklearn")
        rng = random.Random(3)
        y = [rng.choice("abcd") for _ in range(200)]
        p = [rng.choice("abcd") for _ in range(200)]
        self.assertAlmostEqual(M.macro_f1(y, p), f1_score(y, p, average="macro"))
        pos = [rng.random() < 0.3 for _ in range(200)]
        s = [round(rng.random(), 1) for _ in range(200)]  # con empates
        self.assertAlmostEqual(M.auroc(pos, s), roc_auc_score(pos, s))


class TestEvaluar(unittest.TestCase):
    def test_metricas_por_tarea_y_globales(self):
        filas = [fila("1", "a"), fila("2", "b"), fila("3", "a", tarea="u"), fila("4", "escalate", ("a", "escalate"), tarea="u")]
        preds = [pred("1", {"a": 0.7, "b": 0.3}, 10), pred("2", {"a": 0.6, "b": 0.4}, 20),
                 pred("3", {"a": 0.9, "escalate": 0.1}, 30), pred("4", {"a": 0.8, "escalate": 0.2}, 40)]
        r = CE.evaluar(filas, preds)
        t = r["por_tarea"]["t"]
        self.assertAlmostEqual(t["brier"], 0.45)
        self.assertAlmostEqual(t["exactitud"], 0.5)
        self.assertIsNone(t["auroc_escalate"])
        u = r["por_tarea"]["u"]
        # fila 3: .01+.01 ; fila 4: .64+.64 -> media .65
        self.assertAlmostEqual(u["brier"], 0.65)
        self.assertAlmostEqual(u["auroc_escalate"], 1.0)  # .2 > .1
        self.assertEqual(r["global"]["n"], 4)
        # global: positivo solo la fila 4 (.2); negativos .3,.4,.1 -> gana a .1 y pierde con .3,.4 => 1/3
        self.assertAlmostEqual(r["global"]["auroc_escalate"], 1 / 3)
        self.assertAlmostEqual(r["global"]["latencia"]["p50_ms"], 25.0)
        self.assertNotIn("latencia", CE.evaluar(filas, [pred(p["id"], p["probs"]) for p in preds])["global"])

    def test_auroc_sin_escalate_usa_uno_menos_confianza(self):
        filas = [fila("1", "escalate", ("a", "b", "escalate")), fila("2", "a", ("a", "b", "escalate"))]
        r = CE.evaluar(filas, [pred("1", {"a": 0.6, "b": 0.4}), pred("2", {"a": 0.9, "b": 0.1})])
        self.assertAlmostEqual(r["global"]["auroc_escalate"], 1.0)

    def test_deriva_en_evaluar(self):
        filas = [fila("1", "a"), fila("2", "b")]
        A = [pred("1", {"a": 0.8, "b": 0.2}), pred("2", {"a": 0.6, "b": 0.4})]
        B = [pred("1", {"a": 0.3, "b": 0.7}), pred("2", {"a": 0.5, "b": 0.5})]
        d = CE.evaluar(filas, A, B)["deriva"]["global"]
        self.assertAlmostEqual(d["tasa_cambio_top1"], 0.5)

    def test_errores(self):
        filas = [fila("1", "a"), fila("2", "b")]
        ok = pred("1", {"a": 0.5, "b": 0.5})
        with self.assertRaisesRegex(CE.ErrorEval, "sin predicción"):
            CE.evaluar(filas, [ok])
        with self.assertRaisesRegex(CE.ErrorEval, "suman"):
            CE.evaluar(filas, [ok, pred("2", {"a": 0.5, "b": 0.6})])
        with self.assertRaisesRegex(CE.ErrorEval, "opción desconocida 'z'"):
            CE.evaluar(filas, [ok, pred("2", {"a": 0.5, "z": 0.5})])
        with self.assertRaisesRegex(CE.ErrorEval, "repetido"):
            CE.evaluar(filas, [ok, ok, pred("2", {"a": 1.0})])
        with self.assertRaisesRegex(CE.ErrorEval, "fuera de opciones"):
            CE.evaluar([fila("1", "q")], [ok])

    def test_escalate_siempre_permitida(self):
        r = CE.evaluar([fila("1", "a")], [pred("1", {"a": 0.5, "escalate": 0.5})])
        self.assertEqual(r["global"]["n"], 1)

    def test_cli_codigos_de_salida(self):
        with tempfile.TemporaryDirectory() as d:
            f, p = os.path.join(d, "f.jsonl"), os.path.join(d, "p.jsonl")
            Path(f).write_text(json.dumps(fila("1", "a")) + "\n")
            Path(p).write_text(json.dumps(pred("1", {"a": 1.0, "b": 0.0})) + "\n")
            s = os.path.join(d, "s.json")
            self.assertEqual(CE.main(["--datos", f, "--pred", p, "--salida", s]), 0)
            self.assertEqual(json.loads(Path(s).read_text())["global"]["exactitud"], 1.0)
            Path(p).write_text(json.dumps(pred("1", {"a": 0.2})) + "\n")
            self.assertEqual(CE.main(["--datos", f, "--pred", p]), 2)
            self.assertEqual(CE.main(["--datos", f]), 2)
            self.assertEqual(CE.main(["--datos", os.path.join(d, "no.jsonl"), "--pred", p]), 2)


class TestPuntaAPunta(unittest.TestCase):
    def test_intencion_uniforme(self):
        ruta = RAIZ / "model" / "sondeo" / "intencion.jsonl"
        filas = CE.asignar_ids(CE.leer_jsonl(str(ruta)), str(ruta))
        self.assertEqual(len(filas), 390)
        preds = []
        for r in filas:
            k = len(r["opciones"])
            preds.append(pred(r["id"], {o: 1 / k for o in r["opciones"]}))
        g = CE.evaluar(filas, preds)["global"]
        # 13 clases x 30 filas; el empate cae en la 1ª opción: exactitud 1/13,
        # F1 de esa clase 60/420 = 1/7 y 0 las demás => macro 1/91; conf 1/13 = exactitud => ECE 0;
        # Brier (12/13)... = ((12/13)^2 + 12/169) = 156/169
        self.assertAlmostEqual(g["exactitud"], 1 / 13)
        self.assertAlmostEqual(g["macro_f1"], 1 / 91)
        self.assertAlmostEqual(g["ece"], 0.0, places=12)
        self.assertAlmostEqual(g["brier"], 156 / 169 - 0.0)
        self.assertEqual(g["cobertura_p95"]["cobertura"], 0.0)
        self.assertIsNone(g["auroc_escalate"])


class TestAdaptadores(unittest.TestCase):
    def test_asr_arena(self):
        r = asr_desde_ledger(str(AQUI / "fixtures" / "ledger_ejemplo.jsonl"))
        self.assertEqual(r["rondas"], 3)
        self.assertAlmostEqual(r["detectores"]["tox-A"]["asr"], 2 / 3)
        # tox-B: 3 rondas, una con error: cuenta 2 respuestas, 0 engañado
        self.assertEqual(r["detectores"]["tox-B"]["ataques"], 2)
        self.assertEqual(r["detectores"]["tox-B"]["errores"], 1)
        self.assertAlmostEqual(r["detectores"]["tox-B"]["asr"], 0.0)
        self.assertEqual(r["detectores"]["tox-B"]["escalados"], 1)
        self.assertAlmostEqual(r["enjambre"]["toxicidad"]["asr"], 1 / 3)

    def test_asr_ledger_real_si_existe(self):
        ruta = RAIZ / "arena" / "data" / "ledger.jsonl"
        if not ruta.exists():
            self.skipTest("sin arena/data/ledger.jsonl (corre make smoke)")
        r = asr_desde_ledger(str(ruta))
        self.assertGreater(r["rondas"], 0)
        for d in r["detectores"].values():
            self.assertTrue(d["asr"] is None or 0 <= d["asr"] <= 1)

    def test_ledger_roto(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write('{"x": 1}\n')
        try:
            with self.assertRaisesRegex(ValueError, "AttackRound"):
                asr_desde_ledger(f.name)
        finally:
            os.unlink(f.name)

    def test_jevbench(self):
        filas = cargar_jevbench(str(AQUI / "fixtures" / "jevbench_ejemplo.jsonl"))
        self.assertEqual([f["id"] for f in filas], ["jev:test:j1", "jev:test:j2"])
        self.assertEqual(filas[1]["etiqueta"], "musica")
        self.assertFalse(filas[0]["uso_comercial"])
        r = CE.evaluar(filas, [pred("jev:test:j1", {"clima": 0.9, "musica": 0.1}),
                               pred("jev:test:j2", {"clima": 0.8, "musica": 0.2})])
        self.assertAlmostEqual(r["global"]["exactitud"], 0.5)

    def test_jevbench_caso_incompleto(self):
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as f:
            f.write('{"caso": "x"}\n')
        try:
            with self.assertRaisesRegex(ValueError, "falta"):
                cargar_jevbench(f.name)
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
