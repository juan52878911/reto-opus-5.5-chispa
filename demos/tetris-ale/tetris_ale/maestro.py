"""Maestro heurístico (Dellacherie por defecto, El-Tetris como alternativa) y veto de seguridad. Mayor valor = mejor."""
from __future__ import annotations

from typing import Dict, List, Tuple

from .motor import Colocacion
from .rasgos import rasgos

# Dellacherie (2003), tal como lo recoge C. Fahey, «Tetris AI – The (Near) Perfect Bot» (colinfahey.com) y Thiery & Scherrer
# (2009), «Building Controllers for Tetris», ICGA Journal 32(1): puntuación = −altura_aterrizaje + celdas_erosionadas
# − transiciones_fila − transiciones_columna − 4·huecos − pozos (todos los pesos ±1 salvo huecos).
PESOS_DELLACHERIE: Dict[str, float] = {
    "altura_aterrizaje": -1.0, "celdas_erosionadas": 1.0, "transiciones_fila": -1.0,
    "transiciones_columna": -1.0, "huecos": -4.0, "pozos": -1.0,
}
# El-Tetris (Yiyuan Lee, 2013, «El-Tetris – An Improvement on Pierre Dellacherie's Algorithm», imake.ninja/el-tetris),
# pesos hallados por enjambre de partículas; cuatro rasgos.
PESOS_EL_TETRIS: Dict[str, float] = {
    "altura_total": -4.500158825082766, "lineas": 3.4181268101392694,
    "huecos": -7.899265427351652, "irregularidad": -3.3855972247263626,
}
MAESTROS = {"dellacherie": PESOS_DELLACHERIE, "el-tetris": PESOS_EL_TETRIS}


def valor(r: Dict[str, float], pesos: Dict[str, float] = PESOS_DELLACHERIE) -> float:
    return sum(w * r[k] for k, w in pesos.items())


def evaluadas(tablero, cols: List[Colocacion], pesos=PESOS_DELLACHERIE) -> List[Tuple[Colocacion, Dict[str, float], float]]:
    """(colocación, rasgos, valor) de cada una."""
    out = []
    for c in cols:
        r = rasgos(tablero, c)
        out.append((c, r, valor(r, pesos)))
    return out


def veto(evs):
    """Veto de seguridad: descarta toda colocación que termina la partida si hay alguna que no. Lo usan todos los agentes."""
    vivas = [e for e in evs if not e[1]["terminado"]]
    return vivas or list(evs)


def ranking(tablero, cols: List[Colocacion], pesos=PESOS_DELLACHERIE):
    """Evaluadas tras el veto, de mejor a peor. Desempate determinista: menor giro y luego menor columna."""
    return sorted(veto(evaluadas(tablero, cols, pesos)), key=lambda e: (-e[2], e[0].giro, e[0].col))


def maestro(tablero, cols: List[Colocacion], pesos=PESOS_DELLACHERIE) -> Colocacion:
    return ranking(tablero, cols, pesos)[0][0]
