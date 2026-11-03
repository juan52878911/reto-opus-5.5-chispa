"""Agentes con interfaz común `decidir(juego) -> Decision` y el bucle de una partida. Todos pasan por el veto de seguridad."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import api, maestro as M, opciones as O
from .motor import Colocacion, Juego

DECIDIR = ("tau", "argmax")
CHISPA_TAU, CHISPA_BAJO_TAU, ESCUDO = "chispa_tau", "chispa_bajo_tau", "escudo"


@dataclass
class Decision:
    col: Colocacion
    id_elegida: Optional[str] = None
    coincide: Optional[bool] = None      # ¿la jugada final es la del maestro?
    decidio: str = ""                    # chispa_tau | chispa_bajo_tau | escudo (solo Chispa)
    escudo: bool = False                 # el maestro decidió porque Chispa escaló / no opinó / falló la red
    motivo_escudo: str = ""
    opino: bool = False                  # Chispa contestó sin escalar
    ms_cliente: Optional[float] = None
    ms_servidor: Optional[float] = None
    forzada: bool = False                # una sola colocación posible
    estado: str = ""
    opciones: List[dict] = field(default_factory=list)
    respuesta: Dict[str, dict] = field(default_factory=dict)


def _mejor(juego: Juego, pesos=M.PESOS_DELLACHERIE):
    rank = M.ranking(juego.tablero, juego.colocaciones(), pesos)
    return rank, rank[0][0]


def _misma(a: Colocacion, b: Colocacion) -> bool:
    return (a.giro, a.col) == (b.giro, b.col)


class AgenteAleatorio:
    nombre = "aleatorio"

    def __init__(self, semilla: int):
        self.rng = random.Random(semilla * 7919 + 1)

    def decidir(self, juego: Juego) -> Decision:
        t0 = time.perf_counter()
        rank, mejor = _mejor(juego)
        col = rank[self.rng.randrange(len(rank))][0]  # colocación legal al azar entre las que pasan el veto
        return Decision(col, coincide=_misma(col, mejor), ms_cliente=(time.perf_counter() - t0) * 1000)


class AgenteMaestro:
    def __init__(self, nombre: str = "maestro", pesos=M.PESOS_DELLACHERIE):
        self.nombre, self.pesos = nombre, pesos

    def decidir(self, juego: Juego) -> Decision:
        t0 = time.perf_counter()
        _, mejor = _mejor(juego, self.pesos)
        return Decision(mejor, coincide=True, ms_cliente=(time.perf_counter() - t0) * 1000)


def argmax_probs(probs, ids: List[str]) -> Optional[str]:
    """Id de mayor probabilidad entre `ids`; None si `probs` falta o es inválida. Empate: el primero de `ids`."""
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
    """Una petición por turno (la pregunta `choice` con las opciones autodescriptivas, barajadas con la semilla de la partida).
    - «tau» (por defecto): si Chispa escala, no opina o falla la red, juega el maestro y se cuenta un escudo.
    - «argmax»: con `probs` válidas se juega su argmax aunque escale (`chispa_bajo_tau`); sin ellas o sin red, el maestro."""

    def __init__(self, url: str, nombre: str = "chispa", timeout: float = 10.0, decidir: str = "tau"):
        if decidir not in DECIDIR:
            raise ValueError(f"decidir debe ser uno de {DECIDIR}, no {decidir!r}")
        self.url, self.nombre, self.timeout, self.modo = url, nombre, timeout, decidir
        self.rng = random.Random(0)

    def preparar(self, semilla: int) -> None:
        self.rng = random.Random(semilla * 1000003 + 17)

    def decidir(self, juego: Juego) -> Decision:
        rank, mejor = _mejor(juego)
        if len(rank) < 2:
            return Decision(mejor, coincide=True, forzada=True)
        ops = O.construir(juego.tablero, [e[0] for e in rank], self.rng)
        cuerpo = O.peticion(O.texto_estado(juego.tablero, juego.pieza, juego.siguiente), ops)
        info = [{"id": o.id, "descripcion": o.descripcion, "puesto": o.puesto, "giro": o.col.giro, "col": o.col.col} for o in ops]
        d = Decision(mejor, estado=cuerpo["state"], opciones=info)
        try:
            res, ms = api.decidir(self.url, cuerpo, self.timeout)
        except api.ErrorRed as e:
            d.escudo, d.decidio, d.motivo_escudo, d.coincide, d.respuesta = True, ESCUDO, "error_red", True, {"error": str(e)}
            return d
        ch = res.get(O.ID_COLOCACION) or {}
        d.ms_cliente, d.ms_servidor, d.respuesta = ms, float(ch.get("ms") or 0), res
        ids = [o.id for o in ops]
        resp = ch.get("answer")
        if not ch.get("escalate") and resp in ids:
            d.opino, d.decidio, d.id_elegida = True, CHISPA_TAU, resp
        else:
            razon = ch.get("escalate_reason") or ("escalar" if ch.get("escalate") else "sin_respuesta_valida")
            alt = argmax_probs(ch.get("probs"), ids) if self.modo == "argmax" else None
            if alt is None:
                d.escudo, d.decidio, d.motivo_escudo, d.coincide = True, ESCUDO, razon, True
                return d
            d.decidio, d.id_elegida = CHISPA_BAJO_TAU, alt
        op = next(o for o in ops if o.id == d.id_elegida)
        d.col, d.coincide = op.col, op.puesto == 1
        return d


def jugar_partida(semilla: int, agente, max_piezas: int, al_decidir=None) -> dict:
    """Juega hasta game over o `max_piezas`. `al_decidir(juego_antes, decision, efecto, juego)` registra la traza."""
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
    return {"semilla": semilla, "piezas": j.piezas_colocadas, "lineas": j.lineas_borradas,
            "game_over": j.terminado, "decisiones": decisiones}
