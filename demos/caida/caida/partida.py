"""Agentes con interfaz común `decidir(juego) -> Decision` y el bucle de una partida."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import api
from .agentes import PESOS, aleatorio, descripcion, ranking
from .estado import peticiones_turno
from .motor import Colocacion, Juego


@dataclass
class Decision:
    col: Colocacion
    id_elegida: Optional[str] = None      # id del choice (solo agentes Chispa)
    coincide: Optional[bool] = None       # ¿la jugada final es la del profesor? (None si no aplica)
    decidio: str = ""                     # chispa_tau | chispa_bajo_tau | escudo (solo agentes Chispa)
    escudo: bool = False                  # el profesor decidió porque Chispa escaló / no opinó / falló
    motivo_escudo: str = ""
    opino: bool = False                   # Chispa contestó el choice sin escalar
    ms_cliente: Optional[float] = None    # latencia de la decisión (HTTP en Chispa; cálculo local en el resto)
    ms_servidor: Optional[float] = None
    forzada: bool = False                 # una sola colocación posible: no hay decisión
    estado: str = ""
    opciones: List[dict] = field(default_factory=list)
    preguntas: Dict[str, dict] = field(default_factory=dict)


class AgenteAleatorio:
    nombre = "aleatorio"

    def __init__(self, semilla: int):
        self.rng = random.Random(semilla * 7919 + 1)

    def decidir(self, juego: Juego) -> Decision:
        t0 = time.perf_counter()
        col = aleatorio(juego, self.rng)
        ms = (time.perf_counter() - t0) * 1000
        mejor = ranking(juego)[0][0]
        return Decision(col, coincide=(col.rot, col.col) == (mejor.rot, mejor.col), ms_cliente=ms)


class AgenteProfesor:
    nombre = "profesor"

    def decidir(self, juego: Juego) -> Decision:
        t0 = time.perf_counter()
        col = ranking(juego)[0][0]
        return Decision(col, coincide=True, ms_cliente=(time.perf_counter() - t0) * 1000)


DECIDIR = ("tau", "argmax")
# decidio
CHISPA_TAU, CHISPA_BAJO_TAU, ESCUDO = "chispa_tau", "chispa_bajo_tau", "escudo"


def argmax_probs(probs, ids: List[str]) -> Optional[str]:
    """Id de mayor probabilidad entre `ids`; None si `probs` falta o es inválida (no es un dict con un número finito
    ≥ 0 por cada id y suma > 0). Empate: el primero de `ids`."""
    if not isinstance(probs, dict) or not probs:
        return None
    vals = []
    for i in ids:
        v = probs.get(i)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            return None
        vals.append(float(v))
    if sum(vals) <= 0:
        return None
    return ids[vals.index(max(vals))]


class AgenteChispa:
    """Dos peticiones por turno (choice; score + noul). `decidir`:
    - «tau» (por defecto): si Chispa escala, no opina en el choice o falla la red, juega el profesor y se cuenta un escudo.
    - «argmax»: si el choice trae `probs` válidas se juega su argmax aunque escale (`chispa_bajo_tau`); solo sin `probs`
      (o inválidas) o con la red caída juega el profesor (escudo).
    Las opciones se ofrecen BARAJADAS con la semilla de la partida (`preparar`): la 1 ya no es la del profesor.
    La traza guarda el puesto del profesor de cada opción (`rank`)."""

    def __init__(self, url: str, nombre: str = "chispa", timeout: float = 10.0, decidir: str = "tau", barajar: bool = True):
        if decidir not in DECIDIR:
            raise ValueError(f"decidir debe ser uno de {DECIDIR}, no {decidir!r}")
        self.url, self.nombre, self.timeout, self.modo, self.barajar = url, nombre, timeout, decidir, barajar
        self.rng = random.Random(0)

    def preparar(self, semilla: int) -> None:
        self.rng = random.Random(semilla * 1000003 + 17)

    def decidir(self, juego: Juego) -> Decision:
        rank = ranking(juego)
        mejor = rank[0][0]
        if len(rank) < 2:
            return Decision(mejor, coincide=True, forzada=True)
        top = list(enumerate(rank[:api.K], 1))  # (puesto del profesor, (col, puntos, métricas))
        if self.barajar:
            self.rng.shuffle(top)
        opciones = [(str(pos + 1), c, m) for pos, (_, (c, _, m)) in enumerate(top)]
        puesto = {str(pos + 1): r for pos, (r, _) in enumerate(top)}
        bodies = peticiones_turno(juego, opciones)
        info = [{"id": i, "descripcion": descripcion(c, m), "rank": puesto[i], "rot": c.rot, "col": c.col,
                 "celdas": [list(x) for x in c.celdas]} for i, c, m in opciones]
        d = Decision(mejor, estado=bodies[0]["state"], opciones=info)
        res, ms, srv = {}, 0.0, 0.0
        try:
            for b in bodies:
                r, t = api.decidir(self.url, b, self.timeout)
                res.update(r)
                ms += t
                srv += sum(float(x.get("ms") or 0) for x in r.values())
        except api.ErrorRed as e:
            d.escudo, d.decidio, d.motivo_escudo, d.coincide = True, ESCUDO, "error_red", True
            d.preguntas = {"error": str(e)}
            return d
        d.ms_cliente, d.ms_servidor, d.preguntas = ms, srv, res
        ch = res.get(api.ID_COLOCACION) or {}
        resp = ch.get("answer")
        ids = [i for i, _, _ in opciones]
        if not ch.get("escalate") and resp in ids:
            d.opino, d.decidio, d.id_elegida = True, CHISPA_TAU, resp
        else:
            razon = ch.get("escalate_reason") or ("escalar" if ch.get("escalate") else "sin_respuesta_valida")
            alt = argmax_probs(ch.get("probs"), ids) if self.modo == "argmax" else None
            if alt is None:
                d.escudo, d.decidio, d.motivo_escudo, d.coincide = True, ESCUDO, razon, True
                return d
            d.decidio, d.id_elegida = CHISPA_BAJO_TAU, alt
        d.col = next(c for i, c, _ in opciones if i == d.id_elegida)
        d.coincide = puesto[d.id_elegida] == 1
        return d


def jugar_partida(semilla: int, agente, max_piezas: int, al_decidir=None) -> dict:
    """Juega hasta game over o `max_piezas`. `al_decidir(juego_antes, decision, efecto, filas_antes)` registra la traza."""
    j = Juego(semilla)
    if hasattr(agente, "preparar"):
        agente.preparar(semilla)
    decisiones: List[Decision] = []
    while not j.terminado and j.piezas_colocadas < max_piezas:
        antes = (j.tablero, j.pieza)
        d = agente.decidir(j)
        ef = j.jugar(d.col)
        decisiones.append(d)
        if al_decidir:
            al_decidir(antes, d, ef, j)
    return {"semilla": semilla, "piezas": j.piezas_colocadas, "filas": j.filas_limpiadas, "puntos": j.puntos,
            "game_over": j.terminado, "decisiones": decisiones}
