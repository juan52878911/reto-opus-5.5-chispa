"""Cabeza conjunta L0 + L2 para `chispa train --conjunta` (T2.6b): calcula las características con `model/l2/conjunta.py`
(L0 fuera de pliegue y prototipos de L2 sin la propia fila), ajusta la cabeza `lr` y devuelve la sección CONJ.

Necesita el repositorio (`model.l2`), torch, sklearn y el checkpoint de L2."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from . import formato
from . import l0tf as L0
from .cliente import ChispaError

SOPORTE = 32


def filas_train(q, ejemplos):
    """Filas en el formato de `model/l2` (las de `train._filas_l2`, con split train y un id estable por posición)."""
    desc = {o.id: o.description for o in q.options}
    return [{"id": f"sdk:train:{i}", "tarea": q.id, "tipo": q.kind, "pregunta": q.question, "texto": t,
             "opciones": [o.id for o in q.options], "descripciones": desc, "etiqueta": e, "idioma": "es",
             "split": "train", "fuente": "chispa train", "licencia": "propia", "uso_comercial": True}
            for i, (t, e) in enumerate(ejemplos)]


def seccion_conj(q, ejemplos, modelo, enc, repo, log=print, l0tf_f16=False, l0tf_max_mb=L0.L0_MAX_MB):
    """-> (bytes de CONJ, bytes de L0TF, informe). `modelo` y `enc` son el ModeloL2 y el Codificador (el checkpoint de `--ckpt`)."""
    if q.kind != "choice":
        raise ChispaError(f"--conjunta solo sirve para preguntas choice (esta es {q.kind})")
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    import numpy as np
    import torch
    from model.l2 import conjunta as C
    from model.l2 import datos as D
    from model.l2.modelo import prototipos

    train = filas_train(q, ejemplos)
    log(f"conjunta: L0 tfidf, L0 fuera de pliegue ({C.PLIEGUES} pliegues) y L2 con soporte sobre {len(train)} ejemplos")
    t0 = time.time()
    # El L0 que se despliega (L0TF) es el mismo que alimenta a la cabeza: mismo código que correr_l0, mismo tope de vocabulario.
    mf, vec, clf = L0.elegir_tope(train, repo, l0tf_f16, l0tf_max_mb, log)
    if list(clf.classes_) != sorted(o.id for o in q.options):
        raise ChispaError("--conjunta: todas las opciones del esquema necesitan ejemplos para entrenar L0")
    b_l0 = L0.seccion(vec, clf, l0tf_f16)
    fold = C.pliegues(train)
    sop = [r for _, r in D.soporte_t17a(train, SOPORTE, C.SEMILLA)]
    c = {"tr_fold": np.array(fold), "tr_y": np.array([r["opciones"].index(r["etiqueta"]) for r in train])}
    c["tr_l0"] = L0.probs_fuera_de_pliegue(train, fold, repo, mf, C)
    t_l0 = time.time() - t0
    c["tr_sp"], c["tr_l2"] = C.l2_train(modelo, enc, train, sop)
    (_, lam), _, tabla = C.elegir(c, cabezas=("lr",))
    cab = C.Cabeza("lr", lam).ajustar(c["tr_l0"], c["tr_sp"], c["tr_l2"], c["tr_y"])
    idx, P = prototipos(modelo, enc, sop)  # (C,K,d), clases en orden de nombre
    clases = sorted(idx, key=idx.get)
    escala, proto = formato.cuantizar_protos(P.detach().cpu().numpy())
    T = float(modelo.log_t["choice"].detach().exp().clamp(min=5e-3))
    e = {"hash": formato.hash_esquema(q.question, sorted(o.id for o in q.options)), "T": T,
         "beta": float(modelo.beta["choice"].detach()), "esc": [float(x) for x in cab.esc],
         "w": [float(x) for x in cab.w.numpy()], "clases": clases, "escala": escala, "proto": proto}
    b = formato.conj([e])
    return b, b_l0, {"l0tf": {"ngramas": len(vec.vocabulary_), "max_features": mf, "bytes": len(b_l0), "f16": l0tf_f16, "s": t_l0},
                     "lambda": lam, "cv_nll": {str(k): v for k, v in tabla["lr"].items()}, "bytes": len(b), "clases": len(clases),
               "T": T, "beta": e["beta"]}


def cargar_ckpt(ckpt, repo):
    """(ModeloL2, Codificador) de un checkpoint de `model/l2`, en CPU."""
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from model.l2.calibrar import cargar_modelo
    from model.l2.modelo import Codificador
    modelo, _ = cargar_modelo(ckpt, "cpu")
    return modelo, Codificador(device="cpu")
