"""T2.2c: cabeza conjunta L0 + L2 (fusión tardía por tarea).

    python -m model.l2.conjunta --ckpt mejor.pt --salida DIR --datos DIR_CONVERTIDOS [--cache DIR] [--renombrar]
                                [--fase todo|caracteristicas|cabezas] [--tareas massive,hatecheck,...] [--max-filas N]

Por tarea, sobre [log-probs de L0, similitud de L2 con cada prototipo de soporte, log-probs de L2 con soporte]:
  · cabeza «lr»: regresión logística multinomial con pesos compartidos entre clases (logit_c = w·f_c);
  · cabeza «puerta»: p = g·p_L0 + (1−g)·p_L2 con g = σ(v·[1, conf_L0, conf_L2, margen_L0, margen_L2]).
La cabeza y su λ se eligen por validación cruzada (NLL) sobre las características de train, nunca en test.

Características sin fuga (fase `caracteristicas`, la única que usa el checkpoint y e5):
  · L0 en train: fuera de pliegue (k = 5; `model.lineas_base.correr.correr_l0`, entrenado con los otros 4 pliegues);
  · L2 en train: soporte de T1.7a (`datos.soporte_t17a`) dejando fuera la propia fila: si la fila es del soporte, el prototipo
    de su clase se calcula sin ella (`ProtosSinPropia`; igual a `modelo.prototipos` sobre el soporte menos la fila);
  · en test: L0 entrenado con todo train y L2 con el soporte completo, como en la evaluación de T2.1b.
Se guardan en `--cache/<tarea>.npz`; la fase `cabezas` no necesita GPU, ni checkpoint, ni e5.

T2.2d: `--modo-cabeza cvtest` entrena la cabeza por pliegues de test (partición de `model.cascada.cascada.pliegue`),
`--calibrar` calibra fuera de pliegue (T o Platt, `calibrar.py`) y `--desde-cache DIR` salta el codificador y la GPU.

Salida en DIR: `pred/<tarea>.jsonl` (conjunta; `{id, probs, ms}`), `pred_l0/`, `pred_l2/`, `resultados.json` (+ `_l0`, `_l2`),
`cabezas.json` (CV y elección), `delta.md` (L0, L2, conjunta y el listón) y, con `--renombrar`, `pred_renombrado/`,
`resultados_renombrado.json` y `caida.md`. Los conjuntos sin train (listón) no entran: no hay con qué entrenar la cabeza.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from model.cascada.cascada import pliegue   # la partición de test de la cascada: se importa, no se copia
from model.evaluacion import chispa_eval as CE
from model.evaluacion import metricas as M
from model.lineas_base import correr as LB0

from . import calibrar as CAL
from . import datos as D
from . import evaluar as EV
from .modelo import Codificador, prototipos, simproto

PLIEGUES = 5
SEMILLA = 0
SOPORTE = 32
EPS = 1e-6
LAMBDAS = (1e-4, 1e-3, 1e-2, 1e-1, 1.0)
CABEZAS = ("lr", "puerta")
UMBRAL_GANA, UMBRAL_LISTON = 0.01, 0.95


# --- datos ----------------------------------------------------------------------------------------------------------
def recortar(train, test, maximo, semilla=SEMILLA):
    """Tope de filas (0 = sin tope): train estratificado por clase (reparto por turnos, orden por id), test submuestra fija."""
    if not maximo:
        return train, test
    if len(train) > maximo:
        por = {}
        for r in sorted(train, key=lambda r: r["id"]):
            por.setdefault(r["etiqueta"], []).append(r)
        out, i = [], 0
        while len(out) < maximo:
            for c in sorted(por):
                if i < len(por[c]) and len(out) < maximo:
                    out.append(por[c][i])
            i += 1
        train = out
    return train, LB0.submuestra(test, maximo)


def cargar_tareas(datos, tareas=None, maximo=0):
    """{conjunto: (train, test)} de T1.7a y herramientas con train; mismo orden y recorte en las dos fases."""
    tests = EV.conjuntos_test(datos)
    trains = EV.train_por_conjunto(datos)
    out = {}
    for t in sorted(trains):
        if t in tests and (not tareas or t in tareas):
            out[t] = recortar(sorted(trains[t], key=lambda r: r["id"]), tests[t], maximo)
    return out


def pliegues(train, k=PLIEGUES, semilla=SEMILLA):
    """Pliegue de cada fila (lista alineada con `train`): reparto por turnos dentro de cada clase tras barajar con semilla fija,
    de modo que cada fila cae en exactamente un pliegue y cada clase se reparte entre todos los que puede."""
    import random
    rng = random.Random(semilla)
    por = {}
    for i, r in enumerate(train):
        por.setdefault(r["etiqueta"], []).append(i)
    fold = [0] * len(train)
    desplazo = 0
    for c in sorted(por):
        g = sorted(por[c], key=lambda i: train[i]["id"])
        rng.shuffle(g)
        for j, i in enumerate(g):
            fold[i] = (j + desplazo) % k
        desplazo += len(g)  # las clases pequeñas no cargan siempre el pliegue 0
    return fold


def hash_ids(filas):
    return hashlib.sha1("\n".join(r["id"] for r in filas).encode("utf-8")).hexdigest()


def hash_fichero(ruta):
    h = hashlib.sha1()
    with open(ruta, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# --- L0 fuera de pliegue ---------------------------------------------------------------------------------------------
def probs_l0(entrenar, objetivo):
    """(array (n, C) en el orden de `opciones` de cada fila, ms por fila): `correr_l0` de las líneas base, entrenado con `entrenar`."""
    probs, ms = LB0.correr_l0([(0, r) for r in entrenar], objetivo, None)
    return np.array(probs, float), np.array(ms, float)


def l0_fuera_de_pliegue(train, fold, k=PLIEGUES):
    out = np.zeros((len(train), len(train[0]["opciones"])))
    for f in range(k):
        dentro = [i for i in range(len(train)) if fold[i] == f]
        if not dentro:
            continue
        resto = [train[i] for i in range(len(train)) if fold[i] != f]
        p, _ = probs_l0(resto, [train[i] for i in dentro])
        out[dentro] = p
    return out


# --- L2: prototipos con y sin la propia fila -----------------------------------------------------------------------
class ProtosSinPropia:
    """Suma de ranuras por clase del soporte, para sacar los prototipos con o sin una fila del soporte.
    `completos()` = `modelo.prototipos(modelo, enc, soporte)`; `sin(id)` = lo mismo sobre el soporte menos esa fila."""

    def __init__(self, modelo, enc, soporte, lote=256):
        self.etqs = sorted({r["etiqueta"] for r in soporte})
        self.idx = {e: i for i, e in enumerate(self.etqs)}
        self.pos = {r["id"]: i for i, r in enumerate(soporte)}
        self.clase = [self.idx[r["etiqueta"]] for r in soporte]
        dev = modelo.ranuras.q.device
        trozos = []
        with torch.no_grad():
            for i in range(0, len(soporte), lote):
                H, m = enc.tokens([r["texto"] for r in soporte[i:i + lote]])
                trozos.append(modelo.ranuras(H.to(dev), m.to(dev)))
        self.S = torch.cat(trozos)  # (n,K,d)
        ci = torch.tensor(self.clase, device=dev)
        self.suma = torch.zeros(len(self.etqs), *self.S.shape[1:], device=dev).index_add(0, ci, self.S)
        self.cuenta = torch.bincount(ci, minlength=len(self.etqs))

    def completos(self):
        return self.idx, F.normalize(self.suma, dim=-1)

    def sin(self, id_):
        i = self.pos[id_]
        c = self.clase[i]
        suma = self.suma.clone()
        suma[c] = suma[c] - self.S[i]
        if self.cuenta[c] > 1:
            return self.idx, F.normalize(suma, dim=-1)
        keep = [j for j in range(len(self.etqs)) if j != c]  # la clase se queda sin soporte: sin prototipo
        idx = {self.etqs[j]: n for n, j in enumerate(keep)}
        return idx, F.normalize(suma[keep], dim=-1)


@torch.no_grad()
def l2_filas(modelo, enc, filas, protos, lote=64):
    """Una tarea; `protos` = (idx, P). -> (simproto por opción (n,C), probs de L2 con soporte (n,C), ms por fila). Como `modelo._simproto`, la clase de
    una opción es su nombre original (`origen`); una opción sin prototipo vale 0."""
    modelo.eval()
    dev = modelo.ranuras.q.device
    tarea, (idx, P) = filas[0]["tarea"], protos
    sps, pr, ms = [], [], []
    for i in range(0, len(filas), lote):
        fs = filas[i:i + lote]
        t0 = time.perf_counter()
        probs, _ = modelo(fs, enc, entrenar=False, protos={tarea: (idx, P)})
        H, m = enc.tokens([r["texto"] for r in fs])
        sp = simproto(modelo.ranuras(H.to(dev), m.to(dev)), P)  # (b,C)
        t = (time.perf_counter() - t0) * 1000 / len(fs)
        for j, r in enumerate(fs):
            col = [idx.get(o, -1) for o in r.get("origen", r["opciones"])]
            v = sp[j, [max(c, 0) for c in col]] * torch.tensor([c >= 0 for c in col], device=dev, dtype=sp.dtype)
            p = probs[j].double().cpu()
            sps.append(v.double().cpu().numpy())
            pr.append((p / p.sum()).numpy())
            ms.append(t)
    return np.array(sps), np.array(pr), np.array(ms)


def l2_train(modelo, enc, train, soporte):
    """L2 en train con soporte sin la propia fila: las filas fuera del soporte usan el soporte completo; las del soporte,
    el suyo menos ellas. -> (simproto, probs) (n,C)."""
    ps = ProtosSinPropia(modelo, enc, soporte)
    en_sop = {r["id"] for r in soporte}
    sp = np.zeros((len(train), len(train[0]["opciones"])))
    pr = np.zeros_like(sp)
    fuera = [i for i, r in enumerate(train) if r["id"] not in en_sop]
    if fuera:
        sp[fuera], pr[fuera], _ = l2_filas(modelo, enc, [train[i] for i in fuera], ps.completos())
    for i, r in enumerate(train):
        if r["id"] in en_sop:
            s, p, _ = l2_filas(modelo, enc, [r], ps.sin(r["id"]))
            sp[i], pr[i] = s[0], p[0]
    return sp, pr


def caracteristicas(modelo, enc, train, test, k=PLIEGUES, soporte_k=SOPORTE, semilla=SEMILLA):
    """Todas las características de una tarea (dict de arrays). Los renombrados (`r_*`) usan las opciones A/B/C de los `choice`;
    L0 no depende del nombre (se busca por posición = `origen`), así que su matriz es la misma."""
    fold = pliegues(train, k, semilla)
    sop = [r for _, r in D.soporte_t17a(train, soporte_k, semilla)]
    c = {"tr_fold": np.array(fold), "tr_y": np.array([r["opciones"].index(r["etiqueta"]) for r in train]),
         "te_y": np.array([r["opciones"].index(r["etiqueta"]) for r in test])}
    c["tr_l0"] = l0_fuera_de_pliegue(train, fold, k)
    c["te_l0"], ms0 = probs_l0(train, test)
    c["tr_sp"], c["tr_l2"] = l2_train(modelo, enc, train, sop)
    protos = prototipos(modelo, enc, sop)
    c["te_sp"], c["te_l2"], ms2 = l2_filas(modelo, enc, test, protos)
    c["te_ms"] = ms0 + ms2
    ren = [D.renombrar_fila(r) for r in test]
    if all(a is b for a, b in zip(ren, test)):
        c["r_sp"], c["r_l2"] = c["te_sp"], c["te_l2"]
    else:
        c["r_sp"], c["r_l2"], _ = l2_filas(modelo, enc, ren, protos)
    return c


def guardar_cache(ruta, c, meta):
    np.savez_compressed(ruta, meta=np.array(json.dumps(meta)), **c)


def leer_cache(ruta):
    z = np.load(ruta, allow_pickle=False)
    return {k: z[k] for k in z.files if k != "meta"}, json.loads(str(z["meta"]))


def meta_de(train, test, k, soporte_k, semilla, ckpt_sha=None):
    return {"ids_train": hash_ids(train), "ids_test": hash_ids(test), "k": k, "soporte": soporte_k, "semilla": semilla,
            "ckpt": ckpt_sha}


# --- cabezas -----------------------------------------------------------------------------------------------------
def _centrar(x):
    return x - x.mean(axis=1, keepdims=True)


class Cabeza:
    """Una cabeza ajustada a una tarea: `ajustar(c, filas, lam)` y `probs(l0, sp, l2)` → (n,C)."""

    def __init__(self, tipo, lam):
        self.tipo, self.lam, self.w, self.esc = tipo, lam, None, None

    def _x(self, l0, sp, l2):
        a, c = _centrar(np.log(np.clip(l0, EPS, 1))), _centrar(np.log(np.clip(l2, EPS, 1)))
        b = _centrar(sp)
        if self.esc is None:
            self.esc = [max(float(v.std()), 1e-6) for v in (a, b, c)]
        top0 = (l0 == l0.max(1, keepdims=True)).astype(float)
        top2 = (l2 == l2.max(1, keepdims=True)).astype(float)
        return torch.tensor(np.stack([a / self.esc[0], b / self.esc[1], c / self.esc[2], top0, top2, top0 * top2], -1))

    @staticmethod
    def _z(l0, l2):
        def cm(p):
            s = np.sort(p, axis=1)
            return s[:, -1], s[:, -1] - s[:, -2]
        c0, m0 = cm(l0)
        c2, m2 = cm(l2)
        return torch.tensor(np.stack([np.ones_like(c0), c0, c2, m0, m2], -1))

    def _logits(self, l0, sp, l2):
        return self._x(l0, sp, l2) @ self.w

    def _mezcla(self, l0, l2, z):
        g = torch.sigmoid(z @ self.w).unsqueeze(1)
        return g * torch.tensor(l0) + (1 - g) * torch.tensor(l2)

    def _perdida(self, l0, sp, l2, y, x=None, z=None):
        y = torch.tensor(y)
        if self.tipo == "lr":
            nll = F.cross_entropy(x @ self.w, y)
            pen = (self.w ** 2).sum()
        else:
            p = self._mezcla(l0, l2, z)
            nll = -torch.log(p[torch.arange(len(y)), y].clamp(min=EPS)).mean()
            pen = (self.w[1:] ** 2).sum()
        return nll + self.lam * pen

    def ajustar(self, l0, sp, l2, y):
        self.esc = None
        if self.tipo == "lr":
            x, z = self._x(l0, sp, l2), None
            self.w = torch.zeros(x.shape[-1], dtype=torch.double, requires_grad=True)
            self.w.data[:3] = torch.tensor([1.0, 1.0, 1.0], dtype=torch.double)
        else:
            x, z = None, self._z(l0, l2)
            self.w = torch.zeros(z.shape[-1], dtype=torch.double, requires_grad=True)
        opt = torch.optim.LBFGS([self.w], lr=1.0, max_iter=200, tolerance_grad=1e-9, tolerance_change=1e-12,
                                line_search_fn="strong_wolfe")

        def cierre():
            opt.zero_grad()
            p = self._perdida(l0, sp, l2, y, x, z)
            p.backward()
            return p
        opt.step(cierre)
        self.w = self.w.detach()
        return self

    def probs(self, l0, sp, l2):
        with torch.no_grad():
            if self.tipo == "lr":
                p = F.softmax(self._logits(l0, sp, l2), -1)
            else:
                p = self._mezcla(l0, l2, self._z(l0, l2))
            p = p.clamp(min=0)
            return (p / p.sum(1, keepdim=True)).numpy()


def nll(p, y):
    return float(-np.log(np.clip(p[np.arange(len(y)), y], EPS, 1)).mean())


def validacion_cruzada(c, tipo, lam, k=PLIEGUES):
    """NLL medio fuera de pliegue de la cabeza sobre las características de train (los pliegues de L0)."""
    f, tot, n = c["tr_fold"], 0.0, 0
    for j in range(k):
        va, tr = f == j, f != j
        if not va.any() or not tr.any():
            continue
        h = Cabeza(tipo, lam).ajustar(c["tr_l0"][tr], c["tr_sp"][tr], c["tr_l2"][tr], c["tr_y"][tr])
        p = h.probs(c["tr_l0"][va], c["tr_sp"][va], c["tr_l2"][va])
        tot += nll(p, c["tr_y"][va]) * int(va.sum())
        n += int(va.sum())
    return tot / max(n, 1)


def elegir(c, cabezas=CABEZAS, lambdas=LAMBDAS, k=PLIEGUES):
    """-> (mejor (tipo, λ), {tipo: mejor λ}, tabla {tipo: {λ: NLL}}). Solo mira train."""
    tabla = {t: {lam: validacion_cruzada(c, t, lam, k) for lam in lambdas} for t in cabezas}
    por_tipo = {t: min(v, key=lambda l: (v[l], l)) for t, v in tabla.items()}
    mejor = min(por_tipo.items(), key=lambda kv: (tabla[kv[0]][kv[1]], cabezas.index(kv[0])))
    return mejor, por_tipo, tabla


def ajustar_y_predecir(c, cabezas=CABEZAS, lambdas=LAMBDAS, k=PLIEGUES):
    """Elige por CV en train, ajusta con todo train y predice test (y test renombrado). -> dict con probs y metadatos."""
    (tipo, lam), por_tipo, tabla = elegir(c, cabezas, lambdas, k)
    hs = {t: Cabeza(t, por_tipo[t]).ajustar(c["tr_l0"], c["tr_sp"], c["tr_l2"], c["tr_y"]) for t in cabezas}
    t0 = time.perf_counter()
    p = hs[tipo].probs(c["te_l0"], c["te_sp"], c["te_l2"])
    ms_cabeza = (time.perf_counter() - t0) * 1000 / len(p)
    return {"elegida": tipo, "lambda": lam, "por_tipo": por_tipo, "cv_nll": {t: {str(l): v for l, v in d.items()} for t, d in tabla.items()},
            "probs": p, "probs_r": hs[tipo].probs(c["te_l0"], c["r_sp"], c["r_l2"]),
            "probs_tipo": {t: hs[t].probs(c["te_l0"], c["te_sp"], c["te_l2"]) for t in cabezas}, "ms_cabeza": ms_cabeza}


def ajustar_y_predecir_cvtest(c, ids, cabezas=CABEZAS, lambdas=LAMBDAS, k=PLIEGUES):
    """Como `ajustar_y_predecir`, pero la cabeza se entrena con test: 2 pliegues por hash del `id` (los de `model/cascada`),
    cada fila se predice con la cabeza ajustada en el otro pliegue. Dentro del pliegue de ajuste, tipo y λ se eligen por CV
    (pliegues por hash con otra sal), así que la fila evaluada no interviene en nada de lo que la predice."""
    ids = list(ids)
    pl = np.array([pliegue(i, SEMILLA) for i in ids])
    inner = np.array([pliegue(i, SEMILLA + 1, k) for i in ids])
    n, nc = c["te_l0"].shape
    probs, probs_r = np.zeros((n, nc)), np.zeros((n, nc))
    probs_tipo = {t: np.zeros((n, nc)) for t in cabezas}
    trozos = []
    for f in (0, 1):
        ev, aj = pl == f, pl != f
        if not ev.any() or not aj.any():
            raise ValueError("el pliegue %d de test está vacío (%d filas)" % (f, n))
        sub = {"tr_l0": c["te_l0"][aj], "tr_sp": c["te_sp"][aj], "tr_l2": c["te_l2"][aj], "tr_y": c["te_y"][aj], "tr_fold": inner[aj],
               "te_l0": c["te_l0"][ev], "te_sp": c["te_sp"][ev], "te_l2": c["te_l2"][ev],
               "r_sp": c["r_sp"][ev], "r_l2": c["r_l2"][ev]}
        a = ajustar_y_predecir(sub, cabezas, lambdas, k)
        probs[ev], probs_r[ev] = a["probs"], a["probs_r"]
        for t in cabezas:
            probs_tipo[t][ev] = a["probs_tipo"][t]
        trozos.append(a)
    elegidas = [a["elegida"] for a in trozos]
    return {"elegida": elegidas[0] if len(set(elegidas)) == 1 else "/".join(elegidas), "lambda": trozos[0]["lambda"],
            "por_tipo": [a["por_tipo"] for a in trozos], "cv_nll": [a["cv_nll"] for a in trozos], "probs": probs, "probs_r": probs_r,
            "probs_tipo": probs_tipo, "ms_cabeza": float(np.mean([a["ms_cabeza"] for a in trozos])),
            "pliegues_test": [int((pl == 0).sum()), int((pl == 1).sum())]}


# --- calibración fuera de pliegue ----------------------------------------------------------------------------------
def _ajustar_cal(p, y, noul):
    """Parámetros de calibración sobre (probs, y) con las funciones de `calibrar.py`: T (choice) o Platt (noul)."""
    if noul:
        s = np.log(np.clip(p[:, 1], EPS, 1)) - np.log(np.clip(p[:, 0], EPS, 1))
        prm, aj = CAL.ajustar("noul", [torch.tensor([float(v)]) for v in s], [int(v) for v in y], {"a": 1.0, "b": 0.0})
    else:
        prm, aj = CAL.ajustar("choice", [torch.tensor(np.log(np.clip(r, EPS, 1)), dtype=torch.float32) for r in p],
                              [int(v) for v in y], {"T": 1.0})
    return prm, aj


def _aplicar_cal(p, prm, noul):
    if noul:
        s = torch.tensor(np.log(np.clip(p[:, 1], EPS, 1)) - np.log(np.clip(p[:, 0], EPS, 1)), dtype=torch.float32)
        pt = torch.sigmoid(prm["a"] * s + prm["b"]).numpy().astype(float)
        return np.stack([1 - pt, pt], 1)
    z = torch.tensor(np.log(np.clip(p, EPS, 1)), dtype=torch.float32) / prm["T"]
    return F.softmax(z, -1).numpy().astype(float)


def calibrar_oof(p, y, ids, tipo):
    """Calibra `p` (n,C) fuera de pliegue: los parámetros de cada fila salen del otro pliegue de test (partición de la cascada).
    -> (probs calibradas, [parámetros por pliegue])."""
    noul = tipo == "noul" and p.shape[1] == 2
    pl = np.array([pliegue(i, SEMILLA) for i in ids])
    out, prms = np.zeros_like(p, dtype=float), []
    for f in (0, 1):
        ev, aj = pl == f, pl != f
        prm, aj_ok = _ajustar_cal(p[aj], y[aj], noul)
        out[ev] = _aplicar_cal(p[ev], prm, noul)
        prms.append({**prm, "ajustado": bool(aj_ok)})
    return out, prms


def metricas_calibracion(p_antes, p_despues, y, filas=None):
    """ECE, NLL, cobertura a precisión 0,95 (`calibrar.tau_escalate`) y AUROC de la confianza; en CLINC, también el de `escalate`."""
    r = {}
    for nombre, p in (("antes", p_antes), ("despues", p_despues)):
        conf, ok = p.max(1), p.argmax(1) == y
        tau, cob, prec = CAL.tau_escalate(conf, ok)
        r[nombre] = {"ece": M.ece(conf, ok), "nll": nll(p, y), "tau": tau, "cobertura_p95": cob, "precision_cubierta": prec,
                     "auroc_acierto": CAL.auroc(conf, ok), "exactitud": float(ok.mean())}
        if filas is not None and any(r_["etiqueta"] == "escalate" for r_ in filas):
            esc = np.array([r_["etiqueta"] == "escalate" for r_ in filas])
            r[nombre]["auroc_escalate"] = CAL.auroc(1 - conf, esc)   # menos confianza = más probable de ser escalate
    return r


def veredicto_h2(cal):
    ece_ok = [t for t, r in cal.items() if r["despues"]["ece"] <= 0.05]
    cob_ok = [t for t, r in cal.items() if r["despues"]["cobertura_p95"] >= 0.70]
    n = len(cal)
    return {"ece_ok": ece_ok, "cobertura_ok": cob_ok,
            "cumple": len(ece_ok) == n and len(cob_ok) >= 3, "n": n}


def calibracion_md(cal, v, modo):
    f = lambda x: "-" if x is None or x != x else "%.3f" % x
    L = ["# Calibración de la conjunta (cabeza %s, T o Platt fuera de pliegue sobre test)" % modo, "",
         "| tarea | ECE antes | ECE después | NLL antes | NLL después | cobertura p≥0,95 antes | después | AUROC acierto | AUROC escalate |",
         "|" + "---|" * 9]
    for t, r in cal.items():
        a, d = r["antes"], r["despues"]
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (t, f(a["ece"]), f(d["ece"]), f(a["nll"]), f(d["nll"]),
                                                                  f(a["cobertura_p95"]), f(d["cobertura_p95"]), f(d["auroc_acierto"]),
                                                                  f(d.get("auroc_escalate"))))
    L += ["", "H2 (ECE ≤ 0,05 en las %d tareas y cobertura ≥ 70 %% en ≥ 3): ECE ok en %d/%d (%s); cobertura ok en %d/%d (%s) → %s." % (
        v["n"], len(v["ece_ok"]), v["n"], ", ".join(v["ece_ok"]) or "ninguna", len(v["cobertura_ok"]), v["n"],
        ", ".join(v["cobertura_ok"]) or "ninguna", "NO EVALUABLE (menos de 5 tareas)" if v["n"] < 5 else ("CUMPLE" if v["cumple"] else "REFUTADA")),
        "Los parámetros de cada fila salen del otro pliegue de test; la cobertura usa el τ que da precisión ≥ 0,95 sobre el mismo test "
        "(como en T2.4), no uno ajustado fuera de pliegue. En `cvtest` las probabilidades del pliegue de ajuste salen de una cabeza "
        "que vio el pliegue evaluado: dependencia débil (1 parámetro), no eliminada."]
    return "\n".join(L)


def h1_md(res_train, res_cv):
    """H1 con los resultados de las dos modalidades: hatecheck ≥ L2 − 1 punto y ≤ 1 punto de pérdida en las demás (frente a `train`)."""
    f = lambda r: r["global"]["macro_f1"]
    L = ["| tarea | L2 | conjunta (train) | conjunta (cvtest) | Δ cvtest − train | Δ cvtest − L2 |", "|---|---|---|---|---|---|"]
    perd, hate = [], None
    for t, r in res_cv.items():
        tr, cv, l2 = f(res_train[t]["conj"]), f(r["conj"]), f(r["l2"])
        L.append("| %s | %.3f | %.3f | %.3f | %+.3f | %+.3f |" % (t, l2, tr, cv, cv - tr, cv - l2))
        if t == "hatecheck":
            hate = cv >= l2 - 0.01
        elif cv - tr < -0.01:
            perd.append(t)
    ok = hate is True and not perd
    L += ["", "H1: hatecheck %s; tareas que pierden > 1 punto frente a `train`: %s → %s." % (
        "n/d" if hate is None else ("≥ L2 − 1 punto" if hate else "< L2 − 1 punto"), ", ".join(perd) or "ninguna",
        "NO EVALUABLE (sin hatecheck)" if hate is None else ("CUMPLE" if ok else "REFUTADA"))]
    return "\n".join(L)


# --- evaluación ------------------------------------------------------------------------------------------------------
def predicciones(filas, probs, ms):
    ms = np.broadcast_to(np.asarray(ms, float), (len(filas),))
    return [{"id": r["id"], "probs": dict(zip(r["opciones"], map(float, p))), "ms": round(float(t), 3)}
            for r, p, t in zip(filas, probs, ms)]


def escribir(ruta, preds):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(p, ensure_ascii=False) + "\n" for p in preds)


def referencias():
    """{tarea: {l0, knn32, mejor}} macro-F1 global de `model/lineas_base/resultados.json`; mejor = máximo de L0, kNN-32 y THX-01."""
    with open(EV.LB) as f:
        base = json.load(f)
    out = {}
    for t, b in base.items():
        g = lambda n: ((b.get(n) or {}).get("global") or b.get(n) or {}).get("macro_f1") if b.get(n) else None
        vals = [v for v in (g("l0_tfidf_lr"), g("e5_knn32"), g("thx01")) if v is not None]
        out[t] = {"l0": g("l0_tfidf_lr"), "knn32": g("e5_knn32"), "mejor": max(vals) if vals else None}
    return out


def tabla_delta(res, ref, elegidas):
    """res = {tarea: {"l0", "l2", "conj", "lr", "puerta"}} (resultados de CE.evaluar). Marca H1: la conjunta supera a la mejor
    capa sola (L0 completo, L0 de las líneas base, L2) en ≥ 1 punto en ≥ 3 tareas y cumple el listón (≥ 0,95 × la mejor referencia) en ≥ 4."""
    f = lambda r: r["global"]["macro_f1"]
    v = lambda x: "-" if x is None else "%.3f" % x
    lin = ["| tarea | n | L0 (línea base) | L0 (train completo) | L2+soporte | conjunta | cabeza | lr | puerta | Δ vs mejor capa | listón (0,95×mejor ref.) | cumple |",
           "|" + "---|" * 12]
    gana = supera = cumple = 0
    for t, r in res.items():
        capas = [x for x in (ref.get(t, {}).get("l0"), f(r["l0"]), f(r["l2"])) if x is not None]
        d = f(r["conj"]) - max(capas)
        mejor = ref.get(t, {}).get("mejor")
        liston = None if mejor is None else UMBRAL_LISTON * mejor
        ok = liston is not None and f(r["conj"]) >= liston
        gana += d >= UMBRAL_GANA
        supera += d > 0
        cumple += ok
        lin.append("| %s | %d | %s | %.3f | %.3f | %.3f | %s | %.3f | %.3f | %+.3f | %s | %s |" % (
            t, r["conj"]["global"]["n"], v(ref.get(t, {}).get("l0")), f(r["l0"]), f(r["l2"]), f(r["conj"]), elegidas[t],
            f(r["lr"]), f(r["puerta"]), d, v(liston), "-" if liston is None else ("sí" if ok else "no")))
    n = len(res)
    lin += ["", "H1 (conjunta ≥ mejor capa + 0,01 en ≥ 3 de 5 y listón en ≥ 4 de 5): %d/%d tareas con Δ ≥ +0,01; %d/%d con el listón." % (gana, n, cumple, n),
            "Refutación (no supera a la mejor capa en ≥ 3 tareas): %d/%d tareas con Δ > 0 → %s." % (
                supera, n, "REFUTADA" if supera < 3 else "no refutada"),
            "Mejor capa = máximo de L0 (línea base), L0 (train completo) y L2 con soporte; «cabeza» es la elegida por CV en train."]
    return "\n".join(lin)


def evaluar_tareas(tareas, caches, sal, renombrar, modo_cabeza="train", calibrar=False, comparar_con=None):
    """tareas {t: (train, test)}, caches {t: dict de características}. Escribe todo en `sal` y devuelve (res, res_r)."""
    sal = Path(sal)
    res, res_r, res_l2r, elegidas, cab, cal = {}, {}, {}, {}, {}, {}
    for t, (train, test) in tareas.items():
        c = caches[t]
        if modo_cabeza == "cvtest":
            a = ajustar_y_predecir_cvtest(c, [r["id"] for r in test])
        else:
            a = ajustar_y_predecir(c)
        ms = c["te_ms"] + a["ms_cabeza"]
        preds = {"conj": predicciones(test, a["probs"], ms), "l0": predicciones(test, c["te_l0"], c["te_ms"]),
                 "l2": predicciones(test, c["te_l2"], c["te_ms"]),
                 "lr": predicciones(test, a["probs_tipo"]["lr"], ms), "puerta": predicciones(test, a["probs_tipo"]["puerta"], ms)}
        res[t] = {k: CE.evaluar(test, p) for k, p in preds.items()}
        for carp, k in (("pred", "conj"), ("pred_l0", "l0"), ("pred_l2", "l2")):
            escribir(sal / carp / (t + ".jsonl"), preds[k])
        elegidas[t] = a["elegida"]
        cab[t] = {k: a[k] for k in ("elegida", "lambda", "por_tipo", "cv_nll")}
        if calibrar:
            y = c["te_y"]
            pc, prms = calibrar_oof(a["probs"], y, [r["id"] for r in test], test[0]["tipo"])
            cal[t] = metricas_calibracion(a["probs"], pc, y, test)
            cal[t]["parametros"] = prms
            escribir(sal / "pred_cal" / (t + ".jsonl"), predicciones(test, pc, ms))
        print("== %s: cabeza %s (λ=%s)  L0 %.3f  L2 %.3f  conjunta %.3f" % (
            t, a["elegida"], a["lambda"], res[t]["l0"]["global"]["macro_f1"], res[t]["l2"]["global"]["macro_f1"],
            res[t]["conj"]["global"]["macro_f1"]), flush=True)
        if renombrar:
            ren = [D.renombrar_fila(r) for r in test]
            pr = predicciones(ren, a["probs_r"], ms)
            escribir(sal / "pred_renombrado" / (t + ".jsonl"), pr)
            res_r[t] = CE.evaluar(ren, pr)
            res_l2r[t] = CE.evaluar(ren, predicciones(ren, c["r_l2"], c["te_ms"]))
    for nombre, sel in (("resultados.json", lambda r: r["conj"]), ("resultados_l0.json", lambda r: r["l0"]),
                        ("resultados_l2.json", lambda r: r["l2"])):
        (sal / nombre).write_text(json.dumps({t: sel(r) for t, r in res.items()}, indent=1, ensure_ascii=False))
    (sal / "cabezas.json").write_text(json.dumps(cab, indent=1, ensure_ascii=False))
    delta = tabla_delta(res, referencias(), elegidas)
    (sal / "delta.md").write_text(delta + "\n", encoding="utf-8")
    print(delta)
    if calibrar:
        v = veredicto_h2(cal)
        (sal / "calibracion.json").write_text(json.dumps({"tareas": cal, "h2": v, "modo_cabeza": modo_cabeza}, indent=1, ensure_ascii=False))
        md = calibracion_md({t: {k: r[k] for k in ("antes", "despues")} for t, r in cal.items()}, v, modo_cabeza)
        (sal / "calibracion.md").write_text(md + "\n", encoding="utf-8")
        print(md)
    if comparar_con:
        base = json.loads((Path(comparar_con) / "resultados.json").read_text())
        ref = {t: {"conj": base[t]} for t in res if t in base}
        md = h1_md(ref, res)
        (sal / "h1.md").write_text(md + "\n", encoding="utf-8")
        print(md)
    if renombrar:
        (sal / "resultados_renombrado.json").write_text(json.dumps(res_r, indent=1, ensure_ascii=False))
        orig = {"conjunta:" + t: r["conj"] for t, r in res.items()} | {"L2:" + t: r["l2"] for t, r in res.items()}
        ren = {"conjunta:" + t: r for t, r in res_r.items()} | {"L2:" + t: r for t, r in res_l2r.items()}
        txt, _, _ = EV.tabla_caida(orig, ren)
        txt += "\n\nL0 no depende del nombre de la opción (se busca por posición): su caída es 0 por construcción."
        (sal / "caida.md").write_text(txt + "\n", encoding="utf-8")
        print("== caída al renombrar\n" + txt)
    return res, res_r


# --- CLI -------------------------------------------------------------------------------------------------------------
def fase_caracteristicas(a, tareas):
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    modelo, ck = EV.cargar_modelo(a.ckpt, a.device)
    enc = Codificador(device=a.device, cache_mensajes=True)  # cada mensaje pasa por e5 una vez (soporte, train y test se repiten)
    enc.cargar_enc(ck.get("enc"))
    sha = hash_fichero(a.ckpt)
    for t, (train, test) in tareas.items():
        meta = meta_de(train, test, PLIEGUES, SOPORTE, SEMILLA, sha)
        ruta = cache / (t + ".npz")
        if ruta.exists() and leer_cache(ruta)[1] == meta:
            print("== %s: características en la caché" % t, flush=True)
            continue
        t0 = time.time()
        c = caracteristicas(modelo, enc, train, test)
        guardar_cache(ruta, c, meta)
        enc.msgs.clear()
        print("== %s: características de %d train + %d test en %.0f s" % (t, len(train), len(test), time.time() - t0), flush=True)


def fase_cabezas(a, tareas):
    caches = {}
    raiz = Path(a.desde_cache) if a.desde_cache else Path(a.cache)
    if a.desde_cache and (raiz / "caracteristicas").is_dir():
        raiz = raiz / "caracteristicas"
    for t, (train, test) in tareas.items():
        c, meta = leer_cache(raiz / (t + ".npz"))
        esperado = meta_de(train, test, PLIEGUES, SOPORTE, SEMILLA)
        for k in ("ids_train", "ids_test", "k", "soporte", "semilla"):
            if meta[k] != esperado[k]:
                raise SystemExit("la caché de %s no corresponde a estos datos (%s); bórrala y repite la fase de características" % (t, k))
        caches[t] = c
    evaluar_tareas(tareas, caches, a.salida, a.renombrar, a.modo_cabeza, a.calibrar, a.comparar_con)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", help="checkpoint de L2 (fase caracteristicas)")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--datos", required=True, help="directorio de model.datos.convertir")
    ap.add_argument("--cache", help="dónde van las características (por defecto, SALIDA/caracteristicas)")
    ap.add_argument("--fase", choices=("todo", "caracteristicas", "cabezas"), default="todo")
    ap.add_argument("--tareas", default="", help="lista separada por comas (por defecto, todas las que tienen train)")
    ap.add_argument("--renombrar", action="store_true", help="evalúa también con las opciones renombradas a A/B/C…")
    ap.add_argument("--modo-cabeza", choices=("train", "cvtest"), default="train",
                    help="train: la cabeza se entrena con train (T2.2c); cvtest: 2 pliegues de test, partición de model/cascada")
    ap.add_argument("--calibrar", action="store_true", help="T (choice) o Platt (noul) fuera de pliegue, ECE, cobertura a p ≥ 0,95 y AUROC")
    ap.add_argument("--desde-cache", help="DIR con las <tarea>.npz (o DIR/caracteristicas/): solo la fase de cabezas, sin codificador ni GPU")
    ap.add_argument("--comparar-con", help="DIR con el resultados.json de la modalidad train: escribe h1.md (solo con cvtest)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--max-filas", type=int, default=0, help="tope de filas de train y de test por tarea (0 = todas)")
    a = ap.parse_args(argv)
    a.cache = a.cache or str(Path(a.salida) / "caracteristicas")
    torch.manual_seed(SEMILLA)
    tareas = cargar_tareas(a.datos, set(filter(None, a.tareas.split(","))), a.max_filas)
    if not tareas:
        raise SystemExit("ninguna tarea con train en %s" % a.datos)
    Path(a.salida).mkdir(parents=True, exist_ok=True)
    if a.desde_cache:
        a.fase = "cabezas"
    if a.fase in ("todo", "caracteristicas"):
        if not a.ckpt:
            raise SystemExit("--ckpt es obligatorio en la fase de características")
        fase_caracteristicas(a, tareas)
    if a.fase in ("todo", "cabezas"):
        fase_cabezas(a, tareas)
    return 0


if __name__ == "__main__":
    sys.exit(main())
