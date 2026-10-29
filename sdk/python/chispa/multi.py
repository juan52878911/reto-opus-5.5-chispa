"""`chispa train` para preguntas multietiqueta (`tipo: multi`): cada opción es un sí/no independiente.

Los ejemplos llevan varias etiquetas separadas por `|` (o ninguna: celda vacía). L0 no se entrena: el lineal es multiclase (sus
probabilidades suman 1) y no da una probabilidad por opción, así que en multi no opina (el contrato de /v1/decide lo dice). Lo que
sí se aprende de los ejemplos, en L1/L2:
  - SOPL1: por opción, k y la media de los embeddings de los ejemplos donde está activa (encogimiento del prototipo, como en choice);
  - CALIB: la sigmoide σ(a·coseno + b) de multi (a y b globales) y un umbral θ por opción que maximiza F1. Las claves llevan el esquema:
    `multi@<hex>` y `multi@<hex>#<id>` (hex = HashEsquema2 de la pregunta con sus opciones): valen solo para este esquema. Las claves
    sin esquema (`multi`, `multi#<id>`) son de ficheros antiguos y el servidor las sigue leyendo si el fichero no trae ninguna con esquema.
  - CALIB de L2: `multi_l2@<hex>` y `multi_l2@<hex>#<id>` (mismos campos), ajustadas con el MaxSim de L2 (otra escala que el coseno de
    L1). Solo se escriben si se da `maxsim_l2`. `chispa train` no lo construye en esta instalación (hace falta el tokenizador y la sesión
    ONNX de L2 con torres al vuelo, que solo existen en Go): sin ellas L2 NO opina en multi y la cascada escala (servidor y móvil).
Sin ejemplos es zero-shot (como choice): CALIB sin multi y el servidor usa la de noul como aproximación."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import formato
from .cliente import ChispaError
from .datos import cargar_ejemplos, validar_multi

MIN_POS_THETA = 3      # positivos (y negativos) mínimos de una opción para darle un θ propio
THETA_MIN, THETA_MAX = 0.05, 0.95
T_MULTI = 0.05         # la «T» de CALIB (no se usa en multi; solo debe ser > 0)


def sufijo_esquema(q) -> str:
    """«@» + HashEsquema2 (pregunta, «multi», opciones con descripción) en hex: el sufijo de las claves de CALIB de multi
    (`server/decide.ClaveCalibMulti`). Así una opción «si» de otro esquema no hereda el θ ni la a, b de este."""
    return "@" + formato.hash_esquema2(q.question, "multi", [(o.id, o.description or "") for o in q.options]).hex()


def texto_opcion(q, o) -> str:
    """El texto de la torre de L1 de una opción: «pregunta · opción · descripción» (server/decide.textoOpcion)."""
    return " · ".join([q.question, o.id] + ([o.description] if o.description else []))


def _sigmoide(z):
    import numpy as np
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))


def ajustar_sigmoide(s, y, iteraciones: int = 100, l2: float = 1e-3) -> Tuple[float, float]:
    """a, b de σ(a·s + b) por Newton (regresión logística de una variable con un ridge mínimo en `a`). s, y: vectores de igual longitud."""
    import numpy as np
    s, y = np.asarray(s, dtype=np.float64), np.asarray(y, dtype=np.float64)
    a, b = 0.0, float(np.log((y.mean() + 1e-6) / (1 - y.mean() + 1e-6)))
    for _ in range(iteraciones):
        p = _sigmoide(a * s + b)
        w = np.maximum(p * (1 - p), 1e-9)
        g = np.array([((p - y) * s).sum() + l2 * a, (p - y).sum()])
        h = np.array([[(w * s * s).sum() + l2, (w * s).sum()], [(w * s).sum(), w.sum()]])
        paso = np.linalg.solve(h, g)
        a, b = a - paso[0], b - paso[1]
        if np.abs(paso).max() < 1e-9:
            break
    return float(a), float(b)


def mejor_theta(p, y) -> float:
    """θ en [THETA_MIN, THETA_MAX] que maximiza F1 de la opción (el candidato más bajo en empate)."""
    import numpy as np
    p, y = np.asarray(p), np.asarray(y).astype(bool)
    mejor, f_mejor = 0.5, -1.0
    for th in sorted(set(np.clip(p, THETA_MIN, THETA_MAX).tolist() + [0.5])):
        pred = p >= th
        tp = float((pred & y).sum())
        f = 2 * tp / max(float(pred.sum() + y.sum()), 1.0)
        if f > f_mejor + 1e-12:
            mejor, f_mejor = th, f
    return float(mejor)


def _ajustar_capa(clave, ops, sims, Y) -> Tuple[Dict[str, dict], float, float]:
    a, b = ajustar_sigmoide(sims.ravel(), Y.ravel())
    tipos = {clave: {"T": T_MULTI, "a": a, "b": b, "theta": 0.5}}
    P_ = _sigmoide(a * sims + b)
    for j, o in enumerate(ops):
        pos = int(Y[:, j].sum())
        if pos >= MIN_POS_THETA and len(Y) - pos >= MIN_POS_THETA:
            tipos[clave + "#" + o.id] = {"T": T_MULTI, "a": a, "b": b, "theta": mejor_theta(P_[:, j], Y[:, j])}
    return tipos, a, b


def calibrar_multi(q, ex, embeber, maxsim_l2=None) -> Tuple[Dict[str, dict], dict]:
    """CALIB.tipos de multi y un informe, de los ejemplos `ex` ([(texto, etiquetas)]) y de `embeber(textos) → (E, ok)` (L1).
    `multi@<hex>` lleva a y b globales (θ 0,5) y `multi@<hex>#<id>` el θ de cada opción con suficientes positivos y negativos (puntuación: coseno de L1).
    Con `maxsim_l2(textos) → (S, ok)` (S (n, K): MaxSim de L2 de cada ejemplo con cada opción, en el orden de la pregunta) se ajusta lo
    mismo sobre esa puntuación y va en `multi_l2@<hex>` / `multi_l2@<hex>#<id>`. Sin variación en las etiquetas (todo activo o todo inactivo) no se
    puede ajustar: devuelve ({}, informe con el motivo)."""
    import numpy as np
    ops = list(q.options)
    textos = [texto_opcion(q, o) for o in ops] + [t for t, _ in ex]
    E, ok = embeber(textos)
    P, X, ok = E[:len(ops)], E[len(ops):], ok[len(ops):]
    sims = X @ P.T  # (n, K): coseno con el prototipo de la descripción
    Y_todo = np.array([[o.id in es for o in ops] for _, es in ex], dtype=bool)
    sims, Y = sims[ok], Y_todo[ok]
    inf = {"ejemplos": int(len(Y)), "positivos": {o.id: int(Y[:, j].sum()) for j, o in enumerate(ops)}}
    if len(Y) == 0 or Y.all() or not Y.any():
        inf["motivo"] = "sin variación: todas las etiquetas iguales (o ningún ejemplo que L1 pueda embeber)"
        return {}, inf
    tipos, a, b = _ajustar_capa("multi" + sufijo_esquema(q), ops, sims, Y)
    esq = sufijo_esquema(q)
    inf.update(a=a, b=b, thetas={k.split("#", 1)[1]: v["theta"] for k, v in tipos.items() if "#" in k})
    if maxsim_l2 is not None:
        S, ok2 = maxsim_l2([t for t, _ in ex])
        S, Y2 = np.asarray(S)[ok2], Y_todo[ok2]
        if len(Y2) == 0 or Y2.all() or not Y2.any():
            inf["motivo_l2"] = "multi_l2: sin variación en los ejemplos que L2 pueda puntuar; L2 usará la CALIB de noul"
        else:
            t2, a2, b2 = _ajustar_capa("multi_l2" + esq, ops, S, Y2)
            tipos.update(t2)
            inf["l2"] = {"a": a2, "b": b2, "thetas": {k.split("#", 1)[1]: v["theta"] for k, v in t2.items() if "#" in k}}
    return tipos, inf


def escribir_calib(salida: Path, tipos: Dict[str, dict]) -> None:
    """Pone `tipos` en la CALIB de `salida` (el resto de campos se conserva)."""
    secs = formato.leer(Path(salida).read_bytes())
    d = json.loads(secs[formato.CALIB])
    d.setdefault("tipos", {}).update(tipos)
    secs[formato.CALIB] = json.dumps(d).encode()
    Path(salida).write_bytes(formato.escribir(secs))


def entrenar_multi(ejemplos, q, extra, salida, *, l1=None, ckpt=None, l2=None, repo=None, shrinkage_lambda=None, sin_soporte=False,
                   embeber: Optional[Callable] = None, maxsim_l2: Optional[Callable] = None, log=print) -> dict:
    """Entrena un `.chispa` de una pregunta multi. Sin `ejemplos`: zero-shot (como choice). Con ellos: lo mismo más SOPL1 y la CALIB de
    multi (ver el docstring del módulo). Devuelve el informe de `entrenar`."""
    import time
    from . import train as T
    t0 = time.time()
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    if not ejemplos:
        inf = T._zero_shot(q, extra, l1, l2, ckpt, T.encontrar_repo(repo), salida, t0, log)
        inf["omitidas"]["L0"] = "multi: el L0 entrenado es multiclase y no da una probabilidad por opción"
        return inf
    ex = cargar_ejemplos(ejemplos, q.id, multi=True)
    cuenta = validar_multi(ex, q)
    log(f"{len(ex)} ejemplos multietiqueta, {sum(len(es) == 0 for _, es in ex)} sin etiquetas; positivos por opción {dict(sorted(cuenta.items()))}")
    inf = T._zero_shot(q, extra, l1, l2, ckpt, T.encontrar_repo(repo), salida, t0, log)
    inf["modo"] = "few-shot"
    inf["omitidas"]["L0"] = "multi: el L0 entrenado es multiclase y no da una probabilidad por opción"
    inf["omitidas"].pop("CALIB", None)
    inf["positivos"] = dict(cuenta)
    if not l1:
        log("AVISO: sin --l1 no se calibra multi ni se escribe SOPL1; el servidor usará la CALIB de noul como aproximación")
        inf["omitidas"]["SOPL1"] = "sin --l1"
        return inf
    lam = T.LAMBDA_L1_SUGERIDA if shrinkage_lambda is None else shrinkage_lambda
    with tempfile.TemporaryDirectory(prefix="chispa-multi-") as tmp:
        emb = embeber
        if emb is None:
            go, fuentes = T.encontrar_go(), T.fuentes_go(T.encontrar_repo(repo))
            if not (go and fuentes):
                log("AVISO: hace falta Go y las fuentes de runtime/l1 para embeber los ejemplos: sin CALIB de multi ni SOPL1")
                inf["omitidas"]["SOPL1"] = inf["omitidas"]["CALIB multi"] = "sin Go o sin fuentes de runtime/l1"
                return inf
            emb = lambda textos: T.embeber_con_go(l1, textos, fuentes, go, Path(tmp))
        tipos, cal = calibrar_multi(q, ex, emb, maxsim_l2)
        inf["calib_multi"] = cal
        if maxsim_l2 is None and (l2 or ckpt):
            inf.setdefault("avisos", []).append("sin `multi_l2`: no se puede calibrar el MaxSim de L2 aquí (hace falta el tokenizador y la sesión "
                                                "ONNX de L2, solo en Go); en multi L2 NO opinará y la cascada escalará (el servidor lo avisa en el log)")
            inf["omitidas"]["CALIB multi_l2"] = "sin maxsim_l2: L2 no opina en multi"
            log("AVISO: " + inf["avisos"][-1])
        if tipos:
            escribir_calib(salida, tipos)
            log(f"CALIB multi: a={cal['a']:.3f}, b={cal['b']:.3f}, θ propio en {sorted(cal['thetas']) or 'ninguna opción'} (claves con el esquema {sufijo_esquema(q)})")
        else:
            inf["omitidas"]["CALIB multi"] = cal["motivo"]
            log("AVISO: " + cal["motivo"] + ": multi usa la CALIB de noul")
        if not sin_soporte:
            plano = [(t, e) for t, es in ex for e in es]  # un par (texto, etiqueta) por etiqueta activa
            if plano:
                T.anadir_sopl1(salida, q, plano, l1, lam, inf, log, emb, repo, None, explicito=shrinkage_lambda is not None)
                # la CALIB de multi se ajustó con los prototipos de la descripción (sin encogimiento): no se declara calibrada con λ
                secs = formato.leer(salida.read_bytes())
                T._ajustar_l1_lambda_calib(secs, None)
                salida.write_bytes(formato.escribir(secs))
                (inf.get("calib") or {}).pop("l1_lambda_calib", None)
                inf.setdefault("avisos", []).append("SOPL1 escrita pero el servidor la IGNORA por defecto en multi: CALIB no lleva l1_lambda_calib (se "
                                                    "ajustó con los prototipos de la descripción, sin encogimiento), así que el soporte few-shot solo entra "
                                                    "si el operador fija l1_shrinkage_lambda; con λ finito las probabilidades cambian y λ = inf reproduce la calibración")
                log("AVISO: " + inf["avisos"][-1])
            else:
                inf["omitidas"]["SOPL1"] = "ningún ejemplo con etiquetas"
    inf["bytes"] = salida.stat().st_size
    inf["reloj_s"] = time.time() - t0
    return inf
