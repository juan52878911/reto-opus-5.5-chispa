"""Partidas reales en `ALE/Tetris-v5` (frameskip=1, sin sticky) con los agentes del simulador.

Por pieza: tablero asentado y tipo leídos de la RAM (`ale_juego`) → `Juego` del simulador → `agente.decidir` → el controlador
lleva la pieza a (forma, columna) y la suelta. Tras cada pieza se compara el tablero asentado del emulador con el que predijo
el simulador (`fieles`).

La secuencia de piezas del cartucho no depende de la semilla ni de los NOOP iniciales (medido): para que las partidas difieran,
las `apertura` primeras piezas de cada semilla se colocan al azar (las mismas para todos los agentes).

    python -m tetris_ale ale --salida DIR [--url URL --decidir argmax] [--partidas 20] [--agentes …] [--video SEMILLA]

Necesita `ale-py` y `gymnasium` (importados solo aquí)."""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from typing import List, Optional

from . import api, evaluar as E, maestro as M
from .ale_juego import FILAS, Partida, normalizar
from .motor import ALTO, Colocacion, Juego, aplicar
from .partida import DECIDIR, AgenteAleatorio, AgenteChispa, AgenteMaestro
from .util import escribir_json

assert ALTO == FILAS, "el simulador y el emulador deben tener las mismas filas"


def tablero_sim(asentado) -> tuple:
    """Celdas (fila, col) con la fila 0 ARRIBA (RAM) → tablero del simulador (fila 0 ABAJO, un entero por fila)."""
    filas = [0] * ALTO
    for r, c in asentado:
        filas[ALTO - 1 - r] |= 1 << c
    return tuple(filas)


def objetivo(col: Colocacion):
    """Colocación del simulador → (forma normalizada con la fila 0 arriba, columna mínima) para el controlador."""
    celdas = [(ALTO - 1 - f, c) for f, c in col.celdas]
    return normalizar(celdas), min(c for _, c in celdas)


def jugar_ale(env, semilla: int, agente, max_piezas: int, apertura: int = 3, al_decidir=None, al_paso=None) -> dict:
    p = Partida(env, semilla, al_paso)
    if hasattr(agente, "preparar"):
        agente.preparar(semilla)
    rng = random.Random(semilla * 31 + 7)
    decisiones, piezas, fieles, lineas_sim = [], 0, 0, 0
    while not p.terminada and piezas < max_piezas:
        x = p.siguiente_pieza()
        if x is None:
            break
        asentado, tipo = x
        j = Juego(semilla, tablero_sim(asentado))
        j.pieza, j.siguiente = tipo, None
        if not j.colocaciones():
            break
        if piezas < apertura:
            rank = M.ranking(j.tablero, j.colocaciones())
            d = None
            col = rank[rng.randrange(len(rank))][0]
        else:
            d = agente.decidir(j)
            col = d.col
            decisiones.append(d)
        ef = aplicar(j.tablero, col)
        forma, columna = objetivo(col)
        if al_decidir:
            al_decidir(p.fotogramas, j, d, col, ef)
        p.colocar(forma, columna)
        piezas += 1
        lineas_sim += ef.lineas
        if not p.terminada:
            p.siguiente_pieza()
            fieles += tablero_sim(p.asentado) == ef.tablero
    return {"semilla": semilla, "piezas": piezas, "lineas": int(p.recompensa), "lineas_sim": lineas_sim,
            "game_over": p.terminada, "fieles": fieles, "fallos_control": p.fallos, "fotogramas": p.fotogramas,
            "decisiones": decisiones}


def entorno():
    import ale_py
    import gymnasium as gym
    gym.register_envs(ale_py)
    return gym.make("ALE/Tetris-v5", frameskip=1, repeat_action_probability=0.0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ale", description=__doc__.splitlines()[0])
    ap.add_argument("--url")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--partidas", type=int, default=20)
    ap.add_argument("--semilla-base", type=int, default=1)
    ap.add_argument("--max-piezas", type=int, default=500)
    ap.add_argument("--apertura", type=int, default=3)
    ap.add_argument("--decidir", choices=DECIDIR, default="argmax")
    ap.add_argument("--agentes", nargs="*")
    ap.add_argument("--video", type=int, help="semilla de la que se guardan fotogramas (uno de cada 2) y traza por agente")
    ap.add_argument("--video-piezas", type=int, default=60, help="tope de piezas de la partida con vídeo")
    a = ap.parse_args(argv)
    if a.url:
        try:
            api.salud(a.url)
        except api.ErrorRed as e:
            print(f"ale: {a.url} no responde a /healthz: {e}", file=sys.stderr)
            return 2
    todos = {"aleatorio": lambda s: AgenteAleatorio(s), "maestro": lambda s: AgenteMaestro("maestro")}
    if a.url:
        todos["chispa"] = lambda s: AgenteChispa(a.url, "chispa", decidir=a.decidir)
    semillas = list(range(a.semilla_base, a.semilla_base + a.partidas))
    os.makedirs(a.salida, exist_ok=True)
    env = entorno()
    out = {}
    for nombre, mk in todos.items():
        if a.agentes and nombre not in a.agentes:
            continue
        ps = []
        for s in semillas:
            t0 = time.time()
            ps.append(jugar_ale(env, s, mk(s), a.max_piezas, a.apertura))
            print(nombre, s, {k: v for k, v in ps[-1].items() if k != "decisiones"}, f"{time.time() - t0:.1f} s", flush=True)
        out[nombre] = {"resumen": E.resumen(ps) | {"fieles": sum(p["fieles"] for p in ps), "piezas": sum(p["piezas"] for p in ps),
                                                    "fallos_control": sum(p["fallos_control"] for p in ps)},
                       "por_partida": [{k: v for k, v in p.items() if k != "decisiones"} for p in ps]}
        if a.video is not None:
            grabar(env, a.video, mk(a.video), min(a.max_piezas, a.video_piezas), a.apertura, os.path.join(a.salida, f"video-{nombre}"))
    r = {"entorno": "ALE/Tetris-v5 frameskip=1 sticky=0", "decidir": a.decidir, "url": a.url, "semillas": semillas,
         "max_piezas": a.max_piezas, "apertura": a.apertura, "agentes": out}
    escribir_json(os.path.join(a.salida, "evaluacion.json"), r)
    md = E.markdown(r).replace("Tetris ALE (simulador)", "Tetris ALE (emulador, ALE/Tetris-v5)", 1)
    md += ("\nControlador: " + "; ".join(f"{n}: {x['resumen']['fieles']}/{x['resumen']['piezas']} piezas asentadas como predijo "
                                       f"el simulador, {x['resumen']['fallos_control']} fallos" for n, x in out.items())
           + f". Las {a.apertura} primeras piezas de cada semilla son al azar (las mismas para todos): el cartucho repite la secuencia.\n")
    with open(os.path.join(a.salida, "evaluacion.md"), "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    return 0


def grabar(env, semilla: int, agente, max_piezas: int, apertura: int, prefijo: str) -> None:
    """Fotogramas (uno de cada 2, uint8 210×160×3, .npz) y traza JSONL (una línea por pieza) para `renderizar`."""
    import numpy as np
    fotos, traza = [], []

    def al_paso(obs, a):
        if al_paso.k % 2 == 0:
            fotos.append(obs.copy())
        al_paso.k += 1
    al_paso.k = 0

    def al_decidir(fot, j, d, col, ef):
        fila = {"fotograma": fot, "foto": len(fotos), "pieza": j.pieza, "giro": col.giro, "col": col.col, "lineas": ef.lineas}
        if d is not None:
            fila.update({"opciones": d.opciones, "id_elegida": d.id_elegida, "decidio": d.decidio, "coincide": d.coincide,
                         "ms_cliente": d.ms_cliente, "probs": ((d.respuesta or {}).get("colocacion") or {}).get("probs")})
        traza.append(fila)
    r = jugar_ale(env, semilla, agente, max_piezas, apertura, al_decidir, al_paso)
    np.savez_compressed(prefijo + ".npz", fotos=np.array(fotos))
    with open(prefijo + ".jsonl", "w", encoding="utf-8") as f:
        for t in traza:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
        f.write(json.dumps({"fin": {k: v for k, v in r.items() if k != "decisiones"}}, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
