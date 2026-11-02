import gzip
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from model.evaluacion.jevbench import cargar_jevbench
from model.l2 import orientacion_score as O
from model.l2.diag_score import coral_params, etiqueta
from model.l2.modelo import Coral, ModeloL2, indice_etiqueta, niveles_score, texto_consulta, texto_opcion
from model.l2.tests.falso import CodificadorFalso, fila

RAIZ_FX = Path(__file__).resolve().parent / "fixtures_largos" / "jevbench"


class Signo(unittest.TestCase):
    """El signo de s en la cabeza CORAL, de extremo a extremo: s alta = nivel alto, en entrenamiento y en evaluación."""

    def test_coral_con_w_positivo_sube_el_nivel_con_s(self):
        c = Coral(5)
        s = torch.linspace(-3, 6, 50)
        niv = Coral.etiqueta(c.acumuladas(s))
        self.assertTrue(bool((niv[1:] >= niv[:-1]).all()))
        self.assertEqual((int(niv[0]), int(niv[-1])), (0, 4))
        self.assertTrue(bool((c.acumuladas(s)[:, :-1] >= c.acumuladas(s)[:, 1:]).all()))   # P(y>j) decrece con j

    def test_etiqueta_diag_igual_que_coral(self):
        c = Coral(4)
        s = np.linspace(-2, 6, 40)
        self.assertTrue((etiqueta(s, {"w": float(c.w), "theta": [float(t) for t in c.umbrales()]})
                         == Coral.etiqueta(c.acumuladas(torch.tensor(s).float())).numpy()).all())

    def test_la_torre_es_la_del_nivel_maximo_y_el_indice_es_el_nivel(self):
        for ops in (["1", "2", "3"], ["3", "1", "2"], ["10", "2", "1", "3", "4", "5", "6", "7", "8", "9"]):
            f = {**fila(0, "score", k=len(ops)), "opciones": ops, "descripciones": {o: "d" + o for o in ops}}
            f["etiqueta"] = "2"
            self.assertEqual(texto_consulta(f), texto_opcion(f, str(len(ops))))
            self.assertEqual(indice_etiqueta(f), 1)          # nivel 2 = índice 1, sea cual sea el orden declarado

    def test_el_entrenamiento_sube_p_del_nivel_alto_con_s_alta(self):
        """Con el mismo texto de torre, a s mayor el entrenamiento mueve la masa hacia niveles más altos (w sigue positivo)."""
        torch.manual_seed(0)
        c = Coral(3)
        opt = torch.optim.Adam(c.parameters(), lr=0.1)
        s = torch.tensor([-1.0] * 20 + [0.0] * 20 + [1.0] * 20)
        y = torch.tensor([0] * 20 + [1] * 20 + [2] * 20)
        for _ in range(200):
            p = c(s)
            loss = -torch.log(p[torch.arange(60), y].clamp(min=1e-7)).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
        self.assertGreater(float(c.w), 0)
        self.assertEqual(Coral.etiqueta(c.acumuladas(torch.tensor([-1.0, 0.0, 1.0]))).tolist(), [0, 1, 2])


class Conversion(unittest.TestCase):
    def test_todos_los_casos_score_de_jevbench(self):
        filas = cargar_jevbench(RAIZ_FX)
        self.assertTrue(any(r["tipo"] == "score" for r in filas))
        self.assertEqual(O.comprobar_conversion(filas), [])

    def test_detecta_una_conversion_rota(self):
        filas = [dict(r) for r in cargar_jevbench(RAIZ_FX) if r["tipo"] == "score"]
        filas[0]["etiqueta"] = str(int(filas[0]["etiqueta"]) % len(filas[0]["opciones"]) + 1)
        self.assertEqual(len(O.comprobar_conversion(filas)), 1)


class Veredicto(unittest.TestCase):
    def g(self, rho):
        return {"global": {"rho_max": rho, "rho_min": -rho, "rho_invertida": -rho, "n": 10, "esquemas": 1}}

    def test_tres_conclusiones(self):
        self.assertIn("conversión", O.veredicto(self.g(-0.5), self.g(0.6), ["x"])[0])
        self.assertIn("orientación", O.veredicto(self.g(-0.5), self.g(-0.4), [])[0])
        self.assertIn("no generaliza", O.veredicto(self.g(-0.5), self.g(0.6), [])[0])
        self.assertTrue(O.veredicto(self.g(0.5), self.g(0.6), [])[0].startswith("sin fallo"))


class Extremo(unittest.TestCase):
    def test_main_con_codificador_falso_y_meta_inventado(self):
        from unittest import mock
        from model.l2.modelo import Codificador
        enc = CodificadorFalso()
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d / "meta" / "fuente").mkdir(parents=True)
            with gzip.open(d / "meta" / "fuente" / "dev-00000.jsonl.gz", "wt", encoding="utf-8") as f:
                for i in range(40):
                    r = fila(i, "score", k=5, tarea="demo/s5")
                    r["split"] = "dev"
                    f.write(json.dumps(r) + "\n")
                for i in range(40, 45):                       # train: no entra
                    f.write(json.dumps({**fila(i, "score", k=5, tarea="demo/s5"), "split": "train"}) + "\n")
            filas = O.filas_dev_meta(d / "meta", 30)
            self.assertEqual(len(filas), 30)
            self.assertEqual({r["split"] for r in filas}, {"dev"})
            torch.save({"modelo": ModeloL2().state_dict(), "cabezas": [], "max_tok": 48}, d / "m.pt")
            with mock.patch("model.l2.modelo.Codificador", lambda **kw: enc):
                rc = O.main(["--ckpt", str(d / "m.pt"), "--jevbench", str(RAIZ_FX), "--meta", str(d / "meta"), "--salida", str(d / "o")])
            self.assertEqual(rc, 0)
            res = json.loads((d / "o" / "orientacion_score.json").read_text())
            self.assertEqual(res["errores_conversion"], [])
            self.assertEqual(res["meta"]["global"]["n"], 40)
            for v in O.VARIANTES:
                self.assertIn("exactitud_" + v, res["jevbench"]["global"])
            self.assertTrue(res["veredicto"])


if __name__ == "__main__":
    unittest.main()
