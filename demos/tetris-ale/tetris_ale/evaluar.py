"""Evaluador en el simulador: N partidas con semillas fijas por agente, con tope de piezas. Salida JSON y Markdown."""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List

from . import api, maestro as M
from .partida import DECIDIR, AgenteAleatorio, AgenteChispa, AgenteMaestro, jugar_partida
from .util import escribir_json, percentil, redondea


def resumen(partidas: List[dict]) -> dict:
    ds = [d for p in partidas for d in p["decisiones"] if not d.forzada]
    n = len(partidas)
    lat = [d.ms_cliente for d in ds if d.ms_cliente is not None]
    chispa = any(d.decidio for d in ds)
    opinan = [d for d in ds if d.opino]
    con = opinan if chispa else [d for d in ds if d.coincide is not None]
    # «bajo τ»: Chispa escaló el choice (se jugó su argmax o el maestro); los fallos de red no cuentan
    bajo = [d for d in ds if d.decidio == "chispa_bajo_tau" or (d.escudo and d.motivo_escudo != "error_red")]
    lineas = [p["lineas"] for p in partidas]
    return {
        "partidas": n,
        "lineas_media": redondea(sum(lineas) / n, 2),
        "lineas_min": min(lineas), "lineas_max": max(lineas),
        "piezas_media": redondea(sum(p["piezas"] for p in partidas) / n, 2),
        "game_overs": sum(p["game_over"] for p in partidas),
        "decisiones": len(ds),
        # Chispa: entre las decisiones donde opinó, cuántas eligieron la del maestro. Resto: jugadas iguales a la del maestro.
        "coincidencia": redondea(sum(bool(d.coincide) for d in con) / len(con), 3) if con else None,
        "pct_bajo_tau": redondea(100 * len(bajo) / len(ds), 1) if ds and chispa else None,
        "intervenciones_escudo": sum(d.escudo for d in ds),
        "errores_red": sum(d.motivo_escudo == "error_red" for d in ds),
        "latencia_ms_p50": redondea(percentil(lat, 50), 3),
        "latencia_ms_p99": redondea(percentil(lat, 99), 3),
    }


def evaluar(semillas: List[int], max_piezas: int, url: str = None, decidir: str = "tau", agentes=None) -> dict:
    todos = {
        "aleatorio": lambda s: AgenteAleatorio(s),
        "maestro": lambda s: AgenteMaestro("maestro"),
        "el-tetris": lambda s: AgenteMaestro("el-tetris", M.PESOS_EL_TETRIS),
    }
    if url:
        todos["chispa"] = lambda s: AgenteChispa(url, "chispa", decidir=decidir)
    out: Dict[str, dict] = {}
    for nombre, mk in todos.items():
        if agentes and nombre not in agentes:
            continue
        ps = [jugar_partida(s, mk(s), max_piezas) for s in semillas]
        out[nombre] = {"resumen": resumen(ps),
                       "por_partida": [{k: v for k, v in p.items() if k != "decisiones"} for p in ps]}
    return {"decidir": decidir, "url": url, "semillas": semillas, "max_piezas": max_piezas, "agentes": out}


def markdown(r: dict) -> str:
    cols = [("lineas_media", "líneas/partida"), ("lineas_min", "mín"), ("lineas_max", "máx"), ("piezas_media", "piezas"),
            ("game_overs", "game over"), ("coincidencia", "coincide maestro"), ("pct_bajo_tau", "% bajo τ"),
            ("intervenciones_escudo", "escudo"), ("latencia_ms_p50", "p50 ms"), ("latencia_ms_p99", "p99 ms")]
    l = [f"# Tetris ALE (simulador) — evaluación ({len(r['semillas'])} partidas por agente, tope {r['max_piezas']} piezas)", ""]
    if r.get("url"):
        l += [f"- Modo de decisión de Chispa: `{r['decidir']}`", f"- Servidor: `{r['url']}`"]
    l += [f"- Semillas: {r['semillas'][0]}…{r['semillas'][-1]}", "",
          "| agente | " + " | ".join(t for _, t in cols) + " |", "|---|" + "---|" * len(cols)]
    for n, a in r["agentes"].items():
        s = a["resumen"]
        l.append(f"| {n} | " + " | ".join("—" if s[k] is None else str(s[k]) for k, _ in cols) + " |")
    l += ["", "Líneas, piezas: media por partida (la principal es líneas). Coincidencia: en Chispa, entre las decisiones donde opinó "
          "(sin escalar), fracción que eligió la mejor del maestro; en los demás, fracción de jugadas iguales a la del maestro. "
          "% bajo τ: decisiones donde Chispa escaló (juega el maestro, o su argmax con `--decidir argmax`). "
          "Latencia: por decisión (una petición HTTP en Chispa; cálculo local en el resto). "
          "Todos los agentes pasan por el veto de seguridad."]
    errs = sum(a["resumen"]["errores_red"] for a in r["agentes"].values())
    if errs:
        l += ["", f"**Aviso:** {errs} decisiones con error de red (cuentan como escudo)."]
    return "\n".join(l) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evaluar", description=__doc__)
    ap.add_argument("--url", help="servidor de Chispa; sin él solo se evalúan los agentes locales")
    ap.add_argument("--salida", required=True, help="directorio de salida (evaluacion.json y evaluacion.md)")
    ap.add_argument("--partidas", type=int, default=20)
    ap.add_argument("--semilla-base", type=int, default=1)
    ap.add_argument("--max-piezas", type=int, default=500)
    ap.add_argument("--decidir", choices=DECIDIR, default="tau", help="tau: al escalar juega el maestro; argmax: se juega el argmax de probs")
    ap.add_argument("--agentes", nargs="*", help="subconjunto de aleatorio, maestro, el-tetris, chispa")
    a = ap.parse_args(argv)
    if a.url:
        try:
            api.salud(a.url)
        except api.ErrorRed as e:
            print(f"evaluar: {a.url} no responde a /healthz: {e}", file=sys.stderr)
            return 2
    semillas = list(range(a.semilla_base, a.semilla_base + a.partidas))
    r = evaluar(semillas, a.max_piezas, a.url, a.decidir, a.agentes)
    os.makedirs(a.salida, exist_ok=True)
    escribir_json(os.path.join(a.salida, "evaluacion.json"), r)
    md = markdown(r)
    with open(os.path.join(a.salida, "evaluacion.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
