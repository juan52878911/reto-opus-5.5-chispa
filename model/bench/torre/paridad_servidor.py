"""Paridad servidor ↔ Python en JevBench: qué texto, qué tokens, qué s y qué CALIB usa cada uno, y a qué se debe cada discrepancia.

    python -m model.bench.torre.paridad_servidor diagnosticar --jevbench RUTA --ckpt mejor.pt --chispa M.chispa --capas capas_por_caso.jsonl \
        --pred pred/l2_k0.jsonl --salida DIR [--n 90] [--max-tok 256]
    python -m model.bench.torre.paridad_servidor reescribir --ckpt mejor.pt --entrada M.chispa --salida N.chispa [--calib-ckpt] [--l2-de OTRO.chispa]

`diagnosticar` no necesita el servidor en marcha (no tiene modo depuración y `server/` no se toca): recalcula en Python lo que hace
/v1/decide con el ONNX de consulta y la TORR del propio `.chispa`, con el texto de torre que arma el servidor (runtime/torre) y su CALIB,
y lo compara con las probabilidades que el servidor devolvió (`capas_por_caso.jsonl`) y con las de Python k = 0 (`l2_k0.jsonl`).
Cada discrepancia (distinta opción elegida) se atribuye cambiando UN factor del servidor al de Python y viendo si eso la cierra:
  calib        CALIB del `.chispa` → cabezas del checkpoint
  truncado     max_len de consulta del ONNX (metadato `chispa.consulta.max_len`, 128 si falta) → el del checkpoint
  texto_torre  texto de torre armado por el servidor (la petición) → el de `texto_opcion` / `texto_consulta` de Python
  onnx         ONNX de consulta y torre del `.chispa` (poda, int8) con h cuantizada a int8 → PyTorch fp32
Sin ningún factor suelto que la cierre: `combinada(a+b…)` si cambiando todos sí, y `otra` si ni así.
`reescribir` hace el `.chispa` de la pasada con la CALIB global (`--calib-ckpt`: las cabezas del checkpoint, que son las que usa Python)
y/o con la sección L2 (consulta ONNX) de otro `.chispa` (`--l2-de`, p. ej. exportado con `--perfil servidor`: fp32, sin poda).
"""
import argparse
import itertools
import json
import math
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from model.evaluacion import metricas as M
from model.evaluacion.jevbench import cargar_jevbench
from model.evaluacion.jevbench_cascada import cuerpo_decide
from model.l2 import calibrar as C
from model.l2 import exportar as E
from model.l2.modelo import SEP, Codificador, texto_consulta, texto_opcion

FACTORES = ("calib", "truncado", "texto_torre", "onnx")
MAX_LEN_DEFECTO = 128   # chispa3.MaxLenDefecto: el truncado de consulta si el ONNX de L2 no declara el suyo


# ------------------------------------------------------------------ CALIB
def calib_del_checkpoint(modelo, filas):
    """Sección CALIB `tipos` con las cabezas del checkpoint (T, a, b de `cabeza_inicial`), que es lo que usa `jevbench_l2`; θ = 0,5."""
    tipos = {}
    for clave in sorted({C.clave_cabeza(r) for r in filas}):
        modelo.asegurar_cabeza(clave)
        p = C.cabeza_inicial(modelo, clave)
        tipos[clave] = {**p, "T": p.get("T", 1.0), "theta": 0.5}
    return C.a_calib_chispa({"tipos": tipos, "tau_escalate": 0.0})["tipos"]


def reescribir(a):
    from chispa import formato
    secs = formato.leer(Path(a.entrada).read_bytes())
    if a.calib_ckpt:
        modelo, _ = C.cargar_modelo(a.ckpt, "cpu")
        filas = cargar_jevbench(a.jevbench)
        d = json.loads(secs[formato.CALIB])
        d["tipos"] = calib_del_checkpoint(modelo, filas)   # τ y demás campos del .chispa se conservan: solo cambian a, b, T y θ
        secs[formato.CALIB] = json.dumps(d).encode()
    if a.l2_de:
        secs[formato.L2] = formato.leer(Path(a.l2_de).read_bytes())[formato.L2]
    Path(a.salida).write_bytes(formato.escribir(secs))
    print("escrito %s (calib_ckpt=%s, l2_de=%s)" % (a.salida, bool(a.calib_ckpt), a.l2_de))
    return 0


# ------------------------------------------------------------------ lo que hace el servidor
def textos_servidor(fila):
    """Textos de torre que arma el servidor con la petición de `cuerpo_decide` (runtime/torre: Texto, OpcionesConsulta)."""
    q = cuerpo_decide(fila)["questions"][0]
    ops = [(o["id"], o.get("description", "")) for o in q.get("options", [])]
    texto = lambda i, d: "passage: " + q["question"] + SEP + i + SEP + d
    if q["kind"] == "choice":
        return [texto(i, d) for i, d in ops]
    if q["kind"] == "noul":
        return [texto("true", dict(ops).get("true", ""))]
    num = [(int(i), (i, d)) for i, d in ops if i.lstrip("-").isdigit()]
    return [texto(*max(num)[1])] if num else ([texto(*ops[-1])] if ops else [])


def textos_python(fila):
    return [texto_opcion(fila, o) for o in fila["opciones"]] if fila["tipo"] == "choice" else [texto_consulta(fila)]


def cuantizar_go(h):
    """`torre.Cuantizar`: int8 con escala max|h|/127 (1 si h es cero), redondeo de math.Round (mitades hacia fuera de 0)."""
    m = float(np.abs(h).max())
    esc = m / 127 if m > 0 else 1.0
    return np.clip(np.sign(h / esc) * np.floor(np.abs(h / esc) + 0.5), -127, 127), esc


def maxsim_np(S, hq, esc):
    d = (S @ hq.astype(np.float64)) * esc
    return float(np.max(np.logaddexp(0.0, d)))


def probs_calib(tipo, K, sims, tipos):
    """Probabilidades con la sección CALIB (como `decide.L2`): choice softmax(s/T), noul σ(a·s+b), scoreK CORAL con a, b y los incrementos `#j`."""
    if tipo == "choice":
        z = np.asarray(sims) / tipos["choice"]["T"]
        z = np.exp(z - z.max())
        return z / z.sum()
    if tipo == "noul":
        p = tipos["noul"]
        pt = 1 / (1 + math.exp(-(p["a"] * sims[0] + p["b"])))
        return np.array([1 - pt, pt])
    clave = "score%d" % K
    base, b, sup = tipos[clave], tipos[clave]["b"], []
    for j in range(K - 1):
        if j:
            b += tipos["%s#%d" % (clave, j)]["a"]
        sup.append(1 / (1 + math.exp(-(base["a"] * sims[0] - b))))
    sup = np.array(sup)
    return np.maximum(np.concatenate([[1], sup]) - np.concatenate([sup, [0]]), 0)


def elegida(fila, p):
    return int(M.etiqueta_coral(p)) if fila["tipo"] == "score" else int(np.argmax(p))


class Servidor:
    """El L2 del `.chispa` (consulta ONNX, TORR, CALIB) en Python, con el tokenizador de e5."""

    def __init__(self, ruta, tmp, tok):
        from chispa import formato
        import onnx
        secs = formato.leer(Path(ruta).read_bytes())
        (tmp / "l2.onnx").write_bytes(secs[formato.L2])
        self.torr = formato.leer_torr(secs[formato.TORR])
        (tmp / "torre.onnx").write_bytes(self.torr["onnx"])
        self.q, self.t, self.tok = E.sesion(tmp / "l2.onnx"), E.sesion(tmp / "torre.onnx"), tok
        self.calib = json.loads(secs[formato.CALIB])
        g = onnx.load(str(tmp / "l2.onnx"), load_external_data=False)
        props = {p.key: p.value for p in g.metadata_props}
        self.max_len_q = int(props.get("chispa.consulta.max_len", MAX_LEN_DEFECTO))
        emb = [i for i in g.graph.initializer if i.dims and max(i.dims) > 1000]
        self.info = {"consulta_max_len": self.max_len_q, "consulta_declara_max_len": "chispa.consulta.max_len" in props,
                     "torre_max_len": self.torr["max_len"], "consulta_filas_embeddings": min((i.dims[0] for i in emb), default=None),
                     "consulta_int8": any(n.op_type in ("MatMulInteger", "DynamicQuantizeLinear") for n in g.graph.node),
                     "calib_tipos": self.calib["tipos"], "calib_tau_escalate": self.calib.get("tau_escalate")}

    def ids_q(self, texto, max_len):
        return self.tok(["query: " + texto], truncation=True, max_length=max_len)["input_ids"][0]

    def S(self, texto, max_len):
        ids = np.array([self.ids_q(texto, max_len)])
        return E.correr(self.q, ids, np.ones_like(ids))[0].astype(np.float64)

    def h(self, textos):
        return E.correr_torre(self.t, ids_torre_con(self.tok, textos, self.torr["max_len"])).astype(np.float64)


def ids_torre_con(tok, textos, max_len):
    return tok(list(textos), truncation=True, max_length=max_len)["input_ids"]


@torch.no_grad()
def s_torch(modelo, enc, fila, textos):
    """s de PyTorch fp32 (consulta y torres), el camino de `ModeloL2.forward`."""
    H, m = enc.tokens([fila["texto"]])
    S = modelo.ranuras(H, m)
    h = modelo.torre(enc.pasaje(textos))
    return [float(x) for x in torch.nn.functional.softplus(torch.einsum("bkd,ud->bku", S, h)).max(dim=1).values[0]]


def s_servidor(srv, fila, textos, max_len):
    S, hs = srv.S(fila["texto"], max_len), srv.h(textos)
    return [maxsim_np(S, *cuantizar_go(h)) for h in hs]


def diagnosticar(a):
    from transformers import AutoTokenizer
    modelo, ck = C.cargar_modelo(a.ckpt, "cpu")
    max_tok = int((ck or {}).get("max_tok") or a.max_tok)
    enc = Codificador(device="cpu", max_tok=max_tok)
    filas = cargar_jevbench(a.jevbench)
    por_id = {r["id"]: r for r in filas}
    srv_p = {}
    for l in Path(a.capas).read_text().splitlines():
        if l.strip():
            q = json.loads(l)
            srv_p[q["id"]] = q
    py_p = {}
    if a.pred and Path(a.pred).exists():
        py_p = {q["id"]: q for q in map(json.loads, filter(str.strip, Path(a.pred).read_text().splitlines()))}
    # N casos por igual de cada tipo, los primeros de cada uno en orden de fichero y solo los que el servidor contestó
    casos = []
    for t in ("choice", "noul", "score"):
        casos += [r for r in filas if r["tipo"] == t and r["id"] in srv_p][:max(1, a.n // 3)] if a.n else [r for r in filas if r["tipo"] == t and r["id"] in srv_p]
    py_tipos = calib_del_checkpoint(modelo, casos)
    with tempfile.TemporaryDirectory() as t:
        tok = AutoTokenizer.from_pretrained(a.tokenizador or _ruta_e5())
        srv = Servidor(a.chispa, Path(t), tok)
        filas_out = []
        for r in casos:
            ops, K, tipo = r["opciones"], len(r["opciones"]), r["tipo"]
            ts_srv, ts_py = textos_servidor(r), textos_python(r)
            ids_py = tok(["query: " + r["texto"]], truncation=True, max_length=max_tok)["input_ids"][0]
            ids_srv = srv.ids_q(r["texto"], srv.max_len_q)
            n_sin_truncar = len(tok(["query: " + r["texto"]], truncation=True, max_length=512)["input_ids"][0])
            s_py = s_torch(modelo, enc, r, ts_py)
            cal = lambda f: py_tipos if f else srv.calib["tipos"]
            def probs(calib=False, truncado=False, texto=False, onnx=False):
                ts = ts_py if texto else ts_srv
                s = s_torch(modelo, enc, r, ts) if onnx else s_servidor(srv, r, ts, max_tok if truncado else srv.max_len_q)
                return probs_calib(tipo, K, s, cal(calib)), s
            p_replay, s_replay = probs()
            p_srv = [srv_p[r["id"]]["probs"].get(o, 0.0) for o in ops]
            tot = sum(p_srv)
            p_srv = np.array(p_srv) / tot if tot > 0 else None
            p_py = np.array([py_p[r["id"]]["probs"][o] for o in ops]) if r["id"] in py_p else probs_calib(tipo, K, s_py, py_tipos)
            fila = {"id": r["id"], "tipo": tipo, "etiqueta": r["etiqueta"], "capa": srv_p[r["id"]]["layer"],
                    "consulta": {"texto_igual": True, "tokens_python": len(ids_py), "tokens_servidor": len(ids_srv),
                                 "tokens_sin_truncar": n_sin_truncar, "truncado_python": n_sin_truncar > max_tok,
                                 "truncado_servidor": n_sin_truncar > srv.max_len_q},
                    "torre": [{"opcion": o, "igual": x == y, "servidor": x, "python": y} for o, x, y in zip(
                        (ops if tipo == "choice" else ["true" if tipo == "noul" else max(ops, key=int)]), ts_srv, ts_py)],
                    "s_python": s_py, "s_servidor_replay": s_replay,
                    "p_python": p_py.tolist(), "p_servidor": None if p_srv is None else p_srv.tolist(), "p_servidor_replay": p_replay.tolist()}
            if p_srv is None:
                fila["causa"] = "escalado"
            else:
                fila["elegida"] = {"python": elegida(r, p_py), "servidor": elegida(r, p_srv), "replay": elegida(r, p_replay)}
                fila["delta_p_max"] = float(np.abs(p_srv - p_py).max())
                fila["replay_fiel"] = float(np.abs(p_srv - p_replay).max())
                if fila["elegida"]["python"] == fila["elegida"]["servidor"]:
                    fila["causa"] = None
                elif fila["elegida"]["replay"] != fila["elegida"]["servidor"]:
                    fila["causa"] = "replay_infiel"   # el recálculo no reproduce al servidor: no se puede atribuir
                else:
                    sueltos = [f for f in FACTORES if elegida(r, probs(**{f if f != "texto_torre" else "texto": True})[0]) == fila["elegida"]["python"]]
                    if sueltos:
                        fila["causa"] = "+".join(sueltos)
                    else:
                        comb = next((c for n in (2, 3, 4) for c in itertools.combinations(FACTORES, n)
                                     if elegida(r, probs(**{(f if f != "texto_torre" else "texto"): True for f in c})[0]) == fila["elegida"]["python"]), None)
                        fila["causa"] = "combinada(%s)" % "+".join(comb) if comb else "otra"
            fila["calib_distinta"] = srv.calib["tipos"].get(C.clave_cabeza(r)) != py_tipos.get(C.clave_cabeza(r))
            filas_out.append(fila)
    out = {"n": len(filas_out), "max_tok_python": max_tok, "servidor": {k: v for k, v in srv.info.items() if k != "calib_tipos"},
           "calib_servidor": srv.info["calib_tipos"], "calib_python": py_tipos, "casos": filas_out, "resumen": resumen(filas_out)}
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    (sal / "paridad_servidor.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (sal / "paridad_servidor.md").write_text(informe(out), encoding="utf-8")
    print(informe(out))
    return 0


def _ruta_e5():
    import glob
    import os
    r = glob.glob(os.path.expanduser("~/hf/hub/models--intfloat--multilingual-e5-small/snapshots/*"))
    return r[0] if r else "intfloat/multilingual-e5-small"


def resumen(filas):
    res = {}
    for t in ("choice", "noul", "score", "todos"):
        fs = [f for f in filas if t == "todos" or f["tipo"] == t]
        con = [f for f in fs if "elegida" in f]
        dis = [f for f in con if f["causa"]]
        causas = {}
        for f in dis:
            causas[f["causa"]] = causas.get(f["causa"], 0) + 1
        res[t] = {"casos": len(fs), "escalados": len(fs) - len(con), "discrepan": len(dis), "causas": causas,
                  "tokens_truncados_python": sum(f["consulta"]["truncado_python"] for f in fs),
                  "tokens_truncados_servidor": sum(f["consulta"]["truncado_servidor"] for f in fs),
                  "texto_torre_distinto": sum(not all(x["igual"] for x in f["torre"]) for f in fs),
                  "replay_fiel_max": max((f["replay_fiel"] for f in con), default=None),
                  "delta_p_medio": float(np.mean([f["delta_p_max"] for f in con])) if con else None}
    return res


def informe(o):
    s = o["servidor"]
    L = ["# Paridad servidor ↔ Python (JevBench, %d casos)" % o["n"], "",
         "- Consulta del `.chispa`: max_len %s (%s en el ONNX; el checkpoint usa %d), %s filas de embeddings (completo = 250037), int8: %s." % (
             s["consulta_max_len"], "declarado" if s["consulta_declara_max_len"] else "NO declarado: defecto", o["max_tok_python"],
             s["consulta_filas_embeddings"], s["consulta_int8"]),
         "- TORR: max_len %s." % s["torre_max_len"], "", "CALIB (servidor frente a checkpoint):", "",
         "| cabeza | parámetros del `.chispa` | parámetros del checkpoint |", "|---|---|---|"]
    for k in sorted(set(o["calib_servidor"]) | set(o["calib_python"])):
        f = lambda d: ", ".join("%s=%.4g" % (x, y) for x, y in sorted((d or {}).items()) if x in ("T", "a", "b", "theta")) or "—"
        L.append("| %s | %s | %s |" % (k, f(o["calib_servidor"].get(k)), f(o["calib_python"].get(k))))
    L += ["", "| tipo | casos | discrepan | truncados Python / servidor | textos de torre distintos | ‖Δp‖ medio | replay fiel (máx |Δp|) | causas |",
          "|---|---|---|---|---|---|---|---|"]
    for t, r in o["resumen"].items():
        L.append("| %s | %d | %d | %d / %d | %d | %s | %s | %s |" % (
            t, r["casos"], r["discrepan"], r["tokens_truncados_python"], r["tokens_truncados_servidor"], r["texto_torre_distinto"],
            "—" if r["delta_p_medio"] is None else "%.3f" % r["delta_p_medio"], "—" if r["replay_fiel_max"] is None else "%.3f" % r["replay_fiel_max"],
            ", ".join("%s: %d" % kv for kv in sorted(r["causas"].items())) or "—"))
    L += ["", "«replay fiel» mide si el recálculo en Python reproduce lo que devolvió el servidor (debe ser ≈ 0: si no, la atribución no vale)."]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diagnosticar")
    for k in ("jevbench", "ckpt", "chispa", "capas", "salida"):
        d.add_argument("--" + k, required=True)
    d.add_argument("--pred")
    d.add_argument("--n", type=int, default=90, help="casos en total, repartidos por igual entre choice, noul y score (0 = todos)")
    d.add_argument("--max-tok", type=int, default=E.MAX_TOK)
    d.add_argument("--tokenizador", help="directorio del tokenizador de e5 (por defecto el de ~/hf)")
    r = sub.add_parser("reescribir")
    r.add_argument("--ckpt")
    r.add_argument("--jevbench")
    r.add_argument("--entrada", required=True)
    r.add_argument("--salida", required=True)
    r.add_argument("--calib-ckpt", action="store_true")
    r.add_argument("--l2-de")
    a = ap.parse_args(argv)
    if a.cmd == "reescribir":
        if a.calib_ckpt and not (a.ckpt and a.jevbench):
            ap.error("--calib-ckpt pide --ckpt y --jevbench")
        return reescribir(a)
    return diagnosticar(a)


if __name__ == "__main__":
    sys.exit(main())
