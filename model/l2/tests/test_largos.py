import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from model.l1 import frente_l2
from model.l2 import diag_score as DS
from model.l2 import largos as L

PREF = [101, 102]            # «query:» inventado de 2 tokens
RAIZ_FX = Path(__file__).resolve().parent / "fixtures_largos" / "jevbench"


def cuerpo(n):
    return list(range(1000, 1000 + n))


class Ventanas(unittest.TestCase):
    MAX = 40                 # b = 40 − 2 − 2 = 36

    def test_presupuesto(self):
        self.assertEqual(L.presupuesto(PREF, self.MAX), 36)
        with self.assertRaises(ValueError):
            L.presupuesto(PREF, 4)

    def test_corto_todas_iguales(self):
        c = cuerpo(36)
        for e in L.ESTRATEGIAS:
            self.assertEqual(L.ventanas(PREF, c, self.MAX, e), [PREF + c])
        self.assertFalse(L.es_largo(PREF, c, self.MAX))
        self.assertTrue(L.es_largo(PREF, cuerpo(37), self.MAX))

    def test_cabeza_y_cola(self):
        c = cuerpo(100)
        self.assertEqual(L.ventanas(PREF, c, self.MAX, "cabeza"), [PREF + c[:36]])
        self.assertEqual(L.ventanas(PREF, c, self.MAX, "cola"), [PREF + c[-36:]])

    def test_cabeza_cola_respeta_max_tok(self):
        for b_extra in (0, 1):                      # presupuesto par e impar
            max_tok = self.MAX + b_extra
            b = L.presupuesto(PREF, max_tok)
            for n in (b + 1, b + 7, 500):
                c = cuerpo(n)
                (w,) = L.ventanas(PREF, c, max_tok, "cabeza_cola")
                self.assertEqual(len(w) + 2, max_tok)           # con <s> y </s> llena max_tok exacto
                self.assertEqual(w[:2], PREF)
                t = b // 2
                self.assertEqual(w[2:2 + b - t], c[:b - t])      # la cabeza se queda con el impar
                self.assertEqual(w[2 + b - t:], c[-t:])
        self.assertEqual(L.ventanas(PREF, cuerpo(10), 5, "cabeza_cola"), [PREF + [1000]])   # b = 1: solo cabeza

    def test_trozos_tokenizacion(self):
        for n in (37, 68, 69, 100, 250):
            c = cuerpo(n)
            ws = L.ventanas(PREF, c, self.MAX, "trozos_max")
            self.assertEqual(ws, L.ventanas(PREF, c, self.MAX, "trozos_media"))
            self.assertTrue(all(w[:2] == PREF and len(w) <= self.MAX - 2 for w in ws))
            cuerpos = [w[2:] for w in ws]
            self.assertEqual(cuerpos[0][0], c[0])
            self.assertEqual(cuerpos[-1][-1], c[-1])                           # el último llega al final
            for a, b in zip(cuerpos, cuerpos[1:]):                              # solape exacto de 32 con el siguiente
                self.assertEqual(a[-L.SOLAPE:], b[:L.SOLAPE])
                self.assertEqual(len(a), 36)
            vistos = set(t for cu in cuerpos for t in cu)
            self.assertEqual(vistos, set(c))                                   # cubre todo el cuerpo
            self.assertEqual(len(ws), 1 + -(-(n - 36) // (36 - L.SOLAPE)))     # nº de trozos: ceil((n − b) / paso) + 1

    def test_trozos_limite(self):
        self.assertEqual(len(L.ventanas(PREF, cuerpo(36), self.MAX, "trozos_max")), 1)
        self.assertEqual(len(L.ventanas(PREF, cuerpo(37), self.MAX, "trozos_max")), 2)    # el 2.º lleva solo 1 token nuevo + 32 de solape
        self.assertEqual(L.ventanas(PREF, cuerpo(37), self.MAX, "trozos_max")[1][2:], cuerpo(37)[4:])

    def test_desconocida(self):
        with self.assertRaises(ValueError):
            L.ventanas(PREF, cuerpo(100), self.MAX, "nada")


class Agregacion(unittest.TestCase):
    def test_max_media_primera(self):
        s = torch.tensor([[1.0, 5.0], [3.0, 2.0], [2.0, 2.0]])
        self.assertEqual(L.agregar(s, "trozos_max").tolist(), [3.0, 5.0])
        self.assertEqual(L.agregar(s, "trozos_media").tolist(), [2.0, 3.0])
        self.assertEqual(L.agregar(s, "cabeza").tolist(), [1.0, 5.0])


class Estadistica(unittest.TestCase):
    def test_ic95(self):
        m, lo, hi = L.ic95([1] * 50 + [0] * 50)
        self.assertAlmostEqual(m, 0.5)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        self.assertEqual(L.ic95([1] * 10), (1.0, 1.0, 1.0))
        self.assertEqual(L.ic95([1, 0, 1, 1]), L.ic95([1, 0, 1, 1]))          # determinista

    def res(self, **kw):
        base = {"largos": {"n": 50, "acc": 0.5, "ic": [0.40, 0.60]}, "coste": 100.0}
        r = {"cabeza": base}
        for e, (acc, lo, hi, coste) in kw.items():
            r[e] = {"largos": {"n": 50, "acc": acc, "ic": [lo, hi]}, "coste": coste}
        return r

    def test_recomendar(self):
        self.assertEqual(L.recomendar(self.res(cola=(0.8, 0.7, 0.9, 100)))[0], "cola")                 # gana: IC sin solape
        self.assertEqual(L.recomendar(self.res(cola=(0.62, 0.5, 0.74, 100)))[0], "cabeza")             # solapa y no es más barata
        self.assertEqual(L.recomendar(self.res(trozos_max=(0.9, 0.8, 0.95, 2000)))[0], "trozos_max")   # gana aunque cueste más
        self.assertEqual(L.recomendar(self.res(cola=(0.5, 0.4, 0.6, 50)))[0], "cola")                  # empata y es más barata
        self.assertEqual(L.recomendar(self.res(cola=(0.3, 0.2, 0.39, 10)))[0], "cabeza")               # peor: no es un empate
        r = self.res(cola=(0.8, 0.7, 0.9, 100), trozos_max=(0.85, 0.75, 0.95, 2000))
        self.assertEqual(L.recomendar(r)[0], "trozos_max")
        r["cabeza"]["largos"]["n"] = 0
        self.assertEqual(L.recomendar(r)[0], "cabeza")


class ConModelo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("ONEDNN_MAX_CPU_ISA", "AVX2")
        from model.evaluacion.jevbench import cargar_jevbench
        from model.l2.exportar import modelo_aleatorio
        from model.l2.modelo import Codificador
        cls.filas = cargar_jevbench(RAIZ_FX)
        cls.modelo = modelo_aleatorio()
        cls.enc = Codificador(max_tok=48)

    def test_cabeza_igual_al_truncado_del_tokenizador(self):
        tok = self.enc.tok
        for r in self.filas[:30]:
            pref, c = L.tokenizar(tok, r["texto"])
            (w,) = L.ventanas(pref, c, 48, "cabeza")
            esperado = tok("query: " + r["texto"], truncation=True, max_length=48)["input_ids"]
            self.assertEqual(L.con_especiales(tok, w), esperado)
            self.assertLessEqual(len(esperado), 48)

    def test_cabeza_cola_y_trozos_con_el_tokenizador_real(self):
        tok = self.enc.tok
        largo = max(self.filas, key=lambda r: len(r["texto"]))
        pref, c = L.tokenizar(tok, largo["texto"])
        self.assertEqual(len(pref), 3)                       # «▁que», «ry», «:»
        for r in self.filas:                                 # el prefijo es siempre el comienzo de la tokenización completa
            ids = tok("query: " + r["texto"], add_special_tokens=False)["input_ids"]
            self.assertEqual(ids, L.tokenizar(tok, r["texto"])[0] + L.tokenizar(tok, r["texto"])[1])
            self.assertEqual(L.tokenizar(tok, r["texto"])[0], tok("query:", add_special_tokens=False)["input_ids"])
        self.assertGreater(len(c), 100)
        (w,) = L.ventanas(pref, c, 48, "cabeza_cola")
        self.assertEqual(len(L.con_especiales(tok, w)), 48)
        for w in L.ventanas(pref, c, 48, "trozos_max"):
            self.assertLessEqual(len(L.con_especiales(tok, w)), 48)

    def test_corto_igual_que_forward(self):
        """Con un texto que cabe, la ruta por ids da las probabilidades de `ModeloL2.forward` (k = 0), con las tres cabezas."""
        from model.evaluacion.jevbench_l2 import _con_tarea_esquema
        for tipo in ("choice", "noul", "score"):
            r = next(x for x in self.filas if x["tipo"] == tipo and len(x["texto"].split()) < 15)
            p = L.predecir_estrategias(self.modelo, self.enc, r, max_tok=48)
            self.assertFalse(p["largo"])
            with torch.no_grad():
                ref, _ = self.modelo([_con_tarea_esquema([r])[0]], self.enc, entrenar=False)
            ref = ref[0].double()
            ref = (ref / ref.sum()).tolist()
            for e in L.ESTRATEGIAS:
                np.testing.assert_allclose(list(p["por"][e]["probs"].values()), ref, atol=1e-5)

    def test_resumen_y_largos(self):
        filas = [r for r in self.filas][:20]
        preds = {r["id"]: L.predecir_estrategias(self.modelo, self.enc, r, max_tok=48) for r in filas}
        res = L.resumir(filas, preds)
        n_largos = sum(p["largo"] for p in preds.values())
        self.assertGreater(n_largos, 0)
        self.assertEqual(res["cabeza"]["largos"]["n"], n_largos)
        self.assertEqual(res["cabeza"]["coste"], 48.0)
        self.assertGreater(res["trozos_max"]["coste"], 48.0)
        self.assertEqual(res["trozos_max"]["largos"]["acc"] >= 0, True)
        rec = L.recomendar(res)
        self.assertIn(rec[0], L.ESTRATEGIAS)
        self.assertIn("cabeza", L.informe_md(res, rec, len(filas), n_largos, 48))


class DiagScore(unittest.TestCase):
    def test_oraculo(self):
        s = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
        n, th = DS.oraculo(s, [0, 0, 1, 1, 2, 2], 3)
        self.assertEqual(n, 6)
        self.assertEqual(len(th), 2)
        self.assertAlmostEqual(th[0], 0.25)
        self.assertAlmostEqual(th[1], 0.45)
        n, _ = DS.oraculo(s, [2, 2, 1, 1, 0, 0], 3)               # al revés: lo mejor monótono es acertar una clase
        self.assertEqual(n, 2)
        n, _ = DS.oraculo([1.0, 1.0, 1.0], [0, 1, 1], 2)           # empates: no se pueden separar
        self.assertEqual(n, 2)

    def test_spearman(self):
        self.assertAlmostEqual(DS.spearman([1, 2, 3, 4], [0, 1, 1, 2]), 0.94868, places=4)
        self.assertTrue(np.isnan(DS.spearman([1, 2, 3], [1, 1, 1])))

    def test_reajuste_recupera_umbrales(self):
        rng = np.random.RandomState(0)
        y = rng.randint(0, 4, 400)
        s = 0.2 * y + rng.normal(0, 0.03, 400) + 1.0                # el orden es bueno, pero los umbrales de partida no
        ini = {"w": 4.0, "theta": [2.0, 3.0, 4.0]}
        antes = (DS.etiqueta(s, ini) == y).mean()
        p = DS.ajustar_coral(s, y, 4, ini)
        despues = (DS.etiqueta(s, p) == y).mean()
        self.assertGreater(despues, antes + 0.2)
        self.assertEqual(p["theta"], sorted(p["theta"]))

    def test_veredicto(self):
        b = {"global": {"spearman_media_esquemas": 0.8, "oraculo": 0.8, "ckpt": 0.33, "loso": 0.7, "mayoria": 0.3}}
        causas, arreglo, _ = DS.veredicto(b)
        self.assertTrue(causas[0].startswith("calibración"))
        self.assertEqual(arreglo["donde"], "CPU (c6a.2xlarge)")
        b = {"global": {"spearman_media_esquemas": 0.05, "oraculo": 0.35, "ckpt": 0.33, "loso": 0.33, "mayoria": 0.3}}
        causas, arreglo, _ = DS.veredicto(b)
        self.assertTrue(causas[0].startswith("ranking"))
        self.assertEqual(arreglo["donde"], "GPU (g5.xlarge)")

    def test_censo_meta(self):
        import gzip
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "tsjev").mkdir()
            with gzip.open(Path(d) / "tsjev" / "train-00000.jsonl.gz", "wt") as f:
                for i in range(30):
                    f.write(json.dumps({"id": "tsjev:train:%d" % i, "split": "train", "tarea": "demo/s5", "tipo": "score", "opciones": list("12345")}) + "\n")
                for i in range(10):
                    f.write(json.dumps({"id": "tsjev:train:s%d" % i, "split": "train", "tarea": "demo/s3", "tipo": "score", "opciones": list("123")}) + "\n")
                for i in range(40):
                    f.write(json.dumps({"id": "tsjev:train:c%d" % i, "split": "train", "tarea": "demo/c", "tipo": "choice", "opciones": ["a", "b"]}) + "\n")
                f.write(json.dumps({"id": "tsjev:dev:1", "split": "dev", "tarea": "demo/s5", "tipo": "score", "opciones": list("12345")}) + "\n")
            c = DS.censo_meta(d, tope=25)
        self.assertEqual(c["tareas_score"], 2)
        self.assertEqual(c["por_k"]["K=5"]["bruto"] + c["por_k"]["K=3"]["bruto"], 40)           # el dev no cuenta
        self.assertLessEqual(c["por_k"].get("K=5", {"con_tope": 0})["con_tope"], 25)
        self.assertEqual(c["por_k"]["K=5"]["bruto"], 30)

    def test_censo_conversion(self):
        c = DS.censo_conversion()
        self.assertEqual(c["fuentes_con_score"], ["tsjev"])
        self.assertGreater(c["score_por_split"]["train"], 1000)

    def test_de_punta_a_punta(self):
        os.environ.setdefault("ONEDNN_MAX_CPU_ISA", "AVX2")
        from model.l2.exportar import modelo_aleatorio
        with tempfile.TemporaryDirectory() as d:
            ck = Path(d) / "mejor.pt"
            torch.save({"modelo": modelo_aleatorio().state_dict(), "cabezas": [], "max_tok": 64}, ck)
            self.assertEqual(DS.main(["--ckpt", str(ck), "--jevbench", str(RAIZ_FX), "--salida", d + "/o"]), 0)
            r = json.loads((Path(d) / "o" / "diag_score.json").read_text())
            self.assertEqual(r["casos"]["global"]["n"], 72)
            self.assertTrue(all(e["reajustado"] for e in r["casos"]["por_esquema"].values() if e["k"] == 4))


class FrenteL2(unittest.TestCase):
    def test_razon_y_resumen(self):
        self.assertAlmostEqual(frente_l2.razon(0.9, 1.0), 0.9)
        self.assertIsNone(frente_l2.razon(0.5, 0.0))
        t = {"a": {"k": {"razon": 0.95}}, "b": {"k": {"razon": 0.80}}, "c": {"k": {"razon": None}}}
        r = frente_l2.resumen(t)
        self.assertAlmostEqual(r["media"], 0.875)
        self.assertFalse(r["cumple"])
        self.assertEqual((r["tareas_bajo_criterio"], r["tareas_sin_razon"], r["n_tareas"]), (["b"], ["c"], 2))
        t["b"]["k"]["razon"] = 0.9
        self.assertTrue(frente_l2.resumen(t)["cumple"])


if __name__ == "__main__":
    unittest.main()
