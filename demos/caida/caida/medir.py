"""Latencia por petición de tres preguntas, con caché de torres fría y caliente. Solo biblioteca estándar.

Fría: cada petición lleva descripciones que el servidor no ha visto (se les añade una marca única por corrida y por
petición), así que L2 tiene que calcular las torres del esquema al vuelo. Caliente: la misma petición repetida tras
una primera llamada que llena la caché. Sin caché de respuestas (no se manda `nonce`). Con un servidor sin L2/TORR
las dos series coinciden: la medida lo muestra tal cual, no lo oculta.
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
import time
import uuid
from typing import List

from . import api
from .agentes import ranking
from .estado import peticiones_turno
from .motor import Juego
from .partida import DECIDIR
from .util import escribir_json, percentil, redondea


def cuerpos_reales(n: int, semilla: int = 1) -> List[List[dict]]:
    """Por decisión, sus dos peticiones (choice; score + noul), de turnos reales de una partida del profesor (se repite la partida con otras semillas si hace falta)."""
    out: List[List[dict]] = []
    s = semilla
    while len(out) < n:
        j = Juego(s)
        while not j.terminado and len(out) < n:
            r = ranking(j)
            if len(r) >= 2:
                ops = [(str(i + 1), c, m) for i, (c, _, m) in enumerate(r[:api.K])]
                out.append(peticiones_turno(j, ops))
            j.jugar(r[0][0])
        s += 1
    return out


def salar(cuerpos: List[dict], marca: str) -> List[dict]:
    """Copia de las peticiones de una decisión con descripciones únicas (fuerza torres nuevas) y estado único."""
    out = copy.deepcopy(cuerpos)
    for c in out:
        c["state"] += f"\n[{marca}]"
        for q in c["questions"]:
            for o in q.get("options", []):
                o["description"] = f'{o.get("description", "")} [{marca}-{q["id"]}-{o["id"]}]'
    return out


def serie(url: str, decisiones: List[List[dict]], timeout: float) -> dict:
    """Cada decisión son dos peticiones en serie; su latencia es la suma."""
    lat, srv, escalas, errores = [], [], 0, 0
    t0 = time.perf_counter()
    for cuerpos in decisiones:
        try:
            res, ms = {}, 0.0
            for c in cuerpos:
                r, t = api.decidir(url, c, timeout)
                res.update(r)
                ms += t
        except api.ErrorRed:
            errores += 1
            continue
        lat.append(ms)
        srv.append(sum(float(r.get("ms") or 0) for r in res.values()))
        escalas += any(r.get("escalate") for r in res.values())
    total = time.perf_counter() - t0
    return {
        "peticiones": len(decisiones), "ok": len(lat), "errores_red": errores, "peticiones_con_escalada": escalas,
        "ms_p50": redondea(percentil(lat, 50)), "ms_p95": redondea(percentil(lat, 95)), "ms_p99": redondea(percentil(lat, 99)),
        "ms_media": redondea(sum(lat) / len(lat)) if lat else None,
        "ms_servidor_media": redondea(sum(srv) / len(srv)) if srv else None,
        # una decisión = dos peticiones (3 preguntas), en serie desde un solo cliente
        "decisiones_por_s": redondea(len(lat) / total, 1) if total > 0 and lat else None,
    }


def medir(url: str, n: int = 100, timeout: float = 30.0, decidir: str = "tau") -> dict:
    cuerpos = cuerpos_reales(n)
    marca = uuid.uuid4().hex[:8]
    fria = serie(url, [salar(c, f"{marca}-{i}") for i, c in enumerate(cuerpos)], timeout)
    # caliente: la petición «fija» se manda una vez para llenar la caché y luego n veces
    fija = salar(cuerpos[0], f"{marca}-fija")
    for c in fija:
        api.decidir(url, c, timeout)
    caliente = serie(url, [fija] * n, timeout)
    return {"url": url, "decidir": decidir, "decisiones_por_serie": n, "peticiones_por_decision": 2, "preguntas_por_decision": 3, "fria": fria, "caliente": caliente}


def markdown(r: dict) -> str:
    cols = [("ms_p50", "p50 ms"), ("ms_p95", "p95 ms"), ("ms_p99", "p99 ms"), ("ms_servidor_media", "ms servidor (media)"),
            ("decisiones_por_s", "decisiones/s"), ("peticiones_con_escalada", "con escalada"), ("errores_red", "errores")]
    l = [f"# Chispa: Caída — latencia por petición de 3 preguntas ({r['decisiones_por_serie']} decisiones por serie, 2 peticiones cada una)", "", f"Servidor: `{r['url']}` (modo de decisión `{r['decidir']}`: no cambia lo que se pide, solo se anota)", "",
         "| caché de torres | " + " | ".join(t for _, t in cols) + " |", "|---|" + "---|" * len(cols)]
    for nombre in ("fria", "caliente"):
        s = r[nombre]
        l.append(f"| {nombre} | " + " | ".join("—" if s[k] is None else str(s[k]) for k, _ in cols) + " |")
    l += ["", "Cliente único y en serie: `decisiones/s` = decisiones/segundo. Fría = descripciones nunca vistas (torres al vuelo); caliente = la misma petición repetida."]
    return "\n".join(l) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="medir", description=__doc__.splitlines()[0])
    ap.add_argument("--url", required=True)
    ap.add_argument("--salida", required=True, help="directorio (latencia.json y latencia.md)")
    ap.add_argument("--n", type=int, default=100, help="peticiones por serie")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--decidir", choices=DECIDIR, default="tau", help="se anota en el informe; la latencia medida es la misma")
    a = ap.parse_args(argv)
    try:
        api.salud(a.url)
    except api.ErrorRed as e:
        print(f"medir: {a.url} no responde a /healthz: {e}", file=sys.stderr)
        return 2
    r = medir(a.url, a.n, a.timeout, a.decidir)
    os.makedirs(a.salida, exist_ok=True)
    escribir_json(os.path.join(a.salida, "latencia.json"), r)
    md = markdown(r)
    with open(os.path.join(a.salida, "latencia.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0 if r["fria"]["ok"] and r["caliente"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
