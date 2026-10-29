"""Calibración de L2 por tipo de pregunta y tarea (T2.4).

    python -m model.l2.calibrar --ckpt DIR --dev A.jsonl [B.jsonl…] --salida calib.json

Trabaja sobre las similitudes crudas s (MaxSim) de las filas de dev y ajusta, con s como única entrada:
  choice  p = softmax(s / T)                            → T (búsqueda en rejilla de log T, NLL)
  noul    p(true) = σ(a·s + b)                          → a, b (Platt, LBFGS); θ = umbral de p(true) que maximiza F1 macro
  scoreK  P(y>j) = σ((a·s − b_j))  con b_1 = b y b_j = b_{j-1} + d_j (CORAL con una T de rejilla: a = w/T, b_j = θ_j/T)
τ de escalate (por tarea): el menor umbral de confianza (máx p) con precisión ≥ 0,95 entre las filas con conf ≥ τ,
es decir la máxima cobertura. `tipos` es el ajuste agrupado por cabeza (lo que va a la sección CALIB de `.chispa` v3, que
solo guarda un τ: el de todas las filas juntas) y `tareas` el de cada tarea.
"""
import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from model.evaluacion import metricas as M

from . import datos as D
from .modelo import clave_cabeza, maxsim, texto_consulta, texto_opcion

PRECISION = 0.95
MIN_FILAS = 20  # por debajo, o con una sola clase, no se ajusta: se conserva la cabeza del modelo (sin_ajuste)


# ---------------------------------------------------------------- similitudes crudas
@torch.no_grad()
def simil(modelo, enc, filas, lote=64):
    """Por fila, s: (n_opciones,) en choice y multi y (1,) en noul/score; mismas entradas que `ModeloL2.forward`."""
    dev = modelo.ranuras.q.device
    out = []
    for i in range(0, len(filas), lote):
        fs = filas[i:i + lote]
        H, m = enc.tokens([r["texto"] for r in fs])
        S = modelo.ranuras(H.to(dev), m.to(dev))
        textos, pos, ixs = [], {}, []
        for r in fs:
            ts = [texto_opcion(r, o) for o in r["opciones"]] if r["tipo"] in ("choice", "multi") else [texto_consulta(r)]
            ix = []
            for t in ts:
                if t not in pos:
                    pos[t] = len(textos)
                    textos.append(t)
                ix.append(pos[t])
            ixs.append(ix)
        sim = maxsim(S, modelo.torre(enc.pasaje(textos).to(dev)))
        out += [sim[j, torch.tensor(ix, device=dev)].cpu() for j, ix in enumerate(ixs)]
    return out


def cabeza_inicial(modelo, clave):
    """Parámetros de la cabeza tal como salen del entrenamiento, en la misma forma que los ajustados."""
    if clave == "choice":
        return {"T": float(modelo.log_t["choice"].detach().exp().clamp(min=5e-3))}
    if clave == "noul":
        a, b = (float(x) for x in modelo.ab["noul"].detach())
        return {"a": a, "b": b}
    c = modelo.coral[clave]
    th = c.umbrales().detach()
    return {"a": float(c.w.detach()), "b": [float(x) for x in th]}


# ---------------------------------------------------------------- probabilidades con parámetros dados
def probs_de(clave, s, p):
    """s (n,) → distribución sobre las opciones, con los parámetros `p` de `ajustar`."""
    if clave == "choice":
        return F.softmax(s / p["T"], -1)
    if clave == "noul":
        pt = torch.sigmoid(p["a"] * s[0] + p["b"])
        return torch.stack([1 - pt, pt])
    sup = torch.sigmoid((p["a"] * s[0] - torch.tensor(p["b"])) / p.get("T", 1.0))
    uno = torch.ones(1)
    return (torch.cat([uno, sup]) - torch.cat([sup, 0 * uno])).clamp(min=0)


def _nll_score(ss, ys, p):
    """NLL de la cabeza score sobre todas las filas a la vez (mismo K)."""
    x = torch.stack([s[0] for s in ss])
    sup = torch.sigmoid((p["a"] * x[:, None] - torch.tensor(p["b"])) / p.get("T", 1.0))
    uno = torch.ones(len(x), 1)
    pr = (torch.cat([uno, sup], 1) - torch.cat([sup, 0 * uno], 1)).clamp(min=1e-7)
    return float(-torch.log(pr[torch.arange(len(x)), torch.tensor(ys)]).mean())


def ajustar(clave, ss, ys, inicial):
    """Ajusta la cabeza `clave` sobre (similitudes, etiquetas). Devuelve (parámetros, ajustado: bool)."""
    if len(ss) < MIN_FILAS:
        return inicial, False
    if clave == "choice":
        n = max(len(s) for s in ss)
        Z = torch.full((len(ss), n), -1e9)
        for i, s in enumerate(ss):
            Z[i, :len(s)] = s
        y = torch.tensor(ys)
        mejor = None
        for lt in np.linspace(math.log(5e-3), math.log(10.0), 400):
            nll = float(F.cross_entropy(Z / math.exp(lt), y))
            if mejor is None or nll < mejor[0]:
                mejor = (nll, math.exp(lt))
        return {"T": mejor[1]}, True
    if clave == "noul":
        if len(set(ys)) < 2:
            return inicial, False
        x = torch.stack([s[0] for s in ss])
        y = torch.tensor(ys).float()
        ab = torch.tensor([inicial["a"], inicial["b"]], requires_grad=True)
        opt = torch.optim.LBFGS([ab], lr=0.5, max_iter=200, line_search_fn="strong_wolfe")

        def cierre():
            opt.zero_grad()
            l = F.binary_cross_entropy_with_logits(ab[0] * x + ab[1], y)
            l.backward()
            return l
        opt.step(cierre)
        a, b = ab.detach()
        return {"a": float(a), "b": float(b)}, True
    # score: CORAL con temperatura; se conservan w y θ del modelo y se busca T
    mejor = None
    for lt in np.linspace(math.log(0.25), math.log(8.0), 120):
        p = {**inicial, "T": math.exp(lt)}
        nll = _nll_score(ss, ys, p)
        if mejor is None or nll < mejor[0]:
            mejor = (nll, p)
    p = mejor[1]
    return {"a": p["a"] / p["T"], "b": [b / p["T"] for b in p["b"]]}, True


def umbral_noul(ss, ys, p):
    """θ: umbral de p(true) que maximiza el F1 macro (rejilla de 99 puntos)."""
    pt = torch.sigmoid(p["a"] * torch.stack([s[0] for s in ss]) + p["b"]).numpy()
    y = np.array(ys)
    mejor = (-1.0, 0.5)
    for th in np.linspace(0.01, 0.99, 99):
        pred = pt >= th
        f = np.mean([_f1(pred == c, y == c) for c in (True, False)])
        if f > mejor[0]:
            mejor = (f, float(th))
    return mejor[1]


def _f1(pred, real):
    tp = float((pred & real).sum())
    return 0.0 if tp == 0 else 2 * tp / (pred.sum() + real.sum())


# ---------------------------------------------------------------- métricas
def tau_escalate(conf, ok, precision=PRECISION):
    """(τ, cobertura, precisión): el menor τ tal que las filas con conf ≥ τ aciertan ≥ `precision` (máxima cobertura).
    Sin ninguno, τ = 1 con cobertura 0 (siempre se escala)."""
    conf, ok = np.asarray(conf, float), np.asarray(ok, float)
    if len(conf) == 0:
        return 1.0, 0.0, float("nan")
    o = np.argsort(-conf, kind="stable")
    c, a = conf[o], ok[o]
    prec = np.cumsum(a) / np.arange(1, len(c) + 1)
    ultimo = np.flatnonzero((np.append(c[1:], -1.0) < c) & (prec >= precision))  # cortes entre valores distintos
    if len(ultimo) == 0:
        return 1.0, 0.0, float("nan")
    k = int(ultimo[-1])
    return float(c[k]), (k + 1) / len(c), float(prec[k])


def auroc(conf, ok):
    """AUROC de la confianza como detector de acierto (rangos medios); nan con una sola clase."""
    conf, ok = np.asarray(conf, float), np.asarray(ok, bool)
    n1, n0 = ok.sum(), (~ok).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    orden = np.argsort(conf, kind="stable")
    r = np.empty(len(conf))
    r[orden] = np.arange(1, len(conf) + 1)
    for v in np.unique(conf):  # empates: rango medio
        m = conf == v
        r[m] = r[m].mean()
    return float((r[ok].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _conf_ok(ps, ys, clave=None):
    """Confianza (máxima) y acierto; en las cabezas score la etiqueta es la mediana CORAL, no el argmax."""
    pred = (lambda p: M.etiqueta_coral(p)) if str(clave).startswith("score") else (lambda p: int(p.argmax()))
    conf = [float(p.max()) for p in ps]
    ok = [pred(p) == y for p, y in zip(ps, ys)]
    return conf, ok


def _tipo_tarea(filas):
    return {r["tarea"]: r["tipo"] for r in filas}


# ---------------------------------------------------------------- calibración completa
def calibrar(modelo, enc, filas, lote=64):
    """Devuelve el informe completo (ver `main`). `filas`: dev con `texto`, `tipo`, `tarea`, `opciones`, `etiqueta`.
    Las filas multi no tienen cabeza propia: van aparte a `multi_l2` (ver `calibrar_multi_l2`)."""
    multi = [r for r in filas if r["tipo"] == "multi"]
    inf = _calibrar(modelo, enc, [r for r in filas if r["tipo"] != "multi"], lote)
    inf["multi_l2"] = calibrar_multi_l2(modelo, enc, multi, lote)
    return inf


def _calibrar(modelo, enc, filas, lote=64):
    for r in filas:
        modelo.asegurar_cabeza(clave_cabeza(r))
    ss = simil(modelo, enc, filas, lote)
    ys = [r["opciones"].index(r["etiqueta"]) for r in filas]
    claves = [clave_cabeza(r) for r in filas]
    por_clave, por_tarea = defaultdict(list), defaultdict(list)
    for i, r in enumerate(filas):
        por_clave[claves[i]].append(i)
        por_tarea[(r["tarea"], claves[i])].append(i)

    def ajuste(idx, clave):
        p0 = cabeza_inicial(modelo, clave)
        p, aj = ajustar(clave, [ss[i] for i in idx], [ys[i] for i in idx], p0)
        d = {**p, "T": p.get("T", 1.0)} if clave != "choice" else dict(p)
        d["theta"] = umbral_noul([ss[i] for i in idx], [ys[i] for i in idx], p) if clave == "noul" and aj else 0.5
        return p, d, aj

    def medir(idx, clave, p, p0):
        y = [ys[i] for i in idx]
        antes = _conf_ok([probs_de(clave, ss[i], p0) for i in idx], y, clave)
        despues = _conf_ok([probs_de(clave, ss[i], p) for i in idx], y, clave)
        return antes, despues

    tipos, tareas, params = {}, {}, {}
    for clave, idx in sorted(por_clave.items()):
        p0 = cabeza_inicial(modelo, clave)
        p, d, aj = ajuste(idx, clave)
        antes, despues = medir(idx, clave, p, p0)
        tipos[clave] = {**d, "n": len(idx), "ajustado": aj, "ece_antes": M.ece(*antes), "ece_despues": M.ece(*despues)}
    for (tarea, clave), idx in sorted(por_tarea.items()):
        p0 = cabeza_inicial(modelo, clave)
        p, d, aj = ajuste(idx, clave)
        antes, despues = medir(idx, clave, p, p0)
        tau, cob, prec = tau_escalate(*despues)
        params[(tarea, clave)] = p
        tareas[tarea] = {"cabeza": clave, **d, "n": len(idx), "ajustado": aj, "ece_antes": M.ece(*antes),
                         "ece_despues": M.ece(*despues), "tau": tau, "cobertura": cob, "precision_cubierta": prec,
                         "exactitud": float(np.mean(despues[1])), "auroc_escalate": auroc(*despues)}
    # τ único de la sección CALIB: filas de todas las tareas, calibradas con su propia tarea
    conf, ok = [], []
    for (tarea, clave), idx in por_tarea.items():
        p = params[(tarea, clave)]  # por (tarea, cabeza): una tarea con varias K tiene varias cabezas
        c, o = _conf_ok([probs_de(clave, ss[i], p) for i in idx], [ys[i] for i in idx], clave)
        conf += c
        ok += o
    tau, cob, prec = tau_escalate(conf, ok)
    return {"tipos": tipos, "tareas": tareas, "tau_escalate": tau,
            "global": {"n": len(filas), "cobertura": cob, "precision_cubierta": prec, "auroc_escalate": auroc(conf, ok)}}


# ---------------------------------------------------------------- multi: CALIB «multi_l2» por esquema
def _sdk():
    """`chispa.formato` y `chispa.multi` del SDK (el hash del esquema y el ajuste de a, b, θ son los de `chispa train`)."""
    sdk = str(Path(__file__).resolve().parents[2] / "sdk" / "python")
    if sdk not in sys.path:
        sys.path.insert(0, sdk)
    from chispa import formato, multi
    return formato, multi


def sufijo_multi(fila):
    """«@» + HashEsquema2 (pregunta, «multi», todas las opciones con su descripción) en hex minúsculas: `decide.ClaveCalibMulti`."""
    formato, _ = _sdk()
    desc = fila.get("descripciones", {})
    return "@" + formato.hash_esquema2(fila["pregunta"], "multi", [(o, desc.get(o, "")) for o in fila["opciones"]]).hex()


def etiquetas_multi(v):
    """Etiquetas activas de una fila multi: lista, o cadena «a|b» (vacía = ninguna), como en `chispa train`."""
    if isinstance(v, (list, tuple)):
        return {str(x) for x in v}
    return {x.strip() for x in str(v or "").split("|") if x.strip()}


def calibrar_multi_l2(modelo, enc, filas, lote=64):
    """{"multi_l2@<hex>[#<id>]": {T, a, b, theta}} de las filas multi con `etiqueta`, un esquema (pregunta, opciones, descripciones) cada vez:
    a, b globales del esquema sobre el MaxSim de L2 de cada opción (σ(a·s + b)) y un θ por opción con positivos y negativos suficientes.
    Los esquemas sin variación en las etiquetas no se ajustan (L2 no opina en ellos). {} sin filas multi."""
    _, M_ = _sdk()
    grupos = defaultdict(list)
    for r in filas:
        if r["tipo"] == "multi" and "etiqueta" in r:
            grupos[sufijo_multi(r)].append(r)
    tipos = {}
    for esq, rs in sorted(grupos.items()):
        S = np.array([s.numpy() for s in simil(modelo, enc, rs, lote)], dtype=np.float64)  # (n, K): MaxSim con la torre de cada opción
        Y = np.array([[o in etiquetas_multi(r["etiqueta"]) for o in rs[0]["opciones"]] for r in rs])
        if Y.all() or not Y.any():
            continue
        ops = [type("O", (), {"id": o}) for o in rs[0]["opciones"]]
        tipos.update(M_._ajustar_capa("multi_l2" + esq, ops, S, Y)[0])
    return tipos


def cabeza_params(clave, d):
    """Parámetros de `probs_de` a partir de un registro de `tipos`/`tareas`."""
    return {"T": d["T"]} if clave == "choice" else {"a": d["a"], "b": d["b"]}


def a_calib_chispa(informe):
    """Sección CALIB de `.chispa` v3 (`format/chispa3`, claves cerradas): {tipos{cabeza:{T,a,b,theta}}, tau_escalate}.
    Las cabezas `scoreK` llevan a = w/T y b = b_1; los incrementos b_j − b_{j-1} van en entradas `scoreK#j` (campo a)."""
    tipos = {}
    for clave, d in informe["tipos"].items():
        base = {"T": float(d.get("T", 1.0)), "a": float(d.get("a", 0.0)), "b": 0.0, "theta": float(d["theta"])}
        if clave.startswith("score"):
            base["b"] = float(d["b"][0])
            for j in range(1, len(d["b"])):
                tipos["%s#%d" % (clave, j)] = {"T": 1.0, "a": float(d["b"][j] - d["b"][j - 1]), "b": 0.0, "theta": 0.5}
        elif clave == "noul":
            base["b"] = float(d["b"])
        tipos[clave] = base
    tipos.update({k: {c: float(v) for c, v in d.items()} for k, d in informe.get("multi_l2", {}).items()})
    return {"tipos": tipos, "tau_escalate": float(informe["tau_escalate"])}


def cargar_modelo(ckpt, device="cpu"):
    from .evaluar import cargar_modelo as cm
    ruta = Path(ckpt)
    return cm(str(ruta / "mejor.pt") if ruta.is_dir() else str(ruta), device)


def filas_dev(rutas):
    filas = D.leer(rutas)
    dev = [r for r in filas if r.get("split") == "dev"]
    return dev or filas


def resumen(inf):
    lin = ["| tarea | cabeza | n | ECE antes | ECE después | τ | cobertura | AUROC |", "|" + "---|" * 8]
    for t, r in inf["tareas"].items():
        lin.append("| %s | %s | %d | %.3f | %.3f | %.3f | %.3f | %.3f |" % (
            t, r["cabeza"], r["n"], r["ece_antes"], r["ece_despues"], r["tau"], r["cobertura"], r["auroc_escalate"]))
    return "\n".join(lin)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True, help="directorio con mejor.pt, o el .pt")
    ap.add_argument("--dev", nargs="+", required=True, help="jsonl de dev (filas con split=dev; si no hay ninguna, todas)")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--max-filas", type=int, default=0)
    a = ap.parse_args(argv)
    from .modelo import Codificador
    modelo, _ = cargar_modelo(a.ckpt, a.device)
    filas = filas_dev(a.dev)
    if a.max_filas:
        filas = filas[:a.max_filas]
    inf = calibrar(modelo, Codificador(device=a.device), filas)
    inf["chispa"] = a_calib_chispa(inf)
    Path(a.salida).write_text(json.dumps(inf, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(resumen(inf))
    print("τ global %.3f, cobertura %.3f" % (inf["tau_escalate"], inf["global"]["cobertura"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
