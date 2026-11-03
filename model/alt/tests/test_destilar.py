import gzip
import json
import tempfile
import unittest
from pathlib import Path

from model.alt import destilar
from model.alt.manifiesto import Manifiesto


def fila(i, tarea, split="train", n=3):
    ops = ["o%d" % k for k in range(n)]
    return {"id": "local:%d" % i, "split": split, "uso_comercial": True, "tarea": tarea, "tipo": "choice", "pregunta": "¿cuál?",
            "texto": "texto %d" % i, "opciones": ops, "descripciones": {}, "etiqueta": ops[0]}


class TestDestilar(unittest.TestCase):
    def test_distribucion_suma_uno_y_piso(self):
        letras = [101, 102, 103]
        d = destilar.distribucion({101: -0.1, 102: -2.5}, ["a", "b", "c"], letras)
        self.assertAlmostEqual(sum(d.values()), 1.0)
        self.assertGreater(d["a"], d["b"])
        self.assertLess(d["c"], 0.01)   # fuera del top: piso = mínimo − 5

    def test_elegir_respeta_tope_y_reescribir_solo_train(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "datos").mkdir()
            filas = [fila(i, "t%d" % (i % 2)) for i in range(10)] + [fila(99, "t0", "dev"), fila(98, "t1", n=30)]
            p = Path(t) / "datos" / "x.jsonl.gz"
            with gzip.open(p, "wt", encoding="utf-8") as f:
                f.write("".join(json.dumps(r) + "\n" for r in filas))
            m = Manifiesto({"conjuntos": [{"nombre": "x", "fuente": "propio", "licencia": "mit", "uso_comercial": True,
                                           "fichero": "datos/x.jsonl.gz"}]})
            el = destilar.elegir(m, t, 0, tope_tarea=3)
            self.assertEqual(len(el), 6)   # 3 por tarea; la de 30 opciones y la de dev fuera
            self.assertNotIn("local:98", {r["id"] for r in el})
            n = destilar.reescribir(m, t, {r["id"]: {"o0": 1.0} for r in el} | {"local:99": {"o0": 1.0}})
            self.assertEqual(n, 6)
            with gzip.open(p, "rt", encoding="utf-8") as f:
                leidas = [json.loads(l) for l in f]
            self.assertEqual(len(leidas), 12)
            self.assertNotIn("blanda", next(r for r in leidas if r["id"] == "local:99"))


if __name__ == "__main__":
    unittest.main()
