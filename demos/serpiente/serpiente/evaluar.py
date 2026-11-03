"""Evaluador: N partidas (20 por defecto, semillas fijas) por agente. Salida JSON y Markdown."""
from __future__ import annotations

import argparse
import os
import statistics
import sys
from typing import Dict, List

from . import api
from .motor import MAX_PASOS
from .partida import DECIDIR, AgenteAleatorio, AgenteChispa, AgenteProfesor, jugar_partida
from .util import escribir_json, percentil, redondea


def _media_mediana(v: List[float]):
    return redondea(sum(v) / len(v), 2), redondea(statistics.median(v), 2)


def resumen(partidas: List[dict]) -> dict:
    ds = [d for p in partidas for d in p["decisiones"] if not d.forzada]
    lat = [d.ms_cliente for d in ds if d.ms_cliente is not None]
    chispa = any(d.decidio for d in ds)
    # coincidencia: entre las decisiones donde Chispa decidió (opinó sin escalar o se jugó su argmax), % de la jugada
    # igual a la del profesor. El escudo (juega el profesor) no cuenta. Aleatorio: todas las decisiones.
    base = [d for d in ds if d.decidio in ("chispa_tau", "chispa_bajo_tau")] if chispa else ds
    p_med, p_mdn = _media_mediana([p["pasos"] for p in partidas])
    c_med, c_mdn = _media_mediana([p["comidas"] for p in partidas])
    pct = lambda n, t: redondea(100.0 * n / t, 1) if t else None
    return {
        "partidas": len(partidas),
        "pasos_media": p_med, "pasos_mediana": p_mdn,
        "comida_media": c_med, "comida_mediana": c_mdn,
        "muertes": sum(p["fin"] in ("muro", "cuerpo") for p in partidas),
        "topes": sum(p["fin"] == "tope" for p in partidas),
        "decisiones": len(ds),
        "decisiones_chispa": len(base) if chispa else None,
        "coincidencia_pct": pct(sum(bool(d.coincide) for d in base), len(base)),
        "bajo_tau_pct": pct(sum(d.decidio == "chispa_bajo_tau" for d in ds), len(ds)) if chispa else None,
        "escudo_pct": pct(sum(d.escudo for d in ds), len(ds)) if chispa else None,
        "errores_red": sum(d.motivo_escudo == "error_red" for d in ds),
        "latencia_ms_p50": redondea(percentil(lat, 50), 3),
        "latencia_ms_p99": redondea(percentil(lat, 99), 3),
    }


def evaluar(url: str, semillas: List[int], agentes=None, decidir: str = "tau") -> dict:
    todos = {
        "aleatorio": lambda s: AgenteAleatorio(s),
        "profesor": lambda s: AgenteProfesor(),
        "chispa_zero_shot": lambda s: AgenteChispa(url, "chispa_zero_shot", decidir=decidir),
    }
    out: Dict[str, dict] = {}
    for nombre, mk in todos.items():
        if agentes and nombre not in agentes:
            continue
        ps = [jugar_partida(s, mk(s)) for s in semillas]
        out[nombre] = {"resumen": resumen(ps),
                       "por_partida": [{k: v for k, v in p.items() if k != "decisiones"} for p in ps]}
    return {"decidir": decidir, "url": url, "semillas": semillas, "max_pasos": MAX_PASOS, "agentes": out}


def markdown(r: dict) -> str:
    cols = [("pasos_media", "pasos (media)"), ("pasos_mediana", "pasos (mediana)"), ("comida_media", "comida (media)"),
            ("comida_mediana", "comida (mediana)"), ("coincidencia_pct", "coincide prof. %"), ("bajo_tau_pct", "bajo τ %"),
            ("escudo_pct", "escudo %"), ("latencia_ms_p50", "p50 ms"), ("latencia_ms_p99", "p99 ms")]
    l = [f"# Chispa: Serpiente — evaluación ({len(r['semillas'])} partidas por agente, tope {r['max_pasos']} pasos)", "",
         f"- Modo de decisión de Chispa: `{r['decidir']}`", f"- Servidor: `{r['url']}`", "",
         "| agente | " + " | ".join(t for _, t in cols) + " |", "|---|" + "---|" * len(cols)]
    for n, a in r["agentes"].items():
        s = a["resumen"]
        l.append(f"| {n} | " + " | ".join("—" if s[k] is None else str(s[k]) for k, _ in cols) + " |")
    l += ["", "Pasos y comida: por partida (se acaba al chocar o a los 500 pasos). Coincidencia: entre las decisiones donde "
          "Chispa decidió (sin escudo), % de jugadas iguales a la del profesor; en aleatorio, de todas. Bajo τ y escudo: "
          "% de las decisiones (sin contar las forzadas, con una sola opción que no choca). Latencia: por decisión, medida "
          "en el cliente (en aleatorio y profesor es el cálculo local)."]
    return "\n".join(l) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evaluar", description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--salida", required=True, help="directorio (evaluacion.json y evaluacion.md)")
    ap.add_argument("--partidas", type=int, default=20)
    ap.add_argument("--semilla-base", type=int, default=1)
    ap.add_argument("--decidir", choices=DECIDIR, default="tau", help="tau: al escalar juega el profesor; argmax: se juega el argmax de probs")
    a = ap.parse_args(argv)
    try:
        api.salud(a.url)
    except api.ErrorRed as e:
        print(f"evaluar: {a.url} no responde a /healthz: {e}", file=sys.stderr)
        return 2
    semillas = list(range(a.semilla_base, a.semilla_base + a.partidas))
    r = evaluar(a.url, semillas, decidir=a.decidir)
    os.makedirs(a.salida, exist_ok=True)
    escribir_json(os.path.join(a.salida, "evaluacion.json"), r)
    md = markdown(r)
    with open(os.path.join(a.salida, "evaluacion.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
