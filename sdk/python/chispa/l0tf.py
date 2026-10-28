"""L0 TF-IDF de caracteres para `chispa train --conjunta` (T4.5c): entrena el L0 de `model/lineas_base/correr.py`
(`correr_l0`, el mismo código) y lo escribe como sección L0TF.

`correr_l0` crea el vectorizador y la regresión dentro de la función y devuelve solo probabilidades; aquí se le
sustituyen las dos clases de sklearn por subclases que recuerdan lo que ajustan (y, si hay tope, fijan `max_features`),
así que no hay una segunda copia de los hiperparámetros que pueda divergir."""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

from . import formato
from .cliente import ChispaError

L0_MAX_MB = 48.0


@contextlib.contextmanager
def capturar(repo, max_features=None):
    """Mientras dura, `correr_l0` ajusta vectorizador y regresión y se guardan en el dict devuelto
    (`vec`, `clf`, el último ajuste). Con `max_features`, el vectorizador conserva solo los n-gramas más frecuentes."""
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    import sklearn.feature_extraction.text as T
    import sklearn.linear_model as M
    cap = {}

    class Vec(T.TfidfVectorizer):
        def fit_transform(self, raw, y=None):
            if max_features:
                self.max_features = int(max_features)
            cap["vec"] = self
            return super().fit_transform(raw, y)

    class LR(M.LogisticRegression):
        def fit(self, X, y, *a, **kw):
            cap["clf"] = self
            return super().fit(X, y, *a, **kw)

    antes = T.TfidfVectorizer, M.LogisticRegression
    T.TfidfVectorizer, M.LogisticRegression = Vec, LR
    try:
        yield cap
    finally:
        T.TfidfVectorizer, M.LogisticRegression = antes


def ajustar(train, repo, max_features=None):
    """(vectorizador, regresión) de `correr_l0` sobre las filas de `train` (dicts con `texto` y `etiqueta`)."""
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from model.lineas_base import correr as LB0
    with capturar(repo, max_features) as cap:
        LB0.correr_l0([(0, r) for r in train], [], None)
    return cap["vec"], cap["clf"]


def tamano_mb(v, c, f16):
    return v * c * (2 if f16 else 4) / 1e6


def elegir_tope(train, repo, f16, max_mb=L0_MAX_MB, log=print):
    """-> (max_features | None, vec, clf): ajusta sin tope y, si la tabla de coeficientes pasa de `max_mb`, vuelve a ajustar
    con el vocabulario podado por frecuencia hasta que cabe."""
    vec, clf = ajustar(train, repo)
    v, c = len(vec.vocabulary_), len(clf.classes_)
    if tamano_mb(v, c, f16) <= max_mb:
        return None, vec, clf
    mf = int(max_mb * 1e6 // (c * (2 if f16 else 4)))
    log(f"L0TF: {v} n-gramas × {c} clases = {tamano_mb(v, c, f16):.1f} MB; se poda a {mf} n-gramas (≤ {max_mb} MB)")
    vec, clf = ajustar(train, repo, mf)
    return mf, vec, clf


def seccion(vec, clf, f16=False) -> bytes:
    """Sección L0TF de un vectorizador y una regresión ya ajustados."""
    import numpy as np
    inv = vec.vocabulary_
    vocab = [None] * len(inv)
    for g, i in inv.items():
        vocab[i] = g
    clases = [str(x) for x in clf.classes_]
    coef, inter = np.asarray(clf.coef_, dtype=np.float64).T, np.asarray(clf.intercept_, dtype=np.float64)
    if len(clases) == 2 and coef.shape[1] == 1:  # sigmoide de sklearn → softmax de dos filas [0, w]
        coef, inter = np.hstack([np.zeros_like(coef), coef]), np.array([0.0, inter[0]])
    if f16 and np.abs(coef).max() > 65000:
        raise ChispaError("L0TF: coeficientes fuera del rango de f16")
    return formato.l0tf(clases, vocab, vec.idf_, inter, coef, f16)


def probs_fuera_de_pliegue(train, fold, repo, max_features, C):
    """Como `model.l2.conjunta.l0_fuera_de_pliegue`, con el mismo tope de vocabulario que el L0 que se despliega."""
    with capturar(repo, max_features):
        return C.l0_fuera_de_pliegue(train, fold)
