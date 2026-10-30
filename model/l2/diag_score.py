"""M5, diagnóstico de score: ¿por qué JevBench score da 0,333? Separa ranking, cabeza/calibración y datos.

    python -m model.l2.diag_score --ckpt mejor.pt --jevbench RUTA --salida DIR [--meta DIR_META] [--device cpu] [--max-tok N]

(a) ranking: s = MaxSim de la consulta de score (`modelo.texto_consulta`) contra el mensaje, antes de la cabeza. Spearman entre s y
    el nivel (por esquema y media; y global dentro de cada K) y exactitud de un ORÁCULO de umbrales: los umbrales monótonos que
    maximizan la exactitud sobre los propios casos, uno por esquema (en el propio test, por tanto una cota superior para cualquier
    regla de umbrales sobre s). Un oráculo «por caso» (un umbral distinto para cada caso) acierta siempre y no dice nada, por eso es por
    esquema; el de un solo juego de umbrales por K (global) va aparte.
(b) cabeza CORAL: exactitud con los umbrales del checkpoint (mediana CORAL, como el runtime) frente a umbrales reajustados en un dev
    (validación cruzada dejando un esquema fuera: se ajustan w y θ con los demás esquemas de su mismo K; sin ellos, o con < 20 casos,
    se conservan los del checkpoint). El dev son los propios casos score de JevBench de los otros esquemas.
(c) datos: ejemplos score del meta de G.8 por K y por tarea (solo `tsjev` tiene score: `model.datos` solo convierte choice/noul), antes y
    después del tope por tarea y de las tareas dejadas fuera (`model.meta.muestreo`), y su peso en el muestreo p ∝ n^α. Con `--meta`
    cuenta los ficheros reales; sin él, usa el censo por tipo de `model/meta/resultados/conversion-20261027.json`.

Salida: `DIR/diag_score.json` y `DIR/diag_score.md` con el veredicto y el arreglo más barato (coste estimado: g5.xlarge ≈ 1,0 USD/h,
c6a.2xlarge ≈ 0,31 USD/h bajo demanda).
"""
import argparse
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

from model.meta import muestreo

from .modelo import MAX_TOK, Coral

RAIZ = Path(__file__).resolve().parents[2]
CONVERSION = RAIZ / "model" / "meta" / "resultados" / "conversion-20261027.json"
MIN_FILAS = 20
USD_H = {"g5.xlarge": 1.0, "c6a.2xlarge": 0.31}


# ---------------------------------------------------------------- (a) ranking
def spearman(x, y):
    from scipy.stats import spearmanr
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < 3 or len(set(y.tolist())) < 2 or len(set(x.tolist())) < 2:
        return float("nan")
    return float(spearmanr(x, y).statistic)


def oraculo(s, y, k):
    """Mejor exactitud de una regla monótona «nivel = nº de umbrales ≤ s» sobre (s, y): DP sobre los valores distintos de s.
    Devuelve (aciertos, umbrales k−1 en el punto medio de cada salto)."""
    s, y = np.asarray(s, float), np.asarray(y, int)
    vals = np.unique(s)
    cuenta = np.zeros((len(vals), k), int)
    for v, c in zip(np.searchsorted(vals, s), y):
        cuenta[v, c] += 1
    mejor = np.full(k, 0)                      # mejor[l]: aciertos con el último grupo en el nivel l
    previo = np.zeros((len(vals), k), int)     # nivel anterior de cada grupo (para reconstruir)
    for g in range(len(vals)):
        acum = np.maximum.accumulate(mejor)
        arg = np.zeros(k, int)
        for l in range(k):
            arg[l] = int(np.argmax(mejor[:l + 1]))
        previo[g] = arg
        mejor = acum + cuenta[g]
    l = int(np.argmax(mejor))
    niveles = [0] * len(vals)
    for g in range(len(vals) - 1, -1, -1):
        niveles[g] = l
        l = previo[g][l]
    th = []
    for j in range(1, k):
        idx = [g for g in range(len(vals)) if niveles[g] >= j]
        th.append(float((vals[idx[0]] + vals[idx[0] - 1]) / 2) if idx and idx[0] > 0 else (float(vals[0]) - 1.0 if idx else float(vals[-1]) + 1.0))
    return int(mejor.max()), th


# ---------------------------------------------------------------- (b) cabeza CORAL
def coral_params(modelo, k):
    c = modelo.coral["score%d" % k]
    return {"w": float(c.w.detach()), "theta": [float(t) for t in c.umbrales().detach()]}


def etiqueta(s, p):
    """Mediana CORAL con parámetros p = {w, theta}: nº de umbrales con σ(w·s − θ_j) > 0,5."""
    s = torch.as_tensor(np.asarray(s, float)).float().unsqueeze(-1)
    return Coral.etiqueta(torch.sigmoid(p["w"] * s - torch.tensor(p["theta"]).float())).numpy()


def ajustar_coral(s, y, k, inicial, reg=1e-3):
    """w y θ (ordenados) por máxima verosimilitud sobre (s, y), con una regularización débil hacia `inicial`."""
    s = torch.as_tensor(np.asarray(s, float)).float()
    y = torch.as_tensor(np.asarray(y, int))
    w0 = torch.tensor(inicial["w"]).float()
    th0 = torch.tensor(inicial["theta"]).float()
    d0 = torch.log(torch.expm1((th0[1:] - th0[:-1]).clamp(min=1e-3)))
    w = w0.clone().requires_grad_(True)
    t1 = th0[:1].clone().requires_grad_(True)
    d = d0.clone().requires_grad_(True)
    opt = torch.optim.LBFGS([w, t1, d], lr=0.5, max_iter=200, line_search_fn="strong_wolfe")

    def umbrales():
        return torch.cat([t1, t1 + torch.cumsum(torch.nn.functional.softplus(d), 0)]) if len(d) else t1

    def cierre():
        opt.zero_grad()
        sup = torch.sigmoid(w * s[:, None] - umbrales())
        uno = torch.ones(len(s), 1)
        p = (torch.cat([uno, sup], 1) - torch.cat([sup, 0 * uno], 1)).clamp(min=1e-7)
        nll = -torch.log(p[torch.arange(len(s)), y]).mean()
        l = nll + reg * (((w - w0) ** 2) + ((umbrales() - th0) ** 2).sum())
        l.backward()
        return l
    opt.step(cierre)
    return {"w": float(w.detach()), "theta": [float(t) for t in umbrales().detach()]}


def evaluar_cabeza(casos, modelo, min_filas=MIN_FILAS):
    """casos: [{esquema, k, s, y}]. → exactitud con el checkpoint, con reajuste dejando un esquema fuera, y el oráculo por esquema."""
    por = defaultdict(list)
    for c in casos:
        por[c["esquema"]].append(c)
    det, tot = {}, Counter()
    for esq, cs in sorted(por.items()):
        k = cs[0]["k"]
        s, y = [c["s"] for c in cs], np.array([c["y"] for c in cs])
        ck = coral_params(modelo, k)
        otros = [c for e, v in por.items() if e != esq and v[0]["k"] == k for c in v]
        ajustado = len(otros) >= min_filas and len({c["y"] for c in otros}) >= 2
        p = ajustar_coral([c["s"] for c in otros], [c["y"] for c in otros], k, ck) if ajustado else ck
        ac, ao = int((etiqueta(s, ck) == y).sum()), int((etiqueta(s, p) == y).sum())
        orc, th = oraculo(s, y, k)
        mae = lambda pr: float(np.abs(pr - y).mean())
        det[esq] = {"k": k, "n": len(cs), "ckpt": ac / len(cs), "loso": ao / len(cs), "reajustado": ajustado, "oraculo": orc / len(cs),
                    "mayoria": float(np.bincount(y, minlength=k).max() / len(cs)), "mae_ckpt": mae(etiqueta(s, ck)), "mae_loso": mae(etiqueta(s, p)),
                    "spearman": spearman(s, y), "umbrales_oraculo": th}
        tot.update(n=len(cs), ckpt=ac, loso=ao, oraculo=orc, mayoria=int(np.bincount(y, minlength=k).max()))
    n = max(tot["n"], 1)
    glob = {x: tot[x] / n for x in ("ckpt", "loso", "oraculo", "mayoria")}
    glob["n"] = tot["n"]
    rhos = [d["spearman"] for d in det.values() if not math.isnan(d["spearman"])]
    glob["spearman_media_esquemas"] = float(np.mean(rhos)) if rhos else float("nan")
    por_k = {}
    for k in sorted({c["k"] for c in casos}):
        cs = [c for c in casos if c["k"] == k]
        por_k[k] = {"n": len(cs), "spearman": spearman([c["s"] for c in cs], [c["y"] for c in cs]),
                    "oraculo_un_juego": oraculo([c["s"] for c in cs], np.array([c["y"] for c in cs]), k)[0] / len(cs)}
    return {"global": glob, "por_esquema": det, "por_k": por_k}


# ---------------------------------------------------------------- (c) datos
def _filas_meta(meta):
    for f in sorted(Path(meta).rglob("*.jsonl*")):
        if "tsjev" not in f.parts:
            continue
        ab = gzip.open if f.suffix == ".gz" else open
        with ab(f, "rt", encoding="utf-8") as fh:
            for l in fh:
                if l.strip():
                    r = json.loads(l)
                    if r.get("split") == "train":
                        yield r


def censo_meta(meta, tope=muestreo.TOPE_TAREA, alfa=muestreo.ALFA_TAREA):
    """Score del meta (split train de tsjev): por K y por tarea, bruto, sin las tareas fuera y con el tope por tarea; y el peso de
    score en el muestreo de tsjev p(tarea) ∝ n^α (sobre lo conservado, todos los tipos)."""
    n_t, tipo_t, k_t = Counter(), {}, {}
    for r in _filas_meta(meta):
        n_t[r["tarea"]] += 1
        tipo_t[r["tarea"]] = r["tipo"]
        if r["tipo"] == "score":
            k_t[r["tarea"]] = len(r["opciones"])
    dentro = {t: n for t, n in n_t.items() if not muestreo.tarea_fuera(t)}
    cap = muestreo.cupos(dentro, tope)
    peso = {t: n ** alfa for t, n in cap.items()}
    ps = sum(w for t, w in peso.items() if tipo_t[t] == "score")
    por_k = defaultdict(lambda: {"tareas": 0, "bruto": 0, "sin_fuera": 0, "con_tope": 0})
    for t, k in k_t.items():
        d = por_k["K=%d" % k]
        d["tareas"] += 1
        d["bruto"] += n_t[t]
        d["sin_fuera"] += dentro.get(t, 0)
        d["con_tope"] += cap.get(t, 0)
    tareas = sorted(((n_t[t], t, k) for t, k in k_t.items()), reverse=True)
    return {"origen": "ficheros del meta", "por_k": dict(sorted(por_k.items())), "tareas_score": len(k_t),
            "tareas_score_dentro": sum(1 for t in k_t if t in dentro), "filas_score_con_tope": sum(cap.get(t, 0) for t in k_t),
            "filas_tsjev_con_tope": sum(cap.values()), "peso_score_en_muestreo_tsjev": ps / max(sum(peso.values()), 1e-9),
            "mayores": [{"tarea": t, "k": k, "n": n} for n, t, k in tareas[:8]]}


def censo_conversion(ruta=CONVERSION):
    d = json.loads(Path(ruta).read_text())
    tipos = d["filas_por_tipo"]
    return {"origen": "conversion-20261027.json (sin ficheros: no hay desglose por K ni por tarea)", "filas_por_tipo": tipos,
            "score_por_split": d["filas_por_fuente_tipo_split"]["tsjev"]["score"], "fuentes_con_score": ["tsjev"],
            "fraccion_score_del_meta": tipos["score"] / sum(tipos.values()),
            "fraccion_score_de_tsjev": tipos["score"] / d["filas_por_fuente"]["tsjev"]}


# ---------------------------------------------------------------- veredicto y arreglo
def veredicto(b, datos=None):
    """(causas, arreglo): lectura automática de las cifras, con el coste del arreglo más barato que las ataca."""
    g = b["global"]
    ok = lambda x: x == x
    rho, orc, ck, lo = g["spearman_media_esquemas"], g["oraculo"], g["ckpt"], g["loso"]
    causas = []
    if ok(rho) and (rho < 0.3 or orc < g["mayoria"] + 0.10):
        causas.append("ranking: s apenas ordena los niveles (ρ medio %.2f; el oráculo de umbrales llega a %.3f frente a %.3f de la clase mayoritaria)"
                      % (rho, orc, g["mayoria"]))
    if orc - ck >= 0.10:
        recup = (lo - ck) / (orc - ck)
        causas.append("calibración: los umbrales del checkpoint dejan %.3f sobre la mesa frente al oráculo; reajustar en un dev (esquema fuera) "
                      "recupera el %.0f %% de esa brecha (%.3f → %.3f)" % (orc - ck, 100 * recup, ck, lo))
    if not causas:
        causas.append("ni el ranking ni los umbrales explican la caída: ck %.3f, reajuste %.3f, oráculo %.3f" % (ck, lo, orc))
    cal = {"que": "reajustar w y θ de las cabezas score en un dev con etiquetas del dominio (calibrar.py ya lo hace por K)",
           "donde": "CPU (c6a.2xlarge)", "horas": 0.25, "usd": round(0.25 * USD_H["c6a.2xlarge"], 2)}
    rank = {"que": "continuar el entrenamiento solo con episodios score (muestreo por tipo), reanudando de mejor.pt; las cabezas y las ranuras "
                   "aprenden el orden, la torre se queda como está", "donde": "GPU (g5.xlarge)", "horas": 1.5,
            "usd": round(1.5 * USD_H["g5.xlarge"] + 0.1, 2)}
    if any(c.startswith("ranking") for c in causas):
        arreglo = rank
    elif any(c.startswith("calibración") for c in causas) and (lo - ck) >= 0.5 * (orc - ck):
        arreglo = cal
    else:
        arreglo = cal if any(c.startswith("calibración") for c in causas) else rank
    return causas, arreglo, {"calibracion": cal, "ranking": rank}


def informe_md(b, datos, causas, arreglo, max_tok):
    g, f = b["global"], lambda x: "%.3f" % x
    lin = ["# M5 diagnóstico de score (max_tok %d)" % max_tok, "",
           "%d casos score de JevBench, %d esquemas." % (g["n"], len(b["por_esquema"])), "",
           "## (a) ranking y (b) cabeza", "",
           "| | exactitud |", "|---|---|",
           "| clase mayoritaria | %s |" % f(g["mayoria"]), "| umbrales del checkpoint | %s |" % f(g["ckpt"]),
           "| umbrales reajustados (esquema fuera) | %s |" % f(g["loso"]), "| oráculo de umbrales por esquema | %s |" % f(g["oraculo"]), "",
           "Spearman s↔nivel: media por esquema %s" % f(g["spearman_media_esquemas"]) + "; global por K: "
           + ", ".join("K=%d %s (oráculo con un solo juego %s, n=%d)" % (k, f(v["spearman"]), f(v["oraculo_un_juego"]), v["n"]) for k, v in b["por_k"].items()),
           "", "| esquema | K | n | ckpt | reajuste | oráculo | mayoría | ρ | MAE ckpt | MAE reajuste |", "|" + "---|" * 10]
    for e, d in b["por_esquema"].items():
        lin.append("| %s | %d | %d | %s | %s%s | %s | %s | %s | %.2f | %.2f |" % (
            e, d["k"], d["n"], f(d["ckpt"]), f(d["loso"]), "" if d["reajustado"] else " (sin dev)", f(d["oraculo"]), f(d["mayoria"]),
            "%.2f" % d["spearman"], d["mae_ckpt"], d["mae_loso"]))
    lin += ["", "## (c) datos de entrenamiento", "", "```", json.dumps(datos, indent=1, ensure_ascii=False), "```", "",
            "## Causas y arreglo más barato", ""] + ["- " + c for c in causas]
    lin += ["", "**Arreglo:** %s. %s, ≈ %.2f h, ≈ %.2f USD." % (arreglo["que"], arreglo["donde"], arreglo["horas"], arreglo["usd"])]
    return "\n".join(lin) + "\n"


def casos_score(modelo, enc, filas, lote=64):
    from .calibrar import simil
    filas = [r for r in filas if r["tipo"] == "score"]
    for r in filas:
        modelo.asegurar_cabeza("score%d" % len(r["opciones"]), modelo.ranuras.q.device)
    ss = simil(modelo, enc, filas, lote)
    return [{"id": r["id"], "esquema": r["esquema"], "k": len(r["opciones"]), "s": float(s[0]), "y": r["opciones"].index(r["etiqueta"])}
            for r, s in zip(filas, ss)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--jevbench", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--meta", help="directorio del meta (con tsjev/); sin él, el censo de conversion-20261027.json")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--max-tok", type=int, default=0)
    a = ap.parse_args(argv)
    from model.evaluacion.jevbench import cargar_jevbench
    from .evaluar import cargar_modelo
    from .modelo import Codificador
    modelo, ck = cargar_modelo(a.ckpt, a.device)
    max_tok = a.max_tok or ck.get("max_tok", MAX_TOK)
    enc = Codificador(device=a.device, max_tok=max_tok)
    enc.cargar_enc(ck.get("enc"))
    casos = casos_score(modelo, enc, cargar_jevbench(a.jevbench))
    if not casos:
        print("sin casos score en JevBench", file=sys.stderr)
        return 1
    b = evaluar_cabeza(casos, modelo)
    datos = censo_meta(a.meta) if a.meta else censo_conversion()
    causas, arreglo, opciones = veredicto(b, datos)
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    (sal / "diag_score.json").write_text(json.dumps({"max_tok": max_tok, "casos": b, "datos": datos, "causas": causas, "arreglo": arreglo,
                                                      "opciones": opciones}, indent=1, ensure_ascii=False))
    md = informe_md(b, datos, causas, arreglo, max_tok)
    (sal / "diag_score.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
