import gzip
import json
import tempfile
import unittest
from pathlib import Path

import torch

from model.datos.comun import filtrar_score
from model.l2 import calibrar as C
from model.l2 import contar_orden_score as c
from model.l2 import datos as D
from model.l2.modelo import ModeloL2, niveles_score, texto_consulta
from model.l2.tests.falso import CodificadorFalso, fila


def invertida(f):
    return dict(f, opciones=list(reversed(f["opciones"])))


class Niveles(unittest.TestCase):
    def test_ordena_por_int(self):
        self.assertEqual(niveles_score(["5", "4", "3", "2", "1"]), ["1", "2", "3", "4", "5"])
        self.assertEqual(niveles_score(["3", "1", "2"]), ["1", "2", "3"])
        self.assertEqual(niveles_score(["10", "9", "8", "7", "6", "5", "4", "3", "2", "1"])[-1], "10")

    def test_errores(self):
        for ops in (["0", "1", "2", "3", "4"], ["01", "02", "03"], ["1", "3"], ["1", "2", "2"], ["a", "b"], ["0", "1"]):
            with self.assertRaises(ValueError, msg=str(ops)):
                niveles_score(ops)


class Modelo(unittest.TestCase):
    def test_declarar_al_reves_da_lo_mismo(self):
        torch.manual_seed(0)
        m, enc = ModeloL2().eval(), CodificadorFalso()
        for k in (5, 3):
            fs = [fila(i, "score", k=k) for i in range(8)]
            fr = [invertida(f) for f in fs]
            with torch.no_grad():
                pa, la = m(fs, enc, entrenar=True)
                pb, lb = m(fr, enc, entrenar=True)
            for f, g, a, b in zip(fs, fr, pa, pb):
                da, db = dict(zip(f["opciones"], a.tolist())), dict(zip(g["opciones"], b.tolist()))
                self.assertEqual(da.keys(), db.keys())
                for o in da:
                    self.assertAlmostEqual(da[o], db[o], places=6)
            for k_ in ("ce", "brier"):
                self.assertAlmostEqual(float(la[k_]), float(lb[k_]), places=5)
            from model.evaluacion.metricas import etiqueta_coral
            f = fs[0]
            niv = niveles_score(f["opciones"])
            self.assertEqual(texto_consulta(f), texto_consulta(fr[0]))
            self.assertEqual(niv[etiqueta_coral([dict(zip(f["opciones"], pa[0].tolist()))[o] for o in niv])],
                             niv[etiqueta_coral([dict(zip(fr[0]["opciones"], pb[0].tolist()))[o] for o in niv])])

    def test_orden_3_1_2(self):
        torch.manual_seed(1)
        m, enc = ModeloL2().eval(), CodificadorFalso()
        f = fila(1, "score", k=3)
        g = dict(f, opciones=["3", "1", "2"])
        with torch.no_grad():
            (a,), _ = m([f], enc, entrenar=False)
            (b,), _ = m([g], enc, entrenar=False)
        for o in "123":
            self.assertAlmostEqual(a[f["opciones"].index(o)].item(), b[g["opciones"].index(o)].item(), places=6)

    def test_ids_malos_fallan(self):
        m, enc = ModeloL2().eval(), CodificadorFalso()
        f = fila(1, "score", k=3)
        for ops in (["0", "1", "2"], ["01", "02", "03"]):
            g = dict(f, opciones=ops, etiqueta=ops[0], descripciones={o: "" for o in ops})
            with self.assertRaises(ValueError):
                m([g], enc, entrenar=False)


class Calibrar(unittest.TestCase):
    def test_calib_scorek_igual_con_orden_invertido(self):
        torch.manual_seed(0)
        m, enc = ModeloL2().eval(), CodificadorFalso()
        fs = [fila(i, "score", k=5, tarea="s") for i in range(60)]
        a = C.a_calib_chispa(C.calibrar(m, enc, fs))
        b = C.a_calib_chispa(C.calibrar(m, enc, [invertida(f) for f in fs]))
        self.assertIn("score5", a["tipos"])
        self.assertEqual(a["tipos"].keys(), b["tipos"].keys())
        for k in a["tipos"]:
            for campo, v in a["tipos"][k].items():
                self.assertAlmostEqual(v, b["tipos"][k][campo], places=5, msg=k)


class Cargador(unittest.TestCase):
    def test_descarta_y_cuenta(self):
        buenas = [fila(0, "score", k=3), invertida(fila(1, "score", k=3))]
        malas = [dict(fila(2, "score", k=3), opciones=["0", "1", "2"], etiqueta="1"),
                 dict(fila(3, "score", k=3), opciones=["01", "02", "03"], etiqueta="01")]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in buenas + malas) + "\n")
            D.DESCARTADAS.clear()
            filas = list(D.iterar(str(p)))
            self.assertEqual([r["id"] for r in filas], [r["id"] for r in buenas])
            self.assertEqual(filas[1]["opciones"], ["3", "2", "1"])   # el orden no ascendente se acepta, sin tocarlo
            self.assertEqual(D.DESCARTADAS["descartadas_score_ids_fuera_de_1k"], 2)
        cuenta = {}
        self.assertEqual(len(list(filtrar_score(buenas + malas, "x", cuenta))), 2)
        self.assertEqual(cuenta["descartadas_score_ids_fuera_de_1k"], 2)


class Recuento(unittest.TestCase):
    def test_meta_y_tabla(self):
        def f(ops, split="train", tarea="t"):
            return {"tipo": "score", "opciones": ops, "tarea": tarea, "split": split}
        filas = [f(["1", "2", "3"]), f(["3", "2", "1"]), f(["3", "2", "1"], "dev"), f(["0", "1", "2"]), f(["01", "02", "03"]),
                 f(["1", "3"]), {"tipo": "noul", "opciones": ["true", "false"]}]
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "meta" / "tsjev").mkdir(parents=True)
            with gzip.open(Path(d) / "meta" / "tsjev" / "train-0.jsonl.gz", "wt", encoding="utf-8") as fh:
                fh.write("\n".join(json.dumps(r) for r in filas) + "\n")
            self.assertEqual(c.main(["--salida", d + "/o", "--meta", d + "/meta"]), 0)
            r = json.load(open(d + "/o/orden-score.json"))
            self.assertEqual(r["total"], {"score": 6, "no_ascendente": 2, "fuera_de_1k": 3, "afectadas": 5})
            self.assertIn("| meta/tsjev | t | dev | 3 | 1 | 1 | 0 | 1 |", open(d + "/o/orden-score.md").read())

    def test_jevbench_fixture(self):
        with tempfile.TemporaryDirectory() as d:
            c.main(["--salida", d, "--jevbench", "model/evaluacion/tests/fixtures/jevbench"])
            self.assertGreater(json.load(open(d + "/orden-score.json"))["total"]["score"], 0)


if __name__ == "__main__":
    unittest.main()
