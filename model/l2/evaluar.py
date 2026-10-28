"""Predicción y evaluación de L2 con `chispa eval`.

    python -m model.l2.evaluar --ckpt mejor.pt --salida DIR [--datos DIR_CONVERTIDOS] [--liston DIR] [--extra nombre=ruta.jsonl] [--renombrar] [--soporte K]

Escribe `DIR/pred/<conjunto>.jsonl` (`{id, probs, ms}`), `DIR/resultados.json` y `DIR/delta.md` (Δ de macro-F1 por tarea frente
al kNN-32 y L0 de `model/lineas_base/resultados.json`). `ms` es el tiempo del lote repartido entre sus filas (no latencia
de una consulta suelta).

`--soporte K` (T2.1b): además de sin soporte, evalúa con K ejemplos por clase de soporte (los mismos que kNN-32 en T1.7a si K = 32,
semilla 0) en `DIR/pred_soporte/` y `DIR/resultados_soporte.json`; `delta.md` lleva las dos columnas. Los prototipos se calculan una
sola vez por tarea. Los conjuntos sin train (listón) se evalúan igual en las dos columnas.

`--renombrar`: además evalúa el mismo test con los ids de las opciones sustituidos por A, B, C… (solo filas `choice`), escribe
`DIR/pred_renombrado/`, `DIR/resultados_renombrado.json` y `DIR/caida.md` con la caída de macro-F1 por tarea (original − renombrado).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import torch

from model.evaluacion import chispa_eval as CE

from . import datos as D
from .modelo import Codificador, ModeloL2, SoporteEval

RAIZ = Path(__file__).resolve().parents[2]
LB = RAIZ / "model" / "lineas_base" / "resultados.json"
TEST_T17A = ("massive", "hatecheck", "clinc150", "inyecciones")


@torch.no_grad()
def predecir(modelo, enc, filas, lote=64, soporte=None):
    """`soporte`: `modelo.SoporteEval` (prototipos por tarea, calculados una vez); sin él, modo sin soporte."""
    modelo.eval()
    out = []
    for i in range(0, len(filas), lote):
        fs = filas[i:i + lote]
        protos = soporte.protos(modelo, enc, {r["tarea"] for r in fs}) if soporte else None
        t0 = time.perf_counter()
        probs, _ = modelo(fs, enc, entrenar=False, protos=protos)
        ms = (time.perf_counter() - t0) * 1000 / len(fs)
        for r, p in zip(fs, probs):
            p = p.double().cpu()
            p = (p / p.sum()).tolist()
            out.append({"id": r["id"], "probs": dict(zip(r["opciones"], p)), "ms": round(ms, 3)})
    return out


def macro_f1_medio(filas, preds):
    por = CE.evaluar(filas, preds)["por_tarea"]
    return sum(m["macro_f1"] for m in por.values()) / max(len(por), 1), por


def cargar_modelo(ruta, device="cpu"):
    ck = torch.load(ruta, map_location=device, weights_only=False)
    m = ModeloL2().to(device)
    for k in ck.get("cabezas", []):
        m.asegurar_cabeza(k, device)
    m.load_state_dict(ck["modelo"])
    return m.eval(), ck


def tabla_caida(res, res_r, tope=0.05):
    """(markdown, peor caída por tarea, peor caída global) de macro-F1: original − renombrado."""
    lin = ["| conjunto | tarea | n | macro-F1 | renombrado | caída |", "|" + "---|" * 6]
    peor = peor_g = float("-inf")
    for nombre in res:
        filas = [(t, m, res_r[nombre]["por_tarea"][t]) for t, m in res[nombre]["por_tarea"].items()]
        filas.append(("GLOBAL", res[nombre]["global"], res_r[nombre]["global"]))
        for t, m, mr in filas:
            c = m["macro_f1"] - mr["macro_f1"]
            if t == "GLOBAL":
                peor_g = max(peor_g, c)
            else:
                peor = max(peor, c)
            lin.append("| %s | %s | %d | %.3f | %.3f | %+.3f |" % (nombre, t, m["n"], m["macro_f1"], mr["macro_f1"], c))
    lin += ["", "Peor caída por tarea: %+.3f; peor caída global: %+.3f (criterio T2.2: ≤ %.2f)." % (peor, peor_g, tope)]
    return "\n".join(lin), peor, peor_g


def conjuntos_test(datos=None, liston=None, extra=()):
    """{nombre: filas test}: T1.7a (datos convertidos), T1.4 (herramientas) y el listón."""
    out = {}
    for t in TEST_T17A:
        if datos and (Path(datos) / (t + ".jsonl")).exists():
            out[t] = D.leer(str(Path(datos) / (t + ".jsonl")), split="test")
    h = RAIZ / "model" / "herramientas" / "test.jsonl"
    if h.exists():
        out["herramientas"] = D.leer(str(h), split="test")
    if liston:
        for f in sorted(Path(liston).glob("*.jsonl")):
            out["liston_" + f.stem] = D.leer(str(f), split="test")
    for e in extra:
        n, _, r = e.partition("=")
        out[n] = D.leer(r, split="test")
    return {k: v for k, v in out.items() if v}


def train_por_tarea(datos=None):
    """{tarea: filas train} de los conjuntos de T1.7a y de herramientas (T1.4): el soporte sale de aquí."""
    out = {}
    fuentes = [str(Path(datos) / (t + ".jsonl")) for t in TEST_T17A if datos and (Path(datos) / (t + ".jsonl")).exists()]
    h = RAIZ / "model" / "herramientas" / "train.jsonl"
    if h.exists():
        fuentes.append(str(h))
    for f in fuentes:
        for r in D.leer(f, split="train"):
            out.setdefault(r["tarea"], []).append(r)
    return out


def tabla_delta(res, res_s=None):
    with open(LB) as f:
        base = json.load(f)
    cab = "| conjunto | n | L2 macro-F1 | e5 kNN-32 | Δ vs kNN-32 | L0 | Δ vs L0 | L2 ECE | kNN-32 ECE |"
    if res_s:
        cab += " L2+soporte macro-F1 | Δ vs kNN-32 (soporte) | L2+soporte ECE |"
    lin = [cab, "|" + "---|" * (12 if res_s else 9)]
    ganadas = ganadas_s = 0
    for nombre, r in res.items():
        g = r["global"]
        b = base.get(nombre, {})
        k, l0 = (b.get("e5_knn32") or {}).get("global", b.get("e5_knn32")), (b.get("l0_tfidf_lr") or {}).get("global", b.get("l0_tfidf_lr"))
        f = lambda x, c: x[c] if isinstance(x, dict) and x.get(c) is not None else None
        mk, ml = f(k, "macro_f1"), f(l0, "macro_f1")
        d = lambda a, c: "-" if c is None else "%+.3f" % (a - c)
        v = lambda x: "-" if x is None else "%.3f" % x
        ganadas += mk is not None and g["macro_f1"] - mk >= 0.05
        fila = "| %s | %d | %.3f | %s | %s | %s | %s | %.3f | %s |" % (
            nombre, g["n"], g["macro_f1"], v(mk), d(g["macro_f1"], mk), v(ml), d(g["macro_f1"], ml), g["ece"], v(f(k, "ece")))
        if res_s:
            gs = res_s[nombre]["global"]
            ganadas_s += mk is not None and gs["macro_f1"] - mk >= 0.05
            fila += " %.3f | %s | %.3f |" % (gs["macro_f1"], d(gs["macro_f1"], mk), gs["ece"])
        lin.append(fila)
    lin += ["", "T2.1 (≥ +0,05 de macro-F1 sobre kNN-32 en ≥ 3 tareas): %d tareas con Δ ≥ 0,05." % ganadas]
    if res_s:
        lin.append("Con soporte: %d tareas con Δ ≥ 0,05." % ganadas_s)
    return "\n".join(lin)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--datos", help="directorio de model.datos.convertir")
    ap.add_argument("--liston")
    ap.add_argument("--extra", nargs="*", default=[])
    ap.add_argument("--renombrar", action="store_true", help="evalúa también con las opciones renombradas a A/B/C…")
    ap.add_argument("--soporte", type=int, default=0, help="ejemplos de soporte por clase (0 = sin soporte); 32 = el de T1.7a")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--max-filas", type=int, default=0, help="tope de filas por conjunto (0 = todas)")
    a = ap.parse_args(argv)
    sal = Path(a.salida)
    (sal / "pred").mkdir(parents=True, exist_ok=True)
    modelo, ck = cargar_modelo(a.ckpt, a.device)
    enc = Codificador(device=a.device)
    enc.cargar_enc(ck.get("enc"))  # capas de e5 ajustadas en T2.2, si las hay
    res, res_r, res_s = {}, {}, {}
    sop = SoporteEval(train_por_tarea(a.datos), a.soporte) if a.soporte else None
    for nombre, filas in conjuntos_test(a.datos, a.liston, a.extra).items():
        if a.max_filas:
            filas = filas[:a.max_filas]
        filas = CE.asignar_ids(filas, nombre) if any("id" not in r for r in filas) else filas
        preds = predecir(modelo, enc, filas)
        with open(sal / "pred" / (nombre + ".jsonl"), "w", encoding="utf-8") as f:
            for p in preds:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        res[nombre] = CE.evaluar(filas, preds)
        print("== %s\n%s" % (nombre, CE.tabla(res[nombre])), flush=True)
        if sop:
            (sal / "pred_soporte").mkdir(exist_ok=True)
            preds_s = predecir(modelo, enc, filas, soporte=sop)
            with open(sal / "pred_soporte" / (nombre + ".jsonl"), "w", encoding="utf-8") as f:
                for p in preds_s:
                    f.write(json.dumps(p, ensure_ascii=False) + "\n")
            res_s[nombre] = CE.evaluar(filas, preds_s)
            print("== %s con soporte (k=%d)\n%s" % (nombre, a.soporte, CE.tabla(res_s[nombre])), flush=True)
        if a.renombrar:
            (sal / "pred_renombrado").mkdir(exist_ok=True)
            filas_r = [D.renombrar_fila(r) for r in filas]
            preds_r = predecir(modelo, enc, filas_r)
            with open(sal / "pred_renombrado" / (nombre + ".jsonl"), "w", encoding="utf-8") as f:
                for p in preds_r:
                    f.write(json.dumps(p, ensure_ascii=False) + "\n")
            res_r[nombre] = CE.evaluar(filas_r, preds_r)
    with open(sal / "resultados.json", "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    if sop:
        with open(sal / "resultados_soporte.json", "w") as f:
            json.dump(res_s, f, indent=1, ensure_ascii=False)
        print("prototipos calculados: %d (uno por tarea)" % sop.cache.calculos)
    if a.renombrar:
        with open(sal / "resultados_renombrado.json", "w") as f:
            json.dump(res_r, f, indent=1, ensure_ascii=False)
        c, _, _ = tabla_caida(res, res_r)
        (sal / "caida.md").write_text(c + "\n", encoding="utf-8")
        print("== caída al renombrar\n" + c)
    t = tabla_delta(res, res_s or None)
    (sal / "delta.md").write_text(t + "\n", encoding="utf-8")
    print(t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
