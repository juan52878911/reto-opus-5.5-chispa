"""Agentes con interfaz común `decidir(juego) -> Decision` y el bucle de una partida."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import api
from .agentes import aleatorio, opciones_vivas, profesor
from .estado import opciones, texto_estado
from .motor import GIROS, Juego

DECIDIR = ("tau", "argmax")
CHISPA_TAU, CHISPA_BAJO_TAU, ESCUDO = "chispa_tau", "chispa_bajo_tau", "escudo"


@dataclass
class Decision:
    giro: str
    coincide: Optional[bool] = None       # ¿la jugada final es la del profesor?
    decidio: str = ""                     # chispa_tau | chispa_bajo_tau | escudo (solo Chispa)
    escudo: bool = False
    motivo_escudo: str = ""
    opino: bool = False                   # Chispa contestó el choice sin escalar
    ms_cliente: Optional[float] = None    # latencia de la decisión (HTTP en Chispa; cálculo local en el resto)
    ms_servidor: Optional[float] = None
    forzada: bool = False                 # a lo sumo una opción no choca: no hay decisión que medir
    confianza: Optional[float] = None     # probabilidad de la opción jugada, si el servidor da `probs`
    estado: str = ""
    opciones: List[dict] = field(default_factory=list)
    respuesta: Dict[str, dict] = field(default_factory=dict)


class AgenteAleatorio:
    nombre = "aleatorio"

    def __init__(self, semilla: int):
        self.rng = random.Random(semilla * 7919 + 1)

    def decidir(self, juego: Juego) -> Decision:
        t0 = time.perf_counter()
        g = aleatorio(juego, self.rng)
        ms = (time.perf_counter() - t0) * 1000
        return Decision(g, coincide=g == profesor(juego), ms_cliente=ms)


class AgenteProfesor:
    nombre = "profesor"

    def decidir(self, juego: Juego) -> Decision:
        t0 = time.perf_counter()
        g = profesor(juego)
        return Decision(g, coincide=True, ms_cliente=(time.perf_counter() - t0) * 1000)


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
    """Una petición por turno (choice de 3 opciones). `decidir`:
    - «tau» (por defecto): si Chispa escala, no opina o falla la red, juega el profesor (escudo).
    - «argmax»: si el choice trae `probs` válidas se juega su argmax aunque escale (`chispa_bajo_tau`); solo sin
      `probs` (o inválidas) o con la red caída juega el profesor (escudo)."""

    def __init__(self, url: str, nombre: str = "chispa_zero_shot", timeout: float = 10.0, decidir: str = "tau"):
        if decidir not in DECIDIR:
            raise ValueError(f"decidir debe ser uno de {DECIDIR}, no {decidir!r}")
        self.url, self.nombre, self.timeout, self.modo = url, nombre, timeout, decidir

    def decidir(self, juego: Juego) -> Decision:
        mejor = profesor(juego)
        if opciones_vivas(juego) < 2:
            return Decision(mejor, coincide=True, forzada=True)
        ops = opciones(juego)
        estado = texto_estado(juego)
        d = Decision(mejor, estado=estado, opciones=[{"id": i, "descripcion": t} for i, t in ops])
        try:
            res, ms = api.decidir(self.url, api.construir_peticion(estado, ops), self.timeout)
        except api.ErrorRed as e:
            d.escudo, d.decidio, d.motivo_escudo, d.coincide = True, ESCUDO, "error_red", True
            d.respuesta = {"error": str(e)}
            return d
        ch = res.get(api.ID_GIRO) or {}
        d.ms_cliente, d.ms_servidor, d.respuesta = ms, float(ch.get("ms") or 0), ch
        resp = ch.get("answer")
        ids = list(GIROS)
        if not ch.get("escalate") and resp in ids:
            d.opino, d.decidio, d.giro = True, CHISPA_TAU, resp
        else:
            razon = ch.get("escalate_reason") or ("escalar" if ch.get("escalate") else "sin_respuesta_valida")
            alt = argmax_probs(ch.get("probs"), ids) if self.modo == "argmax" else None
            if alt is None:
                d.escudo, d.decidio, d.motivo_escudo, d.coincide = True, ESCUDO, razon, True
                return d
            d.decidio, d.giro = CHISPA_BAJO_TAU, alt
        p = (ch.get("probs") or {}).get(d.giro)
        d.confianza = float(p) if isinstance(p, (int, float)) and not isinstance(p, bool) else None
        d.coincide = d.giro == mejor
        return d


def jugar_partida(semilla: int, agente, al_decidir=None) -> dict:
    """Juega hasta que termina (choque, tope de 500 pasos o rejilla llena). `al_decidir(antes, decision, resultado, juego)`
    recibe (cuerpo, dir, comida) previos para grabar la traza."""
    j = Juego(semilla)
    decisiones: List[Decision] = []
    while not j.terminado:
        antes = (j.cuerpo, j.dir, j.comida)
        d = agente.decidir(j)
        r = j.paso(d.giro)
        decisiones.append(d)
        if al_decidir:
            al_decidir(antes, d, r, j)
    return {"semilla": semilla, "pasos": j.pasos, "comidas": j.comidas, "longitud": j.longitud, "fin": j.motivo,
            "decisiones": decisiones}
