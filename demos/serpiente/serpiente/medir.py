"""Latencia por decisión (una petición choice), con caché de torres fría y caliente. Solo biblioteca estándar.

Fría: cada petición lleva descripciones que el servidor no ha visto (marca única por corrida y petición), así que L2
tiene que calcular las torres al vuelo. Caliente: la misma petición repetida tras una primera llamada que llena la
caché. Sin caché de respuestas (no se manda `nonce`). Con un servidor sin L2 las dos series coinciden: se muestra tal cual.
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
from .agentes import opciones_vivas, profesor
from .estado import opciones, texto_estado
from .motor import Juego
from .partida import DECIDIR
from .util import escribir_json, percentil, redondea


def cuerpos_reales(n: int, semilla: int = 1) -> List[dict]:
    """Peticiones de pasos reales de partidas del profesor (con otras semillas si hace falta). Solo pasos con decisión."""
    out: List[dict] = []
    s = semilla
    while len(out) < n:
        j = Juego(s)
        while not j.terminado and len(out) < n:
            if opciones_vivas(j) >= 2:
                out.append(api.construir_peticion(texto_estado(j), opciones(j)))
            j.paso(profesor(j))
        s += 1
    return out


def salar(cuerpo: dict, marca: str) -> dict:
    """Copia con descripciones y estado únicos (fuerza torres nuevas)."""
    c = copy.deepcopy(cuerpo)
    c["state"] += f"\n[{marca}]"
    for q in c["questions"]:
        for o in q.get("options", []):
            o["description"] = f'{o.get("description", "")} [{marca}-{o["id"]}]'
    return c


def serie(url: str, cuerpos: List[dict], timeout: float) -> dict:
    lat, srv, escalas, errores = [], [], 0, 0
    t0 = time.perf_counter()
    for c in cuerpos:
        try:
            res, ms = api.decidir(url, c, timeout)
        except api.ErrorRed:
            errores += 1
            continue
        lat.append(ms)
        srv.append(sum(float(r.get("ms") or 0) for r in res.values()))
        escalas += any(r.get("escalate") for r in res.values())
    total = time.perf_counter() - t0
    return {
        "peticiones": len(cuerpos), "ok": len(lat), "errores_red": errores, "peticiones_con_escalada": escalas,
        "ms_p50": redondea(percentil(lat, 50)), "ms_p95": redondea(percentil(lat, 95)), "ms_p99": redondea(percentil(lat, 99)),
        "ms_media": redondea(sum(lat) / len(lat)) if lat else None,
        "ms_servidor_media": redondea(sum(srv) / len(srv)) if srv else None,
        "decisiones_por_s": redondea(len(lat) / total, 1) if total > 0 and lat else None,
    }


def medir(url: str, n: int = 100, timeout: float = 30.0, decidir: str = "tau") -> dict:
    cuerpos = cuerpos_reales(n)
    marca = uuid.uuid4().hex[:8]
    fria = serie(url, [salar(c, f"{marca}-{i}") for i, c in enumerate(cuerpos)], timeout)
    fija = salar(cuerpos[0], f"{marca}-fija")
    api.decidir(url, fija, timeout)
    caliente = serie(url, [fija] * n, timeout)
    return {"url": url, "decidir": decidir, "decisiones_por_serie": n, "fria": fria, "caliente": caliente}


def markdown(r: dict) -> str:
    cols = [("ms_p50", "p50 ms"), ("ms_p95", "p95 ms"), ("ms_p99", "p99 ms"), ("ms_servidor_media", "ms servidor (media)"),
            ("decisiones_por_s", "decisiones/s"), ("peticiones_con_escalada", "con escalada"), ("errores_red", "errores")]
    l = [f"# Chispa: Serpiente — latencia por decisión ({r['decisiones_por_serie']} por serie, 1 petición cada una)", "",
         f"Servidor: `{r['url']}` (modo de decisión `{r['decidir']}`: no cambia lo que se pide, solo se anota)", "",
         "| caché de torres | " + " | ".join(t for _, t in cols) + " |", "|---|" + "---|" * len(cols)]
    for nombre in ("fria", "caliente"):
        s = r[nombre]
        l.append(f"| {nombre} | " + " | ".join("—" if s[k] is None else str(s[k]) for k, _ in cols) + " |")
    l += ["", "Cliente único y en serie. Fría = descripciones nunca vistas; caliente = la misma petición repetida."]
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
