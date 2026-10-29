#!/usr/bin/env python3
"""T4.5b: ablación de H2. Reconstruye fila a fila la decisión de L2c (la cabeza conjunta del servidor) desde el `.chispa` que
produce `chispa train --conjunta` y sustituye, de uno en uno, los componentes del servidor por los de `model/l2/conjunta.py`.

  A codificador   srv: el ONNX int8 del .chispa            ref: PyTorch con el checkpoint (fp32)
  B torres        srv: int8 de ESQUEMAS                    ref: `modelo.torre` en fp32
  C prototipos    srv: int8 de CONJ                        ref: `prototipos(modelo, enc, soporte)` en fp32
  D simproto      srv: S cuantizada a int8 por ranura, como el producto entero de server/decide   ref: S en float
                  (C y D son independientes: C pone los valores de los prototipos y D si S se cuantiza)
  E L0            srv: L0 de Chispa (binario del servidor)  ref: L0 de sklearn de conjunta.py; la cabeza es la del .chispa
                  (entrenada con el L0 de sklearn fuera de pliegue). `E+` (extra): L0 de Chispa y cabeza reentrenada con L0 de
                  Chispa fuera de pliegue.
  F entradas      srv: el atajo de la cascada forzada (L0 responde si su confianza llega a τ(L0) = 1)   ref: solo la cabeza.
                  Además se compara con el pred.jsonl del servidor (el campo `probs`).

  ablacion.py correr --tarea massive --chispa M.chispa --prep PREP/massive --ckpt mejor.pt --salida DIR [...]

Corridas: 1 todo «servidor», 2 todo «referencia» (deben dar los objetivos ±0,5 puntos: si no, el arnés está mal y no hay
conclusiones), 3 una sustitución cada vez de servidor a referencia (y, de añadido, de referencia a servidor).
El núcleo (`Arnes`) es numpy puro; torch, onnxruntime y sklearn solo entran al construir las fuentes de una tarea real."""
import argparse
import json
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
REPO = AQUI.parents[2]
for _p in (str(REPO), str(REPO / "sdk" / "python"), str(REPO / "server" / "deploy" / "aws")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

COMPONENTES = ("A", "B", "C", "D", "E", "F")
NOMBRES = {"A": "codificador", "B": "torres (ESQUEMAS)", "C": "prototipos (CONJ)", "D": "simproto int8", "E": "L0 (Chispa/sklearn)",
           "F": "atajo de la cascada"}
OBJETIVOS = {"massive": (0.771, 0.817), "clinc150": (0.846, 0.890)}   # (servidor, referencia): LEEME de e2e-20261028
TOL_REPRO = 0.005     # ±0,5 puntos
UMBRAL_CULPABLE = 0.03
EPS = 1e-6
PUERTO_L0 = 8091


# ---------------------------------------------------------------- lectura del .chispa
def leer_esquemas(b):
    """ESQUEMAS → {hash: (vec int8 (d,), escala)}. Disposición de format/chispa3/secciones.go: v1 empieza por dim y lleva
    claves de 32 bytes; v2 por (2<<16 | dim) y claves de 16 bytes (HashEsquema2)."""
    u, n = struct.unpack_from("<II", b, 0)
    if u >> 16 not in (0, 2):   # como DecodificarEsquemas en Go
        raise ValueError(f"ESQUEMAS versión {u >> 16} desconocida")
    dim, kb = u & 0xFFFF, (16 if u >> 16 == 2 else 32)
    hs, ss, vs = 8, 8 + kb * n, 8 + (kb + 4) * n
    esc = np.frombuffer(b, "<f4", n, ss)
    vec = np.frombuffer(b, np.int8, n * dim, vs).reshape(n, dim)
    return {bytes(b[hs + kb * i:hs + kb * i + kb]): (vec[i], float(esc[i])) for i in range(n)}


def leer_conj(b):
    """CONJ → lista de entradas (format/chispa3/conj.go)."""
    ver, n = struct.unpack_from("<II", b, 0)
    off, out = 8, []
    for _ in range(n):
        h = bytes(b[off:off + 32])
        _, K, d, C, nw = struct.unpack_from("<5I", b, off + 32)
        off += 52
        f = np.frombuffer(b, "<f4", 5 + nw, off)
        off += 4 * len(f)
        clases = []
        for _ in range(C):
            (ln,) = struct.unpack_from("<H", b, off)
            clases.append(bytes(b[off + 2:off + 2 + ln]).decode("utf-8"))
            off += 2 + ln
        escala = np.frombuffer(b, "<f4", C * K, off).reshape(C, K)
        off += 4 * C * K
        proto = np.frombuffer(b, np.int8, C * K * d, off).reshape(C, K, d)
        off += C * K * d
        out.append({"hash": h, "K": K, "d": d, "T": float(f[0]), "beta": float(f[1]), "esc": f[2:5].astype(float),
                    "w": f[5:5 + nw].astype(float), "clases": clases, "escala": escala, "proto": proto})
    return out


def hash_esquema(pregunta, opciones):
    from chispa import formato
    return formato.hash_esquema(pregunta, opciones)


# ---------------------------------------------------------------- núcleo numpy (réplica de server/decide/l2c.go)
def softplus(x):
    return np.logaddexp(0.0, x)


def maxsim(S, H):
    """S (K,d), H (n,d) → (n,): max_k softplus(h · s_k)."""
    return softplus(S.astype(np.float64) @ H.astype(np.float64).T).max(0)


def _maxmedia(M, C, Kp):
    """M (Ks, C·Kp) → (C,): media sobre las ranuras del mensaje del máximo sobre los Kp prototipos de la clase."""
    return M.reshape(M.shape[0], C, Kp).max(-1).mean(0)


def simproto_float(S, P):
    """S (K,d), P (C,Kp,d) → (C,) en float: lo que calcula `model/l2/modelo.simproto`."""
    C, Kp, d = P.shape
    return _maxmedia(S.astype(np.float64) @ P.reshape(C * Kp, d).astype(np.float64).T, C, Kp)


def cuantizar_ranuras(S):
    """Como `cuantizarRanura`: escala = máx|s|/127 en float32, q = redondeo a par de s/escala."""
    S = S.astype(np.float32)
    esc = np.abs(S).max(1) / np.float32(127)
    seguro = np.where(esc > 0, esc, np.float32(1))
    q = np.rint(S / seguro[:, None]) * (esc > 0)[:, None]
    return q, esc


def deq_ranuras(S):
    """La S que ve el producto entero del servidor: q · escala por ranura."""
    q, esc = cuantizar_ranuras(S)
    return q.astype(np.float64) * esc.astype(np.float64)[:, None]


def simproto_int8(S, proto, escala):
    """Réplica de `simproto` de server/decide: producto entero exacto (float64 es exacto aquí: |dot| < 2^22) por las
    escalas de la ranura y del prototipo, en float64."""
    C, Kp, d = proto.shape
    q, esc = cuantizar_ranuras(S)
    dots = q.astype(np.float64) @ proto.reshape(C * Kp, d).astype(np.float64).T
    v = dots * esc.astype(np.float64)[:, None] * escala.reshape(1, C * Kp).astype(np.float64)
    return _maxmedia(v, C, Kp)


def centrar(x):
    return x - x.mean()


def cabeza_lr(l0, sp, l2, esc, w):
    """Logits de la cabeza `lr` (`logitsLR` / `conjunta.Cabeza._x`) → softmax. l0, sp, l2: (n,) de una fila."""
    a = centrar(np.log(np.clip(l0, EPS, 1)))
    c = centrar(np.log(np.clip(l2, EPS, 1)))
    b = centrar(sp)
    t0, t2 = (l0 == l0.max()).astype(float), (l2 == l2.max()).astype(float)
    lg = w[0] * a / esc[0] + w[1] * b / esc[1] + w[2] * c / esc[2] + w[3] * t0 + w[4] * t2 + w[5] * t0 * t2
    e = np.exp(lg - lg.max())
    return e / e.sum()


class Fuentes:
    """Todo lo que el arnés necesita de una tarea, ya calculado por fuente.

    filas: filas de test (dicts con id, opciones, etiqueta, …)
    S[x]: lista de arrays (K,d), x ∈ {srv, ref};  H[x]: {opción: (d,)};  P[x]: (C,Kp,d) float;
    P8: (proto int8 (C,Kp,d), escala (C,Kp)) de CONJ;  clases: nombres de las C clases de CONJ
    L0[x]: lista de arrays (n_opciones,) por fila, x ∈ {srv, ref}
    cabeza: {T, beta, esc, w};  cabeza_e: ídem, reentrenada con el L0 de Chispa (opcional)."""

    def __init__(self, filas, S, H, P, P8, clases, L0, cabeza, cabeza_e=None):
        self.filas, self.S, self.H, self.P, self.P8, self.clases = filas, S, H, P, P8, clases
        self.L0, self.cabeza, self.cabeza_e = L0, cabeza, cabeza_e


class Arnes:
    def __init__(self, f):
        self.f = f
        self._sims, self._sp = {}, {}
        self.idx_clase = {c: i for i, c in enumerate(f.clases)}

    def sims(self, a, b):
        """MaxSim por fila y opción con las ranuras de `a` y las torres de `b`."""
        if (a, b) not in self._sims:
            f = self.f
            self._sims[(a, b)] = [maxsim(S, np.stack([f.H[b][o] for o in r["opciones"]])) for S, r in zip(f.S[a], f.filas)]
        return self._sims[(a, b)]

    def sp_clases(self, a, c, d):
        """simproto por fila y clase de CONJ (C,) con ranuras de `a`, prototipos de `c` y aritmética de `d`."""
        if (a, c, d) not in self._sp:
            f = self.f
            # D srv: cada ranura de S se cuantiza a int8 antes del producto, que con prototipos int8 es el entero del servidor
            # (`simproto_int8`) y con prototipos fp32 (C ref) es el mismo producto con la S cuantizada. D ref: S en float.
            self._sp[(a, c, d)] = [simproto_float(deq_ranuras(S) if d == "srv" else S, f.P[c]) for S in f.S[a]]
        return self._sp[(a, c, d)]

    def probs(self, cfg):
        """Probabilidades por fila (en el orden de sus opciones) con la configuración cfg {A..F: 'srv'|'ref'|'srv+'}."""
        f, cb = self.f, self.f.cabeza
        if cfg["E"] == "srv+":
            if f.cabeza_e is None:
                raise ValueError("E+ necesita la cabeza reentrenada con L0 de Chispa (cabeza_e)")
            cb = f.cabeza_e
        sims = self.sims(cfg["A"], cfg["B"])
        sps = self.sp_clases(cfg["A"], cfg["C"], cfg["D"])
        l0s = f.L0["ref" if cfg["E"] == "ref" else "srv"]
        out = []
        for i, r in enumerate(f.filas):
            ops = r["opciones"]
            col = [self.idx_clase.get(o, -1) for o in ops]
            sp = np.array([sps[i][c] if c >= 0 else 0.0 for c in col])
            z = (sims[i] + cb["beta"] * sp) / cb["T"]
            l2 = np.exp(z - z.max())
            l2 /= l2.sum()
            l0 = l0s[i]
            p = cabeza_lr(l0, sp, l2, cb["esc"], cb["w"])
            if cfg["F"] == "srv" and f.L0["srv"][i].max() >= 1.0:   # τ(L0) = 1 del modo forzado: responde L0
                p = f.L0["srv"][i] / f.L0["srv"][i].sum()
            out.append(p)
        return out


def a_preds(filas, probs):
    return [{"id": r["id"], "probs": {o: float(x) for o, x in zip(r["opciones"], p)}} for r, p in zip(filas, probs)]


def macro_f1(filas, probs):
    from model.evaluacion import chispa_eval as CE
    return float(CE.evaluar(filas, a_preds(filas, probs))["global"]["macro_f1"])


def cfg_de(base, **cambios):
    return {**{k: base for k in COMPONENTES}, **cambios}


def corridas(arnes, extra_e_mas=False):
    """[(nombre, cfg, macro-F1)] de las corridas 1, 2 y 3 (y las inversas y E+)."""
    f, res = arnes.f, []

    def anota(nombre, cfg, tipo):
        res.append({"nombre": nombre, "tipo": tipo, "cfg": cfg, "macro_f1": macro_f1(f.filas, arnes.probs(cfg))})
    anota("1 todo servidor", cfg_de("srv"), "todo-srv")
    anota("2 todo referencia", cfg_de("ref"), "todo-ref")
    for x in COMPONENTES:
        anota(f"3{x} servidor con {x} de referencia ({NOMBRES[x]})", cfg_de("srv", **{x: "ref"}), "sustituye")
    for x in COMPONENTES:
        anota(f"4{x} referencia con {x} de servidor ({NOMBRES[x]})", cfg_de("ref", **{x: "srv"}), "inversa")
    if extra_e_mas:
        anota("5 servidor con E+ (L0 de Chispa y cabeza reentrenada con él)", cfg_de("srv", E="srv+"), "extra")
    return res


def tabla(res, objetivo, tarea):
    """-> (markdown, veredicto dict). Δ en puntos de macro-F1 frente a «1 todo servidor»."""
    r1 = next(r for r in res if r["tipo"] == "todo-srv")["macro_f1"]
    r2 = next(r for r in res if r["tipo"] == "todo-ref")["macro_f1"]
    o1, o2 = objetivo
    ok1, ok2 = abs(r1 - o1) <= TOL_REPRO, abs(r2 - o2) <= TOL_REPRO
    lin = [f"### {tarea}", "", "| corrida | macro-F1 | Δ vs 1 (puntos) |", "|---|---|---|"]
    for r in res:
        d = (r["macro_f1"] - r1) * 100
        r["delta_pts"] = d
        lin.append(f"| {r['nombre']} | {r['macro_f1']:.4f} | {'' if r['tipo'] == 'todo-srv' else f'{d:+.2f}'} |")
    sust = [r for r in res if r["tipo"] == "sustituye"]
    culpables = [r["nombre"][1] for r in sust if r["delta_pts"] >= UMBRAL_CULPABLE * 100]
    hueco = (r2 - r1) * 100
    suma = sum(max(r["delta_pts"], 0) for r in sust)
    v = {"valido": ok1 and ok2, "run1": r1, "run2": r2, "objetivo_srv": o1, "objetivo_ref": o2, "hueco_pts": hueco,
         "suma_deltas_pts": suma, "culpables": culpables}
    lin += ["", f"- Reproducción: corrida 1 = {r1:.4f} (objetivo {o1:.3f} ±{TOL_REPRO}) {'ok' if ok1 else 'NO'}; "
            f"corrida 2 = {r2:.4f} (objetivo {o2:.3f} ±{TOL_REPRO}) {'ok' if ok2 else 'NO'}.",
            f"- Hueco 2 − 1 = {hueco:+.2f} puntos; suma de las sustituciones (solo las positivas) = {suma:+.2f}."]
    if not v["valido"]:
        lin.append("- **EL ARNÉS ESTÁ MAL (o falta una pieza): una de las corridas 1/2 no reproduce su objetivo. No hay conclusiones.**")
    elif culpables:
        lin.append(f"- Culpable(s) (Δ ≥ {UMBRAL_CULPABLE * 100:.0f} puntos): {', '.join(culpables)}.")
    else:
        lin.append(f"- Ningún componente pasa de {UMBRAL_CULPABLE * 100:.0f} puntos por sí solo: H refutada"
                   f"{'; la suma no cierra el hueco' if suma < 0.7 * hueco else ''}.")
    return "\n".join(lin), v


def comparar_servidor(filas, probs, pred):
    """F: probs del arnés (todo servidor) frente al pred.jsonl del servidor (campo probs). -> dict de acuerdo."""
    por = {p["id"]: p for p in pred}
    n = d_max = d_sum = top = 0
    capas, malas = {}, []
    for r, p in zip(filas, probs):
        s = por.get(r["id"])
        if s is None or "error" in s:
            continue
        q = np.array([s["probs"].get(o, 0.0) for o in r["opciones"]])
        n += 1
        d = float(np.abs(p - q).max())
        d_max, d_sum = max(d_max, d), d_sum + d
        ok = int(np.argmax(p)) == int(np.argmax(q))
        top += ok
        capas[s.get("layer", "?")] = capas.get(s.get("layer", "?"), 0) + 1
        if not ok and len(malas) < 5:
            malas.append({"id": r["id"], "arnes": r["opciones"][int(np.argmax(p))], "servidor": r["opciones"][int(np.argmax(q))]})
    return {"n": n, "acuerdo_top1": top / max(n, 1), "dif_max": d_max, "dif_media": d_sum / max(n, 1), "capas_servidor": capas,
            "desacuerdos": malas}


# ---------------------------------------------------------------- fuentes reales
def leer_jsonl(ruta):
    return [json.loads(l) for l in open(ruta, encoding="utf-8") if l.strip()]


def escribir_jsonl(ruta, filas):
    with open(ruta, "w", encoding="utf-8") as f:
        for r in filas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def probs_de_pred(filas, pred):
    """Probabilidades de un pred.jsonl en el orden de las opciones de cada fila."""
    por = {p["id"]: p["probs"] for p in pred}
    return [np.array([por[r["id"]].get(o, 0.0) for o in r["opciones"]], float) for r in filas]


def servir_l0(servidor, chispa, filas, puerto=PUERTO_L0, tok=None):
    """Probabilidades del L0 de Chispa del .chispa: el binario del servidor con L0 como única capa que responde (τ = 0)."""
    import urllib.request
    import e2e_util
    cfg = {"capas": [{"nombre": "L0", "tau": 0.0}, {"nombre": "L1", "tau": 1.0}, {"nombre": "L2", "tau": 1.0},
                     {"nombre": "L3", "tau": 1.0}], "cache_esquemas": 1024, "cache_respuestas": 4096}
    with tempfile.TemporaryDirectory(prefix="abl-l0-") as t:
        t = Path(t)
        (t / "cfg.json").write_text(json.dumps(cfg))
        escribir_jsonl(t / "filas.jsonl", filas)
        cmd = [str(servidor), "-addr", f"127.0.0.1:{puerto}", "-modelo", str(chispa), "-config", str(t / "cfg.json")]
        if tok:
            cmd += ["-tok", str(tok)]
        log = open(t / "servidor.log", "w")
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(120):
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{puerto}/healthz", timeout=2).read()
                    break
                except OSError:
                    if p.poll() is not None:
                        raise RuntimeError("el servidor se cerró: " + (t / "servidor.log").read_text()[-500:])
                    time.sleep(1)
            else:
                raise RuntimeError("el servidor no responde en /healthz")
            ns = argparse.Namespace(url=f"http://127.0.0.1:{puerto}", test=str(t / "filas.jsonl"), salida=str(t / "pred.jsonl"), max=0)
            if e2e_util.cliente(ns):
                raise RuntimeError("errores del cliente con el servidor L0")
        finally:
            p.terminate()
            p.wait()
            log.close()
        pred = leer_jsonl(t / "pred.jsonl")
    capas = {x.get("layer") for x in pred}
    if capas != {"L0"}:
        raise RuntimeError(f"con τ(L0) = 0 todo debía responder L0 y salieron las capas {capas}")
    return pred


def l0_chispa_fuera_de_pliegue(servidor, train, esquema, repo, k, fold, python=sys.executable):
    """L0 de Chispa fuera de pliegue: por pliegue, `chispa train` (solo L0, mismo entrenador y topes que el .chispa) con el resto
    y el servidor sobre el pliegue. -> array (n_train, C) en el orden de opciones (todas las filas comparten opciones)."""
    ops = train[0]["opciones"]
    out = np.zeros((len(train), len(ops)))
    with tempfile.TemporaryDirectory(prefix="abl-oof-") as t:
        t = Path(t)
        for f in range(k):
            dentro = [i for i in range(len(train)) if fold[i] == f]
            if not dentro:
                continue
            resto = [train[i] for i in range(len(train)) if fold[i] != f]
            escribir_jsonl(t / "ej.jsonl", [{"texto": r["texto"], "etiqueta": r["etiqueta"]} for r in resto])
            r = subprocess.run([python, "-m", "chispa", "train", "--ejemplos", str(t / "ej.jsonl"), "--esquema", str(esquema),
                                "--salida", str(t / "f.chispa"), "--repo", str(repo)], capture_output=True, text=True, cwd=repo)
            if r.returncode:
                raise RuntimeError("chispa train del pliegue falló:\n" + r.stderr[-1500:])
            pred = servir_l0(servidor, t / "f.chispa", [train[i] for i in dentro])
            out[dentro] = np.array(probs_de_pred([train[i] for i in dentro], pred))
    return out


def construir(a):
    """Fuentes reales de una tarea. Necesita torch, onnxruntime, sklearn y el repo (`model.l2`)."""
    import onnxruntime as ort
    import torch
    from chispa import formato
    from chispa.conjunta import cargar_ckpt, filas_train
    from chispa.datos import cargar_ejemplos, cargar_esquema
    from model.l2 import conjunta as C
    from model.l2 import datos as D
    from model.l2.modelo import prototipos, texto_opcion

    prep = Path(a.prep)
    sec = formato.leer(Path(a.chispa).read_bytes())
    esq, conj = leer_esquemas(sec[formato.ESQUEMAS]), leer_conj(sec[formato.CONJ])[0]
    q, _ = cargar_esquema(prep / "esquema.json")
    ejemplos = cargar_ejemplos(prep / "ejemplos.jsonl", q.id)
    train = filas_train(q, ejemplos)
    test = leer_jsonl(prep / "test.jsonl")[: a.max or None]
    ops = test[0]["opciones"]
    if any(r["opciones"] != ops or r["pregunta"] != q.question for r in test):
        raise ValueError("el arnés espera una sola pregunta choice con las mismas opciones en todo el test")
    modelo, enc = cargar_ckpt(a.ckpt, REPO)
    modelo.eval()
    sop = [r for _, r in D.soporte_t17a(train, C.SOPORTE, C.SEMILLA)]
    log = lambda *x: print("[ablacion]", *x, flush=True)

    # A: ranuras. ONNX del .chispa (batch 1, como el servidor) y PyTorch fp32.
    sess = ort.InferenceSession(sec[formato.L2], providers=["CPUExecutionProvider"])
    S_srv, S_ref = [], []
    with torch.no_grad():
        for i in range(0, len(test), 64):
            fs = test[i:i + 64]
            H, m = enc.tokens([r["texto"] for r in fs])
            S_ref += list(modelo.ranuras(H, m).double().numpy().astype(np.float32))
    for r in test:
        b = enc.tok(["query: " + r["texto"]], truncation=True, max_length=enc.max_tok, return_tensors="np")
        S_srv.append(sess.run(["S"], {"input_ids": b["input_ids"].astype(np.int64), "attention_mask": b["attention_mask"].astype(np.int64)})[0][0])
    log("A: ranuras de", len(test), "filas")

    # B: torres
    H_srv, H_ref = {}, {}
    with torch.no_grad():
        h = modelo.torre(enc.pasaje([texto_opcion(test[0], o) for o in ops])).numpy()
    for o, v in zip(ops, h):
        H_ref[o] = v
        vec, e = esq[hash_esquema(q.question, [o])]
        H_srv[o] = vec.astype(np.float64) * np.float32(e)

    # C: prototipos (fp32 de PyTorch y int8 de CONJ), en el orden de clases de CONJ
    idx, Pf = prototipos(modelo, enc, sop)
    if sorted(idx, key=idx.get) != conj["clases"]:
        raise ValueError("las clases del soporte no coinciden con las de CONJ")
    P_ref = Pf.detach().double().numpy()
    P_srv = conj["proto"].astype(np.float64) * conj["escala"].astype(np.float64)[..., None]

    # E: L0 de Chispa (servidor) y de sklearn
    if a.l0_chispa:
        l0c = probs_de_pred(test, leer_jsonl(a.l0_chispa))
    elif a.servidor:
        pred_l0 = servir_l0(a.servidor, a.chispa, test)
        l0c = probs_de_pred(test, pred_l0)
        if a.salida:
            escribir_jsonl(Path(a.salida) / "l0-chispa-test.jsonl", pred_l0)
    else:
        raise ValueError("hace falta --servidor o --l0-chispa para el L0 de Chispa")
    log("E: sklearn L0 sobre", len(train), "ejemplos")
    l0s, _ = C.probs_l0(train, test)
    f = Fuentes(test, {"srv": S_srv, "ref": S_ref}, {"srv": H_srv, "ref": H_ref}, {"srv": P_srv, "ref": P_ref},
                (conj["proto"], conj["escala"]), conj["clases"], {"srv": l0c, "ref": list(np.array(l0s, float))},
                {"T": conj["T"], "beta": conj["beta"], "esc": conj["esc"], "w": conj["w"]})
    ctx = {"modelo": modelo, "enc": enc, "train": train, "sop": sop, "q": q, "esquema": prep / "esquema.json", "C": C,
           "ops": ops}
    return f, ctx


def autocomprobacion(f, ctx, n=200):
    """El arnés «todo referencia» frente a `l2_filas` de conjunta.py (PyTorch): simproto y probs de L2 con soporte."""
    C, modelo, enc = ctx["C"], ctx["modelo"], ctx["enc"]
    idx, P = __import__("model.l2.modelo", fromlist=["prototipos"]).prototipos(modelo, enc, ctx["sop"])
    sub = f.filas[:n]
    sp, pr, _ = C.l2_filas(modelo, enc, sub, (idx, P))
    ar = Arnes(Fuentes(sub, {k: v[:n] for k, v in f.S.items()}, f.H, f.P, f.P8, f.clases, {k: v[:n] for k, v in f.L0.items()}, f.cabeza))
    sps = ar.sp_clases("ref", "ref", "ref")
    sims = ar.sims("ref", "ref")
    d_sp = max(float(np.abs(np.array([sps[i][ar.idx_clase[o]] for o in sub[i]["opciones"]]) - sp[i]).max()) for i in range(len(sub)))
    d_p = 0.0
    for i in range(len(sub)):
        z = (sims[i] + f.cabeza["beta"] * sp[i]) / f.cabeza["T"]
        p = np.exp(z - z.max())
        d_p = max(d_p, float(np.abs(p / p.sum() - pr[i]).max()))
    return {"n": len(sub), "dif_max_simproto": d_sp, "dif_max_probs_L2": d_p}


def extras(f, ctx, a, log):
    """E+ (L0 de Chispa fuera de pliegue y cabeza reentrenada) y la corrida «conjunta.py pura» (ids originales del train)."""
    C, modelo, enc, train = ctx["C"], ctx["modelo"], ctx["enc"], ctx["train"]
    out = {}
    fold = C.pliegues(train)
    y = np.array([r["opciones"].index(r["etiqueta"]) for r in train])
    log("extras: L2 con soporte sin la propia fila sobre", len(train), "ejemplos")
    tr_sp, tr_l2 = C.l2_train(modelo, enc, train, ctx["sop"])
    if a.servidor:
        log("extras: L0 de Chispa fuera de pliegue")
        tr_l0c = l0_chispa_fuera_de_pliegue(a.servidor, train, ctx["esquema"], REPO, C.PLIEGUES, fold)
        c = {"tr_fold": np.array(fold), "tr_y": y, "tr_l0": tr_l0c, "tr_sp": tr_sp, "tr_l2": tr_l2}
        (_, lam), _, _ = C.elegir(c, cabezas=("lr",))
        cab = C.Cabeza("lr", lam).ajustar(tr_l0c, tr_sp, tr_l2, y)
        f.cabeza_e = {"T": f.cabeza["T"], "beta": f.cabeza["beta"], "esc": np.array(cab.esc, float), "w": cab.w.numpy().astype(float)}
        out["lambda_e_mas"] = lam
    if a.datos_orig:
        log("extras: conjunta.py con los ids originales del train")
        orig = [r for r in leer_jsonl(a.datos_orig) if r.get("split") == "train"]
        orig = sorted(orig, key=lambda r: r["id"])
        fo = C.pliegues(orig)
        sop = [r for _, r in __import__("model.l2.datos", fromlist=["x"]).soporte_t17a(orig, C.SOPORTE, C.SEMILLA)]
        yo = np.array([r["opciones"].index(r["etiqueta"]) for r in orig])
        c = {"tr_fold": np.array(fo), "tr_y": yo, "tr_l0": C.l0_fuera_de_pliegue(orig, fo)}
        c["tr_sp"], c["tr_l2"] = C.l2_train(modelo, enc, orig, sop)
        (_, lam), _, _ = C.elegir(c, cabezas=("lr",))
        cab = C.Cabeza("lr", lam).ajustar(c["tr_l0"], c["tr_sp"], c["tr_l2"], yo)
        from model.l2.modelo import prototipos
        l0t, _ = C.probs_l0(orig, f.filas)
        te_sp, te_l2, _ = C.l2_filas(modelo, enc, f.filas, prototipos(modelo, enc, sop))
        p = cab.probs(np.array(l0t, float), te_sp, te_l2)
        out["conjunta_pura_macro_f1"] = macro_f1(f.filas, list(p))
        out["conjunta_pura_lambda"] = lam
    return out


def guardar(salida, inf, md):
    (salida / "ablacion.json").write_text(json.dumps(inf, indent=1, default=float))
    (salida / "ablacion.md").write_text(md + "\n")


def correr(a):
    t0 = time.time()
    log = lambda *x: print("[ablacion]", *x, flush=True)
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    f, ctx = construir(a)
    ar = Arnes(f)
    inf = {"tarea": a.tarea, "n": len(f.filas), "autocomprobacion": autocomprobacion(f, ctx)}
    log("autocomprobación:", inf["autocomprobacion"])
    res = corridas(ar)
    objetivo = (a.objetivo_srv if a.objetivo_srv is not None else OBJETIVOS.get(a.tarea, (None, None))[0],
                a.objetivo_ref if a.objetivo_ref is not None else OBJETIVOS.get(a.tarea, (None, None))[1])
    if None in objetivo:
        raise SystemExit(f"{a.tarea}: sin objetivos conocidos: pasa --objetivo-srv y --objetivo-ref")
    md, v = tabla(res, objetivo, a.tarea)
    inf.update({"corridas": res, "veredicto": v})
    if a.pred_servidor:
        pred = leer_jsonl(a.pred_servidor)
        inf["servidor_vs_arnes"] = comparar_servidor(f.filas, ar.probs(cfg_de("srv")), pred)
        inf["servidor_macro_f1"] = macro_f1(f.filas, probs_de_pred(f.filas, pred))
        md += (f"\n- F, pred.jsonl del servidor: macro-F1 {inf['servidor_macro_f1']:.4f}; acuerdo top-1 con la corrida 1 "
               f"{inf['servidor_vs_arnes']['acuerdo_top1']:.4f}, |Δp| máx {inf['servidor_vs_arnes']['dif_max']:.3g}, "
               f"capas del servidor {inf['servidor_vs_arnes']['capas_servidor']}.")
    guardar(salida, inf, md)   # lo principal queda en disco antes de los extras, que son lentos
    if time.time() - t0 < a.presupuesto_s and (a.extras):
        try:
            inf["extras"] = extras(f, ctx, a, log)
            if f.cabeza_e is not None:
                r = {"nombre": "5 servidor con E+ (L0 de Chispa, cabeza reentrenada con L0 de Chispa fuera de pliegue)", "tipo": "extra",
                     "cfg": cfg_de("srv", E="srv+"), "macro_f1": macro_f1(f.filas, ar.probs(cfg_de("srv", E="srv+")))}
                r["delta_pts"] = (r["macro_f1"] - v["run1"]) * 100
                inf["corridas"].append(r)
                md += f"\n- **E+** (cabeza reentrenada con L0 de Chispa): macro-F1 {r['macro_f1']:.4f} ({r['delta_pts']:+.2f} puntos vs 1)."
            if "conjunta_pura_macro_f1" in inf["extras"]:
                md += (f"\n- conjunta.py pura (ids originales del train, cabeza reentrenada): macro-F1 "
                       f"{inf['extras']['conjunta_pura_macro_f1']:.4f}.")
        except Exception as e:   # los extras no deben tirar las corridas principales
            inf["extras_error"] = f"{type(e).__name__}: {e}"
            md += f"\n- extras no calculados: {inf['extras_error']}"
    else:
        md += "\n- extras (E+, conjunta.py pura) omitidos: sin tiempo o sin --extras."
    inf["segundos"] = time.time() - t0
    guardar(salida, inf, md)
    print(md)
    return 0 if v["valido"] else 3


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("correr")
    p.add_argument("--tarea", required=True)
    p.add_argument("--chispa", required=True, help=".chispa de `chispa train --conjunta`")
    p.add_argument("--prep", required=True, help="PREP/<tarea> de e2e_util preparar (ejemplos.jsonl, esquema.json, test.jsonl)")
    p.add_argument("--ckpt", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--servidor", help="binario chispa-server (L0 de Chispa y L0 fuera de pliegue)")
    p.add_argument("--l0-chispa", help="pred.jsonl de un servidor con τ(L0) = 0 sobre el test (en vez de --servidor)")
    p.add_argument("--pred-servidor", help="pred.jsonl del modo forzado, para la comparación F")
    p.add_argument("--datos-orig", help="DATOS/<tarea>.jsonl de model.datos.convertir (ids originales) para «conjunta.py pura»")
    p.add_argument("--extras", action="store_true", help="E+ y conjunta.py pura (caros)")
    p.add_argument("--presupuesto-s", type=float, default=1e9, help="no empieza los extras si ya pasó este tiempo")
    p.add_argument("--max", type=int, default=0, help="filas de test (0 = todas)")
    p.add_argument("--objetivo-srv", type=float)
    p.add_argument("--objetivo-ref", type=float)
    a = ap.parse_args(argv)
    return correr(a)


if __name__ == "__main__":
    sys.exit(main())
