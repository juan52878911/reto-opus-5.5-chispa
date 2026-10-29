"""Clave v2 de esquema (HashEsquema2) y ESQUEMAS/CONJ v2: Python escribe los mismos bytes que Go.

Regenerar el fichero que lee Go:  python -m tests.test_claves_v2 --gen   (desde sdk/python)"""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

from chispa import formato

TESTDATA = Path(__file__).resolve().parents[3] / "format/chispa3/testdata"
VECTORES = TESTDATA.parent / "vectores-clave-v2.json"


def vectores():
    return json.loads(VECTORES.read_text(encoding="utf-8"))["vectores"]


def secciones():
    """La misma receta que seccionesClavesV2 en format/chispa3/claves_v2_fichero_test.go."""
    es, cs, vistos = [], [], set()
    for i, v in enumerate(vectores()):
        if v["hash"] in vistos:
            continue
        vistos.add(v["hash"])
        h = bytes.fromhex(v["hash"])
        es.append({"hash": h, "escala": 0.5 * (i + 1), "vec": np.array([i + 1, -(i + 1), 2, -2], dtype=np.int8)})
        ids = sorted(o["id"] for o in v["opciones"])
        c = len(ids)
        proto = (np.arange(c * 4) + 1 - 4).astype(np.int8).reshape(c, 1, 4)
        cs.append({"hash": h, "T": 0.05, "beta": 1.0, "esc": [1, 1, 1], "w": [1, 0.5, 0.25, 0, 0, 0], "clases": ids,
                   "escala": np.full((c, 1), 0.5, dtype=np.float32), "proto": proto})
    return {formato.ESQUEMAS: formato.esquemas(4, es, version=2), formato.CONJ: formato.conj(cs, version=2)}


class TestClavesV2(unittest.TestCase):
    def test_vectores(self):
        vs = vectores()
        self.assertGreaterEqual(len(vs), 4)
        for v in vs:
            h = formato.hash_esquema2(v["pregunta"], v["kind"], [(o["id"], o["description"]) for o in v["opciones"]])
            self.assertEqual(h.hex(), v["hash"], v["nombre"])

    def test_orden_descripcion_y_kind(self):
        a = formato.hash_esquema2("q", "choice", [("a", "x"), ("b", "y")])
        self.assertEqual(a, formato.hash_esquema2("q", "choice", [("b", "y"), ("a", "x")]))
        self.assertNotEqual(a, formato.hash_esquema2("q", "choice", [("a", "z"), ("b", "y")]))
        self.assertNotEqual(a, formato.hash_esquema2("q", "multi", [("a", "x"), ("b", "y")]))

    def test_v1_intacto(self):
        e = formato.esquemas(2, [{"hash": formato.hash_esquema("q", ["a"]), "escala": 1.0, "vec": [1, 2]}])
        self.assertEqual(e[:8], bytes([2, 0, 0, 0, 1, 0, 0, 0]))  # dim sola: sin versión
        self.assertEqual(formato.conj([], version=1)[:4], bytes([1, 0, 0, 0]))
        with self.assertRaises(ValueError):
            formato.conj([], version=3)

    def test_fichero_escrito_por_python_es_el_que_lee_go(self):
        self.assertEqual(TESTDATA.joinpath("claves-v2.chispa").read_bytes(), formato.escribir(secciones()))

    def test_fichero_v2_escrito_por_go(self):
        got = formato.leer((TESTDATA / "claves-v2-go.chispa").read_bytes())
        self.assertEqual(got[formato.ESQUEMAS], secciones()[formato.ESQUEMAS])
        self.assertEqual(got[formato.CONJ], secciones()[formato.CONJ])


if __name__ == "__main__":
    if sys.argv[1:] == ["--gen"]:
        (TESTDATA / "claves-v2.chispa").write_bytes(formato.escribir(secciones()))
    else:
        unittest.main()
