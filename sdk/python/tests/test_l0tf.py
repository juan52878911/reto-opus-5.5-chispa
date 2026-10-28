import struct
import unittest

import numpy as np

from chispa import formato, l0tf
from chispa.train import encontrar_repo
from tests import fixture_l0tf as fx

REPO = encontrar_repo()


@unittest.skipUnless(REPO, "sin repositorio")
class TestL0TF(unittest.TestCase):
    def test_captura_el_mismo_ajuste_que_correr_l0(self):
        train, test = fx.datos()
        vec, clf = l0tf.ajustar(train, REPO)
        from model.lineas_base import correr as LB0
        filas = [{"texto": t, "opciones": list(clf.classes_)} for t in test[:20]]
        ref, _ = LB0.correr_l0([(0, r) for r in train], filas, None)
        np.testing.assert_allclose(clf.predict_proba(vec.transform([r["texto"] for r in filas])), np.array(ref), atol=1e-15)
        self.assertEqual((vec.analyzer, vec.ngram_range, vec.sublinear_tf, vec.lowercase), ("char_wb", (2, 5), True, True))

    def test_el_fixture_guardado_es_el_que_se_genera(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            fx.generar(Path(d), REPO)
            for f in ("modelo.l0tf", "modelo_f16.l0tf", "frases.json"):
                self.assertEqual((Path(d) / f).read_bytes(), (REPO / "server/decide/testdata/l0tf" / f).read_bytes(), f)

    def test_poda_por_frecuencia(self):
        train, _ = fx.datos()
        vec, _ = l0tf.ajustar(train, REPO, 300)
        self.assertEqual(len(vec.vocabulary_), 300)
        mf, vec, clf = l0tf.elegir_tope(train, REPO, False, max_mb=300 * 6 * 4 / 1e6, log=lambda m: None)
        self.assertEqual((mf, len(vec.vocabulary_)), (300, 300))
        self.assertIsNone(l0tf.elegir_tope(train, REPO, False, log=lambda m: None)[0])

    def test_seccion_ordena_por_bytes_y_cuadra_con_el_modelo(self):
        train, _ = fx.datos()
        vec, clf = l0tf.ajustar(train, REPO)
        b = l0tf.seccion(vec, clf, False)
        v, c = len(vec.vocabulary_), len(clf.classes_)
        self.assertEqual(struct.unpack("<IIII", b[:16]), (1, v, c, 1))
        self.assertEqual(len(b), 16 + sum(2 + len(str(x).encode()) for x in clf.classes_) + 4 * c + 4 * v + 4 * (v + 1)
                         + sum(len(g.encode()) for g in vec.vocabulary_) + 4 * v * c)
        self.assertEqual(len(l0tf.seccion(vec, clf, True)), len(b) - 2 * v * c)

    def test_dos_clases_se_expande_a_softmax(self):
        train, test = fx.datos()
        train = [r for r in train if r["etiqueta"] in ("cuenta", "envíos")]
        vec, clf = l0tf.ajustar(train, REPO)
        self.assertEqual(clf.coef_.shape[0], 1)
        b = l0tf.seccion(vec, clf, False)
        self.assertEqual(struct.unpack("<III", b[4:16])[1], 2)

    def test_formato_rechaza(self):
        base = dict(etiquetas=["a", "b"], vocab=["ab", "ba"], idf=[1, 1], inter=[0, 0], coef=np.zeros((2, 2)))
        formato.l0tf(**base)
        for cambio in ({"etiquetas": ["b", "a"]}, {"vocab": ["ab", "ab"]}, {"vocab": ["a", "ba"]}, {"etiquetas": ["a"]},
                       {"vocab": ["abcdef", "ba"]}):
            with self.assertRaises(ValueError):
                formato.l0tf(**{**base, **cambio})


if __name__ == "__main__":
    unittest.main()
