"""L2 sobre JevBench público, sin soporte y con soporte k por opción dejando fuera el caso (y sus paráfrasis).

    python -m model.evaluacion.jevbench_l2 --ckpt mejor.pt --jevbench RUTA --salida DIR [--k 0 8 32] [--device cpu] [--max-casos N]

Escribe `DIR/pred/l2_k<k>.jsonl` (`{id, probs, ms, soporte_n}`) y `DIR/jevbench_filas.jsonl` (las filas del esquema).
k = 0 es zero-shot. Con k > 0, un caso sin ningún otro caso de su esquema se predice sin soporte (`soporte_n` = 0: se dice
en el informe, no se cuenta como «con soporte»). Los prototipos se calculan una vez por pliegue (esquema + grupo de paráfrasis).
En score, la etiqueta que se evalúa es la mediana CORAL (`metricas.top1`), no el argmax de las probs. `--kappa` = λ (κ = λ de formula-shrinkage.md; el zero-shot es k = 0).
L2 trunca el estado a MAX_TOK tokens (model.l2.modelo): los casos largos del nivel hard pierden el final; el informe lo cuenta.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from . import chispa_eval as CE
from .jevbench import cargar_jevbench, pliegues


def _con_tarea_esquema(filas):
    """L2 busca los prototipos por `tarea`: aquí es el esquema. La familia sigue en `familia`."""
    return [dict(r, tarea=r["esquema"], familia=r["tarea"]) for r in filas]


def predecir_variante(modelo, enc, filas, k, lote=64, kappa=0.0):
    """[{id, probs, ms, soporte_n}] en el orden de `filas`."""
    import torch
    from model.l2.modelo import prototipos
    filas = _con_tarea_esquema(filas)
    por_id, vistos = {}, 0
    for clave, rs, sop in pliegues(filas, k) if k else [(r["id"], [r], []) for r in filas]:
        protos = None
        if sop:
            with torch.no_grad():
                protos = {rs[0]["tarea"]: prototipos(modelo, enc, sop, kappa=kappa)}
        for i in range(0, len(rs), lote):
            fs = rs[i:i + lote]
            t0 = time.perf_counter()
            with torch.no_grad():
                probs, _ = modelo(fs, enc, entrenar=False, protos=protos)
            ms = (time.perf_counter() - t0) * 1000 / len(fs)
            for r, p in zip(fs, probs):
                p = p.double().cpu()
                por_id[r["id"]] = {"id": r["id"], "probs": dict(zip(r["opciones"], (p / p.sum()).tolist())), "ms": round(ms, 3),
                                   "soporte_n": len(sop)}
        vistos += len(rs)
    return [por_id[r["id"]] for r in filas]


def escribir(ruta, filas):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        for r in filas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--jevbench", required=True, help="clon del repo, datasets/public o un .jsonl")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--k", type=int, nargs="*", default=[0, 8, 32])
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--max-tok", type=int, default=0, help="tokens por mensaje (0 = el del checkpoint; sin él, 128)")
    ap.add_argument("--kappa", type=float, default=0.0, help="shrinkage de los prototipos hacia la torre de la descripción (0 = sin)")
    ap.add_argument("--max-casos", type=int, default=0, help="tope de casos (0 = todos); solo para pruebas en seco")
    a = ap.parse_args(argv)
    from model.l2.evaluar import cargar_modelo
    from model.l2.modelo import MAX_TOK, Codificador
    filas = cargar_jevbench(a.jevbench)
    if a.max_casos:
        filas = filas[:a.max_casos]
    sal = Path(a.salida)
    escribir(sal / "jevbench_filas.jsonl", filas)
    modelo, ck = cargar_modelo(a.ckpt, a.device)
    enc = Codificador(device=a.device, max_tok=a.max_tok or ck.get("max_tok", MAX_TOK))
    enc.cargar_enc(ck.get("enc"))
    for k in a.k:
        t0 = time.time()
        preds = predecir_variante(modelo, enc, filas, k, kappa=a.kappa)
        escribir(sal / "pred" / f"l2_k{k}.jsonl", preds)
        res = CE.evaluar(filas, [{x: p[x] for x in ("id", "probs", "ms")} for p in preds])
        print(f"== L2 k={k}: exactitud {res['global']['exactitud']:.4f}, macro-F1 {res['global']['macro_f1']:.4f}, "
              f"{sum(p['soporte_n'] > 0 for p in preds)} casos con soporte, {time.time() - t0:.1f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
