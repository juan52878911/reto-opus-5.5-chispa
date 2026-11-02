"""W4 (a): ¿s ordena los niveles de score en el sentido que supone la cabeza CORAL (P(y>j) = σ(w·s − θ_j))?

    python -m model.l2.orientacion_score --ckpt mejor.pt --jevbench RUTA --salida DIR [--meta DIR_META] [--device cpu] [--max-tok N]

Para cada esquema score calcula, con s = MaxSim(ranuras del mensaje, torre de la consulta):
  máx   la torre del nivel MÁXIMO (la de entrenamiento y evaluación: `modelo.texto_consulta`, R9b/R16)
  mín   la torre del nivel MÍNIMO
  −s    la s de la torre máxima, invertida
el ρ de Spearman con el nivel de oro y la exactitud de la mediana CORAL (parámetros w, θ del checkpoint, sin reajustar).
Conjuntos: todos los casos score de JevBench y el dev de score del meta de G.8 (filas score con `split == "dev"` de
`<meta>/<fuente>/*.jsonl[.gz]`, hasta `--max-meta` por K, 3000 por defecto; esquema = tarea).

Comprueba además la conversión de JevBench (`comprobar_conversion`: etiqueta = oro + 1, descripción del nivel i+1 = criteria[i],
sin niveles repetidos) y escribe un veredicto: fallo de conversión de JevBench · fallo de orientación en el modelo · el modelo ordena
bien en el meta y no generaliza a JevBench.

Salida: `DIR/orientacion_score.json` y `DIR/orientacion_score.md`.
"""
import argparse
import gzip
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

from .diag_score import coral_params, etiqueta, spearman
from .modelo import MAX_TOK, indice_etiqueta, maxsim, niveles_score, texto_opcion

MIN_FILAS = 20          # filas mínimas de un esquema para contar su ρ en la media
UMBRAL_BIEN = 0.3       # ρ medio a partir del cual «ordena bien»
VARIANTES = ("max", "min", "invertida")


# ---------------------------------------------------------------- conversión de JevBench
def comprobar_conversion(filas):
    """Errores de la conversión de JevBench en TODAS las filas score: [] si es correcta. `criteria` va de menos a más gravedad y
    `expected` es el índice del nivel: opciones «1»..«K», etiqueta = expected + 1 y descripción del nivel i+1 = criteria[i]."""
    errores = []
    for r in filas:
        if r["tipo"] != "score":
            continue
        try:
            niv = niveles_score(r["opciones"])
        except ValueError as e:
            errores.append("%s: %s" % (r["id"], e))
            continue
        k = len(niv)
        if r["etiqueta"] != str(r["oro_jev"] + 1):
            errores.append("%s: etiqueta %s con expected %s" % (r["id"], r["etiqueta"], r["oro_jev"]))
        if not 0 <= r["oro_jev"] < k:
            errores.append("%s: expected %s fuera de 0..%d" % (r["id"], r["oro_jev"], k - 1))
        descs = [r["descripciones"].get(o, "") for o in niv]
        if any(not d for d in descs) or len(set(descs)) != k:
            errores.append("%s: descripciones de nivel vacías o repetidas" % r["id"])
    return errores


# ---------------------------------------------------------------- meta
def filas_dev_meta(meta, max_por_k=3000, semilla=0):
    """Filas score con split dev de `<meta>/<fuente>/*.jsonl[.gz]`, como mucho `max_por_k` por K (muestreo de reservorio, determinista)."""
    rng = random.Random(semilla)
    res, vistas = defaultdict(list), defaultdict(int)
    for f in sorted(Path(meta).rglob("*.jsonl*")):
        ab = gzip.open if f.suffix == ".gz" else open
        with ab(f, "rt", encoding="utf-8") as fh:
            for l in fh:
                if '"score"' not in l or not l.strip():
                    continue
                r = json.loads(l)
                if r.get("tipo") != "score" or r.get("split") != "dev" or "texto" not in r:
                    continue
                try:
                    niveles_score(r["opciones"])
                    indice_etiqueta(r)
                except (ValueError, KeyError):
                    continue
                r.setdefault("pregunta", "")
                r.setdefault("descripciones", {})
                r["esquema"] = r["tarea"]
                k = len(r["opciones"])
                vistas[k] += 1
                if len(res[k]) < max_por_k:
                    res[k].append(r)
                else:
                    j = rng.randrange(vistas[k])
                    if j < max_por_k:
                        res[k][j] = r
    return [r for k in sorted(res) for r in res[k]]


# ---------------------------------------------------------------- s con cada torre
def similitudes(modelo, enc, filas, lote=64):
    """[(s_max, s_min)] por fila: la misma s (ranuras del mensaje contra torre) con la torre del nivel máximo y la del mínimo."""
    dev = modelo.ranuras.q.device
    out = []
    for i in range(0, len(filas), lote):
        fs = filas[i:i + lote]
        with torch.no_grad():
            H, m = enc.tokens([r["texto"] for r in fs])
            S = modelo.ranuras(H.to(dev), m.to(dev))
            textos, pos, ix = [], {}, []
            for r in fs:
                niv = niveles_score(r["opciones"])
                par = []
                for o in (niv[-1], niv[0]):
                    t = texto_opcion(r, o, modelo.texto_torre)
                    if t not in pos:
                        pos[t] = len(textos)
                        textos.append(t)
                    par.append(pos[t])
                ix.append(par)
            sim = maxsim(S, modelo.torre(enc.pasaje(textos).to(dev))).cpu()
        out += [(float(sim[j, a]), float(sim[j, b])) for j, (a, b) in enumerate(ix)]
    return out


def medir(casos, params_por_k):
    """casos: [{esquema, k, s_max, s_min, y}] → {global, por_esquema}: ρ y exactitud de CORAL por variante (máx, mín, invertida)."""
    def fila_de(cs):
        k, y = cs[0]["k"], np.array([c["y"] for c in cs])
        smax, smin = np.array([c["s_max"] for c in cs]), np.array([c["s_min"] for c in cs])
        p = params_por_k[k]
        d = {"k": k, "n": len(cs), "mayoria": float(np.bincount(y, minlength=k).max() / len(cs)), "w": p["w"]}
        for nombre, s in (("max", smax), ("min", smin), ("invertida", -smax)):
            d["rho_" + nombre] = spearman(s, y)
            d["exactitud_" + nombre] = float((etiqueta(s, p) == y).mean())
        return d
    por = defaultdict(list)
    for c in casos:
        por[c["esquema"]].append(c)
    det = {e: fila_de(cs) for e, cs in sorted(por.items())}
    glob = {"n": len(casos), "esquemas": len(det)}
    validos = [d for d in det.values() if d["n"] >= MIN_FILAS] or list(det.values())
    for v in VARIANTES:
        rhos = [d["rho_" + v] for d in validos if not math.isnan(d["rho_" + v])]
        glob["rho_" + v] = float(np.mean(rhos)) if rhos else float("nan")
        glob["exactitud_" + v] = float(sum(d["exactitud_" + v] * d["n"] for d in det.values()) / max(len(casos), 1))
    glob["mayoria"] = float(sum(d["mayoria"] * d["n"] for d in det.values()) / max(len(casos), 1))
    return {"global": glob, "por_esquema": det}


# ---------------------------------------------------------------- veredicto
def veredicto(jev, meta, errores_conversion):
    """(conclusión, razón). Una de: fallo de conversión de JevBench · fallo de orientación en el modelo ·
    el modelo ordena bien en el meta y no generaliza a JevBench (· sin fallo: s ordena bien en los dos)."""
    rj = jev["global"]["rho_max"]
    rm = meta["global"]["rho_max"] if meta else None
    if errores_conversion:
        return "fallo de conversión de JevBench", "%d errores en la conversión, p. ej. %s" % (len(errores_conversion), errores_conversion[0])
    if rm is not None and rm == rm:
        if rm < 0.1:
            mejor = max(("min", "invertida"), key=lambda v: meta["global"]["rho_" + v] if meta["global"]["rho_" + v] == meta["global"]["rho_" + v] else -9)
            return "fallo de orientación en el modelo", ("en el propio dev del meta ρ(s máx) = %.2f (≥ %.1f haría falta); con la variante «%s» "
                                                         "sale %.2f" % (rm, UMBRAL_BIEN, mejor, meta["global"]["rho_" + mejor]))
        if rj == rj and rj < 0.1:
            return "el modelo ordena bien en el meta y no generaliza a JevBench", \
                "ρ meta = %.2f frente a ρ JevBench = %.2f, con la conversión de JevBench correcta" % (rm, rj)
        return "sin fallo: s ordena bien en el meta y en JevBench", "ρ meta = %.2f, ρ JevBench = %.2f" % (rm, rj)
    if rj == rj and rj < 0.1:
        return "fallo de orientación en el modelo", "sin meta; ρ(s máx) en JevBench = %.2f y la conversión es correcta (no concluyente sin meta)" % rj
    return "sin fallo: s ordena bien en JevBench", "sin meta; ρ JevBench = %.2f" % rj


def informe_md(res):
    f = lambda x: "—" if x != x else "%.3f" % x
    lin = ["# W4 (a) orientación de score (max_tok %d)" % res["max_tok"], "",
           "## Veredicto: %s" % res["veredicto"], "", res["razon"], "",
           "Conversión de JevBench: %s" % ("correcta en los %d casos score" % res["jevbench"]["global"]["n"] if not res["errores_conversion"]
                                           else "%d errores" % len(res["errores_conversion"])), ""]
    for nombre in ("jevbench", "meta"):
        d = res.get(nombre)
        if not d:
            lin += ["## %s" % nombre, "", "(sin datos)", ""]
            continue
        g = d["global"]
        lin += ["## %s (n = %d, %d esquemas)" % (nombre, g["n"], g["esquemas"]), "", "| torre | ρ medio por esquema | exactitud CORAL |", "|---|---|---|",
                "| nivel máximo (actual) | %s | %s |" % (f(g["rho_max"]), f(g["exactitud_max"])),
                "| nivel mínimo | %s | %s |" % (f(g["rho_min"]), f(g["exactitud_min"])),
                "| s invertida (−s) | %s | %s |" % (f(g["rho_invertida"]), f(g["exactitud_invertida"])),
                "| clase mayoritaria | | %s |" % f(g["mayoria"]), "",
                "| esquema | K | n | w | ρ máx | ρ mín | ρ −s | ex. máx | ex. mín | ex. −s |", "|" + "---|" * 10]
        for e, x in list(d["por_esquema"].items())[:40]:
            lin.append("| %s | %d | %d | %.2f | %s | %s | %s | %s | %s | %s |" % (
                e, x["k"], x["n"], x["w"], f(x["rho_max"]), f(x["rho_min"]), f(x["rho_invertida"]),
                f(x["exactitud_max"]), f(x["exactitud_min"]), f(x["exactitud_invertida"])))
        lin.append("")
    return "\n".join(lin) + "\n"


def casos_de(modelo, enc, filas, lote=64):
    filas = [r for r in filas if r["tipo"] == "score"]
    for r in filas:
        modelo.asegurar_cabeza("score%d" % len(r["opciones"]), modelo.ranuras.q.device)
    return [{"esquema": r["esquema"], "k": len(r["opciones"]), "s_max": a, "s_min": b, "y": indice_etiqueta(r)}
            for r, (a, b) in zip(filas, similitudes(modelo, enc, filas, lote))]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--jevbench", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--meta", help="directorio del meta (<fuente>/*.jsonl.gz); sin él solo se mide JevBench")
    ap.add_argument("--max-meta", type=int, default=3000, help="filas del dev del meta por K")
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
    filas_jev = cargar_jevbench(a.jevbench)
    errores = comprobar_conversion(filas_jev)
    cj = casos_de(modelo, enc, filas_jev)
    if not cj:
        print("sin casos score en JevBench", file=sys.stderr)
        return 1
    params = {k: coral_params(modelo, k) for k in {c["k"] for c in cj}}
    cm = []
    if a.meta:
        fm = filas_dev_meta(a.meta, a.max_meta)
        cm = casos_de(modelo, enc, fm)
        for k in {c["k"] for c in cm} - set(params):
            params[k] = coral_params(modelo, k)
    jev = medir(cj, params)
    meta = medir(cm, params) if cm else None
    concl, razon = veredicto(jev, meta, errores)
    res = {"max_tok": max_tok, "veredicto": concl, "razon": razon, "errores_conversion": errores[:20], "jevbench": jev, "meta": meta}
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    (sal / "orientacion_score.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    md = informe_md(res)
    (sal / "orientacion_score.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
