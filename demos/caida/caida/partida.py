"""Agentes con interfaz común `decidir(juego) -> Decision` y el bucle de una partida."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import api
from .agentes import PESOS, aleatorio, descripcion, ranking
from .estado import texto_estado
from .motor import Colocacion, Juego


@dataclass
class Decision:
    col: Colocacion
    id_elegida: Optional[str] = None      # id del choice (solo agentes Chispa)
    coincide: Optional[bool] = None       # ¿la jugada final es la del profesor? (None si no aplica)
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


class AgenteChispa:
    """Una petición por turno con tres preguntas. Si Chispa escala, no opina en el choice o falla la red,
    juega el profesor y se cuenta una intervención del escudo."""

    def __init__(self, url: str, nombre: str = "chispa", timeout: float = 10.0):
        self.url, self.nombre, self.timeout = url, nombre, timeout

    def decidir(self, juego: Juego) -> Decision:
        rank = ranking(juego)
        mejor = rank[0][0]
        if len(rank) < 2:
            return Decision(mejor, coincide=True, forzada=True)
        top = rank[:api.K]
        opciones = [(str(i + 1), c, m) for i, (c, _, m) in enumerate(top)]
        estado = texto_estado(juego, opciones)
        cuerpo = api.construir_peticion(estado, [(i, descripcion(c, m)) for i, c, m in opciones])
        info = [{"id": i, "descripcion": descripcion(c, m), "rot": c.rot, "col": c.col,
                 "celdas": [list(x) for x in c.celdas]} for i, c, m in opciones]
        d = Decision(mejor, estado=estado, opciones=info)
        try:
            res, ms = api.decidir(self.url, cuerpo, self.timeout)
        except api.ErrorRed as e:
            d.escudo, d.motivo_escudo = True, "error_red"
            d.preguntas = {"error": str(e)}
            return d
        d.ms_cliente = ms
        d.ms_servidor = sum(float(r.get("ms") or 0) for r in res.values())
        d.preguntas = res
        ch = res.get(api.ID_COLOCACION) or {}
        resp = ch.get("answer")
        ids = {i for i, _, _ in opciones}
        if ch.get("escalate") or resp not in ids:
            d.escudo = True
            d.motivo_escudo = ch.get("escalate_reason") or ("escalar" if ch.get("escalate") else "sin_respuesta_valida")
            return d
        d.opino, d.id_elegida = True, resp
        d.col = next(c for i, c, _ in opciones if i == resp)
        d.coincide = resp == "1"
        return d


def jugar_partida(semilla: int, agente, max_piezas: int, al_decidir=None) -> dict:
    """Juega hasta game over o `max_piezas`. `al_decidir(juego_antes, decision, efecto, filas_antes)` registra la traza."""
    j = Juego(semilla)
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
