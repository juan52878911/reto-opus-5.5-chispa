"""G.8b: barrido de λ (shrinkage, κ = λ) en test, y τ para esquemas nuevos. Lo corre model/l2/aws/barrido.sh.

    python -m model.l2.barrido --ckpt mejor.pt --salida DIR --datos DIR_CONVERTIDOS --jevbench RUTA --kappa K
        [--meta-fuera META] [--excluir massive,hatecheck,inyecciones] [--lam 0 1 2 4 8 inf] [--k 8] [--l1] [--max-filas N]

Para cada λ evalúa las tareas no vistas (las excluidas del entrenamiento, con k ejemplos de soporte por clase del train) y JevBench
(k por esquema, dejando fuera el caso); λ = ∞ es zero-shot (sin soporte: el runtime solo usa la torre de la descripción). Además
de la rejilla evalúa el κ elegido en dev. El codificador va con la caché de mensajes: e5 se calcula una vez por texto, no por λ.
Escribe `DIR/barrido.json` y `DIR/comparacion.md` (tabla λ × tarea y «τ para esquemas nuevos»).
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

from model.evaluacion import chispa_eval as CE
from model.evaluacion import metricas as M

from . import datos as D
from . import evaluar as EV
from .calibrar import tau_escalate

LAMBDAS = (0.0, 1.0, 2.0, 4.0, 8.0, math.inf)
PRECISION, ABSTENCION = 0.95, 0.20


def etiqueta_lam(lam):
    return "∞" if math.isinf(lam) else ("%g" % lam)


def conf_ok(filas, preds):
    """(confianza top-1, acierto) por fila; en score, la etiqueta es la mediana CORAL."""
    por = {p["id"]: p for p in preds}
    c, o = [], []
    for r in filas:
        et, conf = M.top1(por[r["id"]]["probs"], r.get("tipo"), r["opciones"])
        c.append(conf)
        o.append(et == r["etiqueta"])
    return c, o


def tau_abstencion(conf, ok, max_abst=ABSTENCION):
    """(τ, abstención, precisión): el mayor τ con abstención ≤ `max_abst` (cobertura ≥ 1 − max_abst, contando empates)."""
    conf, ok = np.asarray(conf, float), np.asarray(ok, float)
    if len(conf) == 0:
        return float("nan"), float("nan"), float("nan")
    c = np.sort(conf)[::-1]
    tau = float(c[max(math.ceil((1 - max_abst) * len(c)), 1) - 1])
    cubre = conf >= tau
    return tau, 1 - float(cubre.mean()), float(ok[cubre].mean())


def resumen_tau(conf, ok):
    tau, cob, prec = tau_escalate(conf, ok, PRECISION)
    ta, ab, pa = tau_abstencion(conf, ok)
    return {"n": len(conf), "exactitud": float(np.mean(ok)) if len(ok) else float("nan"),
            "tau_p95": tau, "abstencion_p95": 1 - cob, "precision_p95": prec,
            "tau_abst20": ta, "abstencion_abst20": ab, "precision_abst20": pa}


def f1_por_tarea(filas, preds):
    ev = CE.evaluar(filas, preds)
    out = {t: m["macro_f1"] for t, m in ev["por_tarea"].items()}
    out["(global)"] = ev["global"]["macro_f1"]
    return out


def conjuntos_no_vistos(datos, excluir, meta_fuera=None, max_filas=0):
    todos = EV.conjuntos_test(datos)
    out = {n: f for n, f in todos.items() if n in excluir}
    if meta_fuera:
        fuera = EV.filas_fuera(meta_fuera)
        if fuera:
            out["tasksource_fuera"] = fuera
    res = {}
    for n, f in out.items():
        f = f[:max_filas] if max_filas else f
        res[n] = CE.asignar_ids(f, n) if any("id" not in r for r in f) else f
    return res


def barrido(a, log=print):
    """Devuelve el dict de resultados (también se escribe en barrido.json)."""
    from model.evaluacion.jevbench import cargar_jevbench
    from model.evaluacion.jevbench_l2 import predecir_variante
    from .modelo import MAX_TOK, Codificador, SoporteEval
    modelo, ck = EV.cargar_modelo(a.ckpt, a.device)
    enc = Codificador(device=a.device, max_tok=a.max_tok or ck.get("max_tok", MAX_TOK), cache_mensajes=True)
    enc.cargar_enc(ck.get("enc"))
    lams = sorted(set(a.lam) | {a.kappa}, key=lambda x: (math.isinf(x), x))
    excluir = [x for x in a.excluir.split(",") if x]
    conj = conjuntos_no_vistos(a.datos, excluir, a.meta_fuera, a.max_filas)
    train = {t: f for t, f in EV.train_por_conjunto(a.datos).items() if t in conj}
    jev = cargar_jevbench(a.jevbench)
    if a.max_jev:
        jev = jev[:a.max_jev]
    log("no vistas: %s; JevBench: %d casos; λ: %s" % ({n: len(f) for n, f in conj.items()}, len(jev), [etiqueta_lam(x) for x in lams]))
    res = {"lambdas": [etiqueta_lam(x) for x in lams], "kappa_dev": a.kappa, "k": a.k, "no_vistas": {}, "jevbench": {}, "tau": {}, "l1": {}}
    pool = {}   # (fuente, λ) → (conf, ok)
    for lam in lams:
        t0 = time.time()
        et = etiqueta_lam(lam)
        cs, os_, f1 = [], [], {}
        for n, filas in conj.items():
            if math.isinf(lam) or n not in train:   # zero-shot (tasksource_fuera no tiene train: siempre sin soporte)
                preds = EV.predecir(modelo, enc, filas)
            else:
                preds = EV.predecir(modelo, enc, filas, soporte=SoporteEval(train, a.k, kappa=lam))
            f1[n] = f1_por_tarea(filas, preds)["(global)"]
            c, o = conf_ok(filas, preds)
            cs += c
            os_ += o
        res["no_vistas"][et] = f1
        pool[("no_vistas", et)] = (cs, os_)
        preds = predecir_variante(modelo, enc, jev, 0 if math.isinf(lam) else a.k, kappa=0.0 if math.isinf(lam) else lam)
        res["jevbench"][et] = f1_por_tarea(jev, preds)
        pool[("jevbench", et)] = conf_ok(jev, preds)
        log("λ=%s: %.1f s, no vistas %s, JevBench F1 %.3f" % (et, time.time() - t0, {n: round(v, 3) for n, v in f1.items()},
                                                             res["jevbench"][et]["(global)"]))
    elegidos = ["∞", etiqueta_lam(a.kappa)]
    for fuente in ("no_vistas", "jevbench"):
        for et in elegidos:
            res["tau"].setdefault(fuente, {})[et] = resumen_tau(*pool[(fuente, et)])
    if a.l1:
        res["l1"] = barrido_l1(a, lams, conj, train, jev, log)
    return res


def barrido_l1(a, lams, conj, train, jev, log=print):
    """L1 (potion con prototipos): el mismo barrido, macro-F1 global por conjunto no visto y de JevBench."""
    from model.cascada import capas as L
    from model.evaluacion.jevbench import pliegues
    from model.evaluacion.jevbench_l2 import _con_tarea_esquema
    m = L.cargar_potion()
    jf = _con_tarea_esquema(jev)
    plg = pliegues(jf, a.k)
    out = {}
    for lam in lams:
        et, f1 = etiqueta_lam(lam), {}
        for n, filas in conj.items():
            if n in train and not math.isinf(lam):
                sop = [r for _, r in D.soporte_t17a(train[n], a.k, 0)]
            else:
                sop = []
            pr = L.l1_lam(m, sop, filas, lam)
            f1[n] = CE.evaluar(filas, list(pr.values()))["global"]["macro_f1"]
        pj = {}
        for _, rs, sop in plg:
            pj.update(L.l1_lam(m, sop, rs, lam if sop else math.inf))
        f1["jevbench"] = CE.evaluar(jf, [pj[r["id"]] for r in jf])["global"]["macro_f1"]
        out[et] = f1
        log("L1 λ=%s: %s" % (et, {n: round(v, 3) for n, v in f1.items()}))
    return out


def _f(v):
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else "%.3f" % v


def tabla_lam(por_lam, titulo):
    lams = list(por_lam)
    filas = sorted({t for d in por_lam.values() for t in d}, key=lambda t: (t == "(global)", t))
    l = ["### " + titulo, "", "| tarea | " + " | ".join("λ=" + x for x in lams) + " |", "|---|" + "---|" * len(lams)]
    for t in filas:
        l.append("| %s | %s |" % (t, " | ".join(_f(por_lam[x].get(t)) for x in lams)))
    return "\n".join(l)


def tabla_tau(tau):
    l = ["| fuente | λ | n | exactitud | τ (prec. 0,95) | abstención | τ (abst. ≤ 20 %) | abstención | precisión |", "|---|---|---|---|---|---|---|---|---|"]
    for fuente, d in tau.items():
        for et, r in d.items():
            l.append("| %s | %s | %d | %s | %s | %s | %s | %s | %s |" % (
                fuente, et, r["n"], _f(r["exactitud"]), _f(r["tau_p95"]), _f(r["abstencion_p95"]), _f(r["tau_abst20"]),
                _f(r["abstencion_abst20"]), _f(r["precision_abst20"])))
    return "\n".join(l)


def comparacion(res):
    k, kd = res["k"], res["kappa_dev"]
    s = ["# G.8b: barrido de λ en test", "",
         "λ = κ de G.8 (`formula-shrinkage.md`): peso de la descripción λ/(λ+n); λ = 0 solo ejemplos, λ = ∞ zero-shot. k = %d por clase/esquema. "
         "Macro-F1. κ elegido en dev: %g. `tasksource_fuera` no tiene train: no depende de λ." % (k, kd), "",
         tabla_lam(res["no_vistas"], "Tareas no vistas (macro-F1 global por conjunto)"), "",
         tabla_lam(res["jevbench"], "JevBench (macro-F1 por familia)")]
    if res.get("l1"):
        s += ["", tabla_lam(res["l1"], "L1 (potion con prototipos; macro-F1 global por conjunto)")]
    tau = res["tau"]
    elegido = "%g" % kd
    nv = tau["no_vistas"]
    rec = nv[elegido]["tau_p95"] if elegido in nv else float("nan")
    s += ["", "## τ para esquemas nuevos", "",
          "Confianza = probabilidad top-1 (en score, la etiqueta es la mediana CORAL). Sobre las no vistas agrupadas, con λ = ∞ y con el λ "
          "elegido (%s); JevBench solo como comprobación." % elegido, "", tabla_tau(tau), ""]
    if "∞" in nv:
        s.append("- **Recomendado** (λ = ∞, el valor por defecto del runtime, sobre las no vistas): τ = %s para precisión 0,95 (abstención %s); "
                 "τ = %s deja la abstención en ≤ 20 %% (precisión %s)." % (
                     _f(nv["∞"]["tau_p95"]), _f(nv["∞"]["abstencion_p95"]), _f(nv["∞"]["tau_abst20"]), _f(nv["∞"]["precision_abst20"])))
    if elegido in nv and elegido != "∞":
        s.append("- Con el λ elegido (%s): τ = %s (abstención %s); τ = %s para abstención ≤ 20 %%." % (
            elegido, _f(rec), _f(nv[elegido]["abstencion_p95"]), _f(nv[elegido]["tau_abst20"])))
    s.append("- τ = 1,000 con abstención 1,000 significa que ningún corte llega a 0,95: no se puede garantizar esa precisión.")
    return "\n".join(s) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--datos", required=True)
    ap.add_argument("--jevbench", required=True)
    ap.add_argument("--kappa", type=float, default=4.0, help="κ elegido en dev (kappa_pos de entrenamiento.json)")
    ap.add_argument("--lam", type=float, nargs="*", default=list(LAMBDAS))
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--excluir", default="massive,hatecheck,inyecciones")
    ap.add_argument("--meta-fuera")
    ap.add_argument("--l1", action="store_true", help="también L1 (potion con prototipos)")
    ap.add_argument("--max-tok", type=int, default=0)
    ap.add_argument("--max-filas", type=int, default=0, help="tope de filas por conjunto no visto (0 = todas)")
    ap.add_argument("--max-jev", type=int, default=0, help="tope de casos de JevBench (0 = todos)")
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args(argv)
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    res = barrido(a, log=lambda m: print(m, flush=True))
    (sal / "barrido.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    (sal / "comparacion.md").write_text(comparacion(res), encoding="utf-8")
    print(comparacion(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
