"""Agentes de referencia: aleatorio y profesor heurístico. Solo biblioteca estándar."""
from __future__ import annotations

import random
from typing import Dict, Optional, Sequence, Tuple

from .analisis import analizar
from .motor import GIROS, Celda, Juego

PREFERENCIA = ("recto", "izquierda", "derecha")  # desempates


def elegir(cuerpo: Sequence[Celda], d: int, comida: Optional[Celda]) -> Tuple[str, str]:
    """Profesor: (giro, razón). Razones: «comida» (BFS hacia la chispa por una opción segura), «espacio» (sin camino a
    la chispa: la opción con más espacio), «encierro» (todas encierran: la de más espacio), «sin_salida» (todas chocan)."""
    a = analizar(cuerpo, d, comida)
    vivas = [g for g in PREFERENCIA if not a[g]["choque"]]
    if not vivas:
        return "recto", "sin_salida"
    seguras = [g for g in vivas if not a[g]["cerrada"]]  # anti-encierro: hay camino a la cola y cabe la serpiente
    if not seguras:
        return max(vivas, key=lambda g: (a[g]["area"], -PREFERENCIA.index(g))), "encierro"
    con_camino = [g for g in seguras if a[g]["dist_comida"] is not None]
    if con_camino:
        return min(con_camino, key=lambda g: (a[g]["dist_comida"], -a[g]["area"], PREFERENCIA.index(g))), "comida"
    return max(seguras, key=lambda g: (a[g]["area"], -PREFERENCIA.index(g))), "espacio"


def profesor(juego: Juego) -> str:
    return elegir(juego.cuerpo, juego.dir, juego.comida)[0]


def opciones_vivas(juego: Juego) -> int:
    a = analizar(juego.cuerpo, juego.dir, juego.comida)
    return sum(1 for g in GIROS if not a[g]["choque"])


def aleatorio(juego: Juego, rng: random.Random) -> str:
    return GIROS[rng.randrange(len(GIROS))]
