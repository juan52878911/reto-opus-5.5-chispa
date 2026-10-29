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
MIN_OOF = 200  # filas fuera de pliegue mínimas para fijar el τ de L2c
MIN_SOPORTE_TAU = 10
MIN_VALID = 50    # filas de validación mínimas para fijar el τ sobre ellas
MARGEN = 0.02     # H2: el τ fuera de pliegue se fija para precisión objetivo + margen
SUELO_FUERA = 0.05  # H2: suelo de τ = el que deja fuera esta fracción fuera de pliegue


def tau_l2c(p, y, objetivo):
    """τ de L2c con las probabilidades fuera de pliegue `p` (n,C) y las etiquetas `y`: el menor τ cuya precisión en lo aceptado
    (conf >= τ) es >= `objetivo` (el prefijo más largo por confianza que lo cumple, con soporte mínimo).
    -> (τ o None si no hay ninguno, precisión aceptada, cobertura)."""
    import numpy as np
    conf, ok = p.max(1), p.argmax(1) == y
    orden = np.argsort(-conf, kind="stable")
    buenos = np.cumsum(ok[orden])
    r = np.arange(1, len(orden) + 1)
    cumple = np.flatnonzero((r >= MIN_SOPORTE_TAU) & (buenos / r >= objetivo))
    if not len(cumple):
        return None, 0.0, 0.0
    tau = float(conf[orden[cumple[-1]]])
    acept = conf >= tau
    return tau, float(ok[acept].mean()), float(acept.mean())


def _en_tau(p, y, tau):
    """(precisión, cobertura) de lo aceptado con conf >= `tau`."""
    conf, ok = p.max(1), p.argmax(1) == y
    acept = conf >= tau
    return (float(ok[acept].mean()) if acept.any() else 0.0), float(acept.mean())


def elegir_tau(po, y, objetivo, validacion=None, margen=MARGEN, suelo=SUELO_FUERA):
    """τ de L2c -> dict(metodo, tau, precision, cobertura) o `tau` None si ninguno cumple.
    `validacion` = (p, y) de filas que la cabeza no vio: τ de precisión `objetivo` sobre ellas (método «validacion»).
    Si no (o son < MIN_VALID), con las probabilidades fuera de pliegue `po`: el mayor entre el τ de precisión `objetivo + margen` y el
    τ que deja fuera la fracción `suelo` de filas (método «fuera_de_pliegue+margen»)."""
    import numpy as np
    if validacion is not None and len(validacion[1]) >= MIN_VALID:
        tau, prec, cob = tau_l2c(validacion[0], validacion[1], objetivo)
        return {"metodo": "validacion", "tau": tau, "precision": prec, "cobertura": cob, "filas": len(validacion[1])}
    tau, _, _ = tau_l2c(po, y, min(objetivo + margen, 0.999))
    if tau is None:
        return {"metodo": "fuera_de_pliegue+margen", "tau": None, "precision": 0.0, "cobertura": 0.0, "filas": len(y)}
    tau = max(tau, float(np.quantile(po.max(1), suelo)))
    prec, cob = _en_tau(po, y, tau)
    return {"metodo": "fuera_de_pliegue+margen", "tau": tau, "precision": prec, "cobertura": cob, "filas": len(y)}


def probs_fuera_de_pliegue_cabeza(C, c, lam, k):
    """Probabilidades de la cabeza `lr` (λ=`lam`) sobre train, cada fila con la cabeza ajustada en los demás pliegues -> (n,C)."""
    import numpy as np
    f = c["tr_fold"]
    out = np.full(c["tr_l0"].shape, np.nan)
    for j in range(k):
        va, tr = f == j, f != j
        if not va.any() or not tr.any():
            continue
        h = C.Cabeza("lr", lam).ajustar(c["tr_l0"][tr], c["tr_sp"][tr], c["tr_l2"][tr], c["tr_y"][tr])
        out[va] = h.probs(c["tr_l0"][va], c["tr_sp"][va], c["tr_l2"][va])
    return out


def filas_train(q, ejemplos):
    """Filas en el formato de `model/l2` (las de `train._filas_l2`, con split train y un id estable por posición)."""
    desc = {o.id: o.description for o in q.options}
    return [{"id": f"sdk:train:{i}", "tarea": q.id, "tipo": q.kind, "pregunta": q.question, "texto": t,
             "opciones": [o.id for o in q.options], "descripciones": desc, "etiqueta": e, "idioma": "es",
             "split": "train", "fuente": "chispa train", "licencia": "propia", "uso_comercial": True}
            for i, (t, e) in enumerate(ejemplos)]


def seccion_conj(q, ejemplos, modelo, enc, repo, log=print, l0tf_f16=False, l0tf_max_mb=L0.L0_MAX_MB, precision_objetivo=0.95,
                 validacion=None, margen=MARGEN, suelo=SUELO_FUERA):
    """-> (bytes de CONJ, bytes de L0TF, informe; `informe["tau_l2c"]` es el τ de L2c o None). `modelo` y `enc` son el ModeloL2 y el Codificador (el checkpoint de `--ckpt`).
    `validacion` = [(texto, etiqueta)] que no están en `ejemplos`: el τ de L2c se elige sobre ellas con la cabeza ya ajustada en todo train."""
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
    po = probs_fuera_de_pliegue_cabeza(C, c, lam, C.PLIEGUES)
    ok = ~np.isnan(po).any(1)
    tau = prec = cob = metodo = None
    if int(ok.sum()) < MIN_OOF:
        log(f"AVISO: solo {int(ok.sum())} filas fuera de pliegue (< {MIN_OOF}): τ de L2c de CALIB, no el de la cabeza conjunta")
    else:
        val = None
        if validacion:
            opc = {o.id for o in q.options}
            vf = [f for f in filas_train(q, [(t, e) for t, e in validacion if e in opc])]
            if len(vf) < MIN_VALID:
                log(f"AVISO: solo {len(vf)} filas de validación utilizables (< {MIN_VALID}): τ fuera de pliegue con margen")
            else:
                for i, f in enumerate(vf):
                    f["id"], f["split"] = f"sdk:valid:{i}", "dev"
                with L0.capturar(repo, mf):  # el L0 que se despliega, ajustado en todo train
                    v0, _ = C.probs_l0(train, vf)
                vsp, vl2, _ = C.l2_filas(modelo, enc, vf, prototipos(modelo, enc, sop))
                val = (cab.probs(v0, vsp, vl2), np.array([f["opciones"].index(f["etiqueta"]) for f in vf]))
        r = elegir_tau(po[ok], c["tr_y"][ok], precision_objetivo, val, margen, suelo)
        tau, prec, cob, metodo = r["tau"], r["precision"], r["cobertura"], r["metodo"]
        if tau is None:
            log(f"AVISO: ningún τ da precisión {precision_objetivo} ({metodo}): τ de L2c de CALIB")
        else:
            log(f"conjunta: τ de L2c {tau:.4f} por {metodo} sobre {r['filas']} filas (precisión esperada {prec:.3f}, cobertura esperada {cob:.3f})")
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
               "T": T, "beta": e["beta"],
               "tau_l2c": tau, "precision_oof": prec, "precision_esperada": prec, "metodo_tau": metodo, "cobertura_esperada": cob, "precision_objetivo": precision_objetivo,
               "filas_oof": int(ok.sum())}


def cargar_ckpt(ckpt, repo):
    """(ModeloL2, Codificador) de un checkpoint de `model/l2`, en CPU."""
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from model.l2.calibrar import cargar_modelo
    from model.l2.modelo import Codificador
    modelo, _ = cargar_modelo(ckpt, "cpu")
    return modelo, Codificador(device="cpu")
