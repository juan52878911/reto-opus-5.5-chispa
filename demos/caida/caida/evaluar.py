"""Evaluador: 20 partidas con semillas fijas por agente. Salida JSON y Markdown."""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List

from . import api
from .partida import DECIDIR, AgenteAleatorio, AgenteChispa, AgenteProfesor, jugar_partida
from .util import escribir_json, percentil, redondea


def _por_origen(ds, k: str) -> tuple:
    """(n, coincidencia con el profesor) de las decisiones con `decidio == k`."""
    g = [d for d in ds if d.decidio == k]
    return len(g), (redondea(sum(bool(d.coincide) for d in g) / len(g), 3) if g else None)


def resumen(partidas: List[dict]) -> dict:
    ds = [d for p in partidas for d in p["decisiones"] if not d.forzada]
    lat = [d.ms_cliente for d in ds if d.ms_cliente is not None]
    con = [d for d in ds if d.coincide is not None]
    opinan = [d for d in ds if d.opino]
    chispa = any(d.id_elegida is not None or d.escudo for d in ds)
    n = len(partidas)
    n_tau, c_tau = _por_origen(ds, "chispa_tau")
    n_bajo, c_bajo = _por_origen(ds, "chispa_bajo_tau")
    n_esc, c_esc = _por_origen(ds, "escudo")
    return {
        "partidas": n,
        "piezas_media": redondea(sum(p["piezas"] for p in partidas) / n, 2),
        "filas_media": redondea(sum(p["filas"] for p in partidas) / n, 2),
        "puntos_media": redondea(sum(p["puntos"] for p in partidas) / n, 1),
        "game_overs": sum(p["game_over"] for p in partidas),
        "decisiones": len(ds),
        # Chispa: coincidencia = entre las decisiones donde Chispa opinó, cuántas eligieron la mejor del profesor
        # (el escudo no cuenta). Aleatorio/profesor: fracción de jugadas iguales a la del profesor.
        "coincidencia": redondea(sum(d.coincide for d in (opinan if chispa else con)) / len(opinan if chispa else con), 3)
        if (opinan if chispa else con) else None,
        # las tres cifras de Chispa y la coincidencia con el profesor de cada una (en escudo juega el profesor: 1.0 por construcción)
        "n_chispa_tau": n_tau, "coincidencia_chispa_tau": c_tau,
        "n_chispa_bajo_tau": n_bajo, "coincidencia_chispa_bajo_tau": c_bajo,
        "n_escudo": n_esc, "coincidencia_escudo": c_esc,
        "coincidencia_jugada": redondea(sum(bool(d.coincide) for d in ds) / len(ds), 3) if ds and chispa else None,
        "intervenciones_escudo": sum(d.escudo for d in ds),
        "tasa_escudo": redondea(sum(d.escudo for d in ds) / len(ds), 3) if ds and chispa else None,
        "errores_red": sum(d.motivo_escudo == "error_red" for d in ds),
        "latencia_ms_p50": redondea(percentil(lat, 50), 3),
        "latencia_ms_p99": redondea(percentil(lat, 99), 3),
    }


def evaluar(url: str, url_fewshot: str, semillas: List[int], max_piezas: int, agentes=None, decidir: str = "tau") -> dict:
    todos = {
        "aleatorio": lambda s: AgenteAleatorio(s),
        "profesor": lambda s: AgenteProfesor(),
        "chispa_zero_shot": lambda s: AgenteChispa(url, "chispa_zero_shot", decidir=decidir),
        "chispa_few_shot": lambda s: AgenteChispa(url_fewshot, "chispa_few_shot", decidir=decidir),
    }
    out: Dict[str, dict] = {}
    for nombre, mk in todos.items():
        if agentes and nombre not in agentes:
            continue
        ps = [jugar_partida(s, mk(s), max_piezas) for s in semillas]
        out[nombre] = {"resumen": resumen(ps),
                       "por_partida": [{k: v for k, v in p.items() if k != "decisiones"} for p in ps]}
    return {"decidir": decidir, "url_zero_shot": url, "url_few_shot": url_fewshot, "semillas": semillas, "max_piezas": max_piezas, "agentes": out}


def markdown(r: dict) -> str:
    cols = [("piezas_media", "piezas"), ("filas_media", "filas"), ("puntos_media", "puntos"), ("game_overs", "game over"),
            ("coincidencia", "coincide prof."), ("n_chispa_tau", "chispa_tau"), ("coincidencia_chispa_tau", "coin. tau"),
            ("n_chispa_bajo_tau", "bajo_tau"), ("coincidencia_chispa_bajo_tau", "coin. bajo_tau"),
            ("n_escudo", "escudo"), ("coincidencia_escudo", "coin. escudo"), ("coincidencia_jugada", "coin. jugada"), ("tasa_escudo", "escudo %"),
            ("latencia_ms_p50", "p50 ms"), ("latencia_ms_p99", "p99 ms")]
    l = [f"# Chispa: Caída — evaluación ({len(r['semillas'])} partidas por agente, tope {r['max_piezas']} piezas)", "",
         f"- Modo de decisión de Chispa: `{r.get('decidir', 'tau')}`", f"- Chispa zero-shot: `{r['url_zero_shot']}`", f"- Chispa few-shot: `{r['url_few_shot']}`", "",
         "| agente | " + " | ".join(t for _, t in cols) + " |", "|---|" + "---|" * len(cols)]
    for n, a in r["agentes"].items():
        s = a["resumen"]
        l.append(f"| {n} | " + " | ".join("—" if s[k] is None else str(s[k]) for k, _ in cols) + " |")
    l += ["", "Piezas/filas/puntos: media por partida. Coincidencia: entre las decisiones donde Chispa opinó (sin escalar), "
          "fracción que eligió la mejor del profesor; en aleatorio, fracción de jugadas iguales a la del profesor. "
          "chispa_tau: Chispa no escaló; bajo_tau: escaló pero se jugó su argmax (solo con `--decidir argmax`); escudo: jugó el profesor "
          "(su coincidencia es 1 por construcción); coin. jugada: la jugada final contra la del profesor, las tres juntas. "
          "Las opciones se ofrecen barajadas con la semilla de la partida: un azar entre 6 coincide ≈ 0,167. "
          "Latencia: por decisión (dos peticiones HTTP en Chispa: choice, y score + noul; cálculo local en el resto)."]
    errs = sum(a["resumen"]["errores_red"] for a in r["agentes"].values())
    if errs:
        l += ["", f"**Aviso:** {errs} decisiones con error de red (cuentan como escudo)."]
    return "\n".join(l) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evaluar", description=__doc__)
    ap.add_argument("--url", required=True, help="servidor de Chispa (zero-shot)")
    ap.add_argument("--url-fewshot", help="servidor con el .chispa few-shot (por defecto, el mismo --url)")
    ap.add_argument("--salida", required=True, help="directorio de salida (evaluacion.json y evaluacion.md)")
    ap.add_argument("--partidas", type=int, default=20)
    ap.add_argument("--semilla-base", type=int, default=1)
    ap.add_argument("--max-piezas", type=int, default=150)
    ap.add_argument("--decidir", choices=DECIDIR, default="tau", help="tau (hoy): al escalar juega el profesor; argmax: se juega el argmax de probs")
    a = ap.parse_args(argv)
    for u in {a.url, a.url_fewshot or a.url}:
        try:
            api.salud(u)
        except api.ErrorRed as e:
            print(f"evaluar: {u} no responde a /healthz: {e}", file=sys.stderr)
            return 2
    semillas = list(range(a.semilla_base, a.semilla_base + a.partidas))
    r = evaluar(a.url, a.url_fewshot or a.url, semillas, a.max_piezas, decidir=a.decidir)
    os.makedirs(a.salida, exist_ok=True)
    escribir_json(os.path.join(a.salida, "evaluacion.json"), r)
    md = markdown(r)
    with open(os.path.join(a.salida, "evaluacion.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
