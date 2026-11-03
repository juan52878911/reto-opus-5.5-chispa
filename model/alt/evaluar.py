"""Evaluación de la alternativa (b) con el mismo arnés que Chispa (`model.evaluacion.chispa_eval`).

    python -m model.alt.evaluar --ckpt DIR --jevbench RUTA [--bateria DIR_JSONL] [--salida DIR] [--max-filas N]

  - JevBench: `cargar_jevbench` y las métricas de `chispa_eval.evaluar` (exactitud, F1 macro, ECE, cobertura a precisión 0,95 y 0,99, por familia).
  - Batería oficial: las filas `split: test` de massive, clinc150, hatecheck, spam, inyecciones y herramientas que haya bajo DIR_JSONL.
  - Latencia: p50/p99 por decisión (una fila por llamada) en CPU con 4 hilos, sobre las primeras `--n-latencia` filas.
Escribe `jevbench.json`, `bateria.json`, `latencia.json` y `informe.md` en la salida.
"""
import argparse
import json
import time
from pathlib import Path

import torch

from model.evaluacion import chispa_eval as CE
from model.evaluacion.jevbench import cargar_jevbench
from model.evaluacion.metricas import latencia
from model.l2.datos import conjunto, iterar

BATERIA = ("massive", "clinc150", "hatecheck", "spam", "inyecciones", "herramientas")
COLUMNAS = ("n", "exactitud", "macro_f1", "ece", "cobertura_p95")


def predecir(modelo, filas, lote=16):
    """[{id, probs}] en el orden de `filas`."""
    out = []
    for i in range(0, len(filas), lote):
        fs = filas[i:i + lote]
        out += [{"id": r["id"], "probs": p} for r, p in zip(fs, modelo.probs(fs))]
    return out


def medir_latencia(modelo, filas, n=100, hilos=4):
    """p50/p99 en ms por decisión (lote de 1), CPU con `hilos` hilos. Calienta con 3 filas."""
    previo = torch.get_num_threads()
    torch.set_num_threads(hilos)
    try:
        modelo = modelo.to("cpu").eval()
        fs = filas[:n]
        for r in fs[:3]:
            modelo.probs([r])
        ms = []
        for r in fs:
            t0 = time.perf_counter()
            modelo.probs([r])
            ms.append((time.perf_counter() - t0) * 1000)
        return dict(latencia(ms) or {}, n=len(ms), hilos=hilos)
    finally:
        torch.set_num_threads(previo)


def evaluar_filas(modelo, filas, lote=16):
    return CE.evaluar(filas, predecir(modelo, filas, lote))


def resumen(ev):
    g = ev["global"]
    return {"n": g["n"], "exactitud": g["exactitud"], "macro_f1": g["macro_f1"], "ece": g["ece"], "cobertura_p95": g["cobertura_p95"]["cobertura"]}


def bateria(modelo, rutas, max_filas=None, lote=16):
    """{conjunto: ev} con las filas test de cada conjunto de la batería presente en `rutas`."""
    por = {}
    for r in iterar(rutas):
        c = conjunto(r)
        if r["split"] == "test" and c in BATERIA:
            por.setdefault(c, []).append(r)
    return {c: evaluar_filas(modelo, fs[:max_filas], lote) for c, fs in sorted(por.items())}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--jevbench")
    ap.add_argument("--bateria")
    ap.add_argument("--salida", default="resultados-alt")
    ap.add_argument("--max-filas", type=int)
    ap.add_argument("--lote", type=int, default=16)
    ap.add_argument("--n-latencia", type=int, default=100)
    ap.add_argument("--dispositivo", default="auto")
    a = ap.parse_args(argv)
    from .modelo import CrossEncoder
    dev = ("cuda" if torch.cuda.is_available() else "cpu") if a.dispositivo == "auto" else a.dispositivo
    modelo = CrossEncoder.cargar(a.ckpt, dev)
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    md, lat_filas = ["# Alternativa (b): codificador abierto + cabeza cross-encoder", ""], []
    if a.jevbench:
        filas = cargar_jevbench(a.jevbench)[:a.max_filas]
        lat_filas = filas
        ev = evaluar_filas(modelo, filas, a.lote)
        (sal / "jevbench.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1), encoding="utf-8")
        md += ["## JevBench", "", CE.tabla(ev), ""]
    if a.bateria:
        evs = bateria(modelo, [a.bateria], a.max_filas, a.lote)
        (sal / "bateria.json").write_text(json.dumps(evs, ensure_ascii=False, indent=1), encoding="utf-8")
        md += ["## Batería oficial (test)", "", "| conjunto | " + " | ".join(COLUMNAS) + " |", "|" + "---|" * (len(COLUMNAS) + 1)]
        for c, e in evs.items():
            r = resumen(e)
            md.append("| %s | %s |" % (c, " | ".join(str(r[k]) if k == "n" else "%.4f" % r[k] for k in COLUMNAS)))
        md.append("")
        if not lat_filas:
            lat_filas = [r for r in iterar([a.bateria]) if r["split"] == "test" and conjunto(r) in BATERIA]
    if lat_filas:
        lat = medir_latencia(modelo, lat_filas, a.n_latencia)
        (sal / "latencia.json").write_text(json.dumps(lat, indent=1), encoding="utf-8")
        md += ["## Latencia (CPU, %d hilos, 1 decisión por llamada, n=%d)" % (lat["hilos"], lat["n"]), "",
               "p50 %.1f ms · p99 %.1f ms (criterio del hito: p50 ≤ 60 ms en el i7)" % (lat["p50_ms"], lat["p99_ms"]), ""]
    (sal / "informe.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
