"""Agentes de referencia: aleatorio y profesor heurístico. Solo biblioteca estándar."""
from __future__ import annotations

import random
from typing import List, Tuple

from .motor import ALTO, Colocacion, Efecto, Juego, alturas, aplicar, huecos

# Pesos FIJOS del profesor (puntuación = suma ponderada del tablero resultante; mayor es mejor).
PESOS = {
    "filas": 8.0,            # por fila limpiada
    "celdas_columna": 0.4,   # por celda borrada por la regla de chispa
    "huecos": -6.0,          # por hueco (celda vacía con algo encima)
    "altura_max": -1.0,      # altura de la torre más alta
    "altura_total": -0.35,   # suma de alturas
    "rugosidad": -0.8,       # suma de |h[i] - h[i+1]|
}


def rugosidad(h: List[int]) -> int:
    return sum(abs(a - b) for a, b in zip(h, h[1:]))


def evaluar(t, col: Colocacion) -> Tuple[float, dict]:
    ef = aplicar(t, col)
    return puntuar(ef)


def puntuar(ef: Efecto) -> Tuple[float, dict]:
    h = alturas(ef.tablero)
    m = {"filas": ef.filas, "celdas_columna": ef.celdas_columna, "huecos": huecos(ef.tablero),
         "altura_max": max(h), "altura_total": sum(h), "rugosidad": rugosidad(h),
         "columnas_borradas": len(ef.columnas)}
    return sum(PESOS[k] * m[k] for k in PESOS), m


def ranking(juego: Juego) -> List[Tuple[Colocacion, float, dict]]:
    """Colocaciones ordenadas de mejor a peor para el profesor (desempate: giro y columna menores)."""
    r = [(c, *evaluar(juego.tablero, c)) for c in juego.colocaciones()]
    r.sort(key=lambda x: (-x[1], x[0].rot, x[0].col))
    return r


def profesor(juego: Juego) -> Colocacion:
    return ranking(juego)[0][0]


def aleatorio(juego: Juego, rng: random.Random) -> Colocacion:
    cs = juego.colocaciones()
    return cs[rng.randrange(len(cs))]


def descripcion(col: Colocacion, m: dict) -> str:
    f = m["filas"]
    txt = f"limpia {f} fila{'s' if f != 1 else ''}"
    if m["columnas_borradas"]:
        txt += f", borra {m['columnas_borradas']} columna{'s' if m['columnas_borradas'] != 1 else ''} por chispa"
    h = m["huecos"]
    return f"{txt}, deja {h} hueco{'s' if h != 1 else ''}, altura máxima {m['altura_max']}"


def puede_completar_fila(juego: Juego) -> bool:
    return any(aplicar(juego.tablero, c).filas > 0 for c in juego.colocaciones())


def riesgo_derivado(t) -> int:
    """Riesgo 1–5 de referencia, por la altura máxima antes de colocar: ≤4→1, 5–7→2, 8–10→3, 11–12→4, ≥13→5."""
    h = max(alturas(t))
    return 1 if h <= 4 else 2 if h <= 7 else 3 if h <= 10 else 4 if h <= 12 else 5
