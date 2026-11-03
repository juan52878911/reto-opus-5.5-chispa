"""Simulador de planificación: tablero de 10 × 22 (el de ALE/Tetris-v5), 7 tetrominós, colocaciones con caída directa. Solo biblioteca estándar.

Tablero: tupla de `ALTO` enteros, uno por fila, con la fila 0 ABAJO; el bit `c` de una fila es la columna `c` (0 = izquierda).
Una colocación es (giro, columna): `giro` indexa los giros DISTINTOS de la pieza (O 1, I/S/Z 2, T/L/J 4) y `columna` es la
columna de la izquierda de la caja de la pieza. El giro 0 es la forma de reposo y cada giro siguiente es un cuarto de vuelta
en sentido horario, para poder mapearlo luego a los giros de Atari."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

ANCHO, ALTO = 10, 22  # ALE/Tetris-v5: 22 filas (mapa de la RAM en ale_juego.py)
ZONA_APARICION = 2  # una pieza que queda con alguna celda en las dos filas de arriba termina la partida
PIEZAS = "OISZTLJ"

# Forma de reposo como celdas (fila, col) con la fila 0 ABAJO, dentro de su caja.
_BASE: Dict[str, List[Tuple[int, int]]] = {
    "O": [(0, 0), (0, 1), (1, 0), (1, 1)],
    "I": [(0, 0), (0, 1), (0, 2), (0, 3)],
    "S": [(0, 0), (0, 1), (1, 1), (1, 2)],
    "Z": [(1, 0), (1, 1), (0, 1), (0, 2)],
    "T": [(0, 0), (0, 1), (0, 2), (1, 1)],
    "L": [(0, 0), (0, 1), (0, 2), (1, 2)],
    "J": [(0, 0), (0, 1), (0, 2), (1, 0)],
}


def _normalizar(celdas) -> Tuple[Tuple[int, int], ...]:
    f0 = min(f for f, _ in celdas)
    c0 = min(c for _, c in celdas)
    return tuple(sorted((f - f0, c - c0) for f, c in celdas))


def _girar_horario(celdas) -> Tuple[Tuple[int, int], ...]:
    # (fila, col) con fila hacia arriba: un cuarto de vuelta horario lleva (f, c) a (-c, f)
    return _normalizar([(-c, f) for f, c in celdas])


def _giros(pieza: str) -> List[Tuple[Tuple[int, int], ...]]:
    forma, vistos = _normalizar(_BASE[pieza]), []
    for _ in range(4):
        if forma not in vistos:
            vistos.append(forma)
        forma = _girar_horario(forma)
    return vistos


GIROS: Dict[str, List[Tuple[Tuple[int, int], ...]]] = {p: _giros(p) for p in PIEZAS}
TABLERO_VACIO: Tuple[int, ...] = (0,) * ALTO


@dataclass(frozen=True)
class Colocacion:
    pieza: str
    giro: int
    col: int
    celdas: Tuple[Tuple[int, int], ...]  # celdas absolutas (fila, col) donde aterriza la pieza


@dataclass(frozen=True)
class Efecto:
    tablero: Tuple[int, ...]   # tablero resultante, con las líneas ya borradas
    lineas: int
    celdas_erosionadas: int    # lineas × celdas de la pieza que estaban en líneas borradas (Dellacherie)
    terminado: bool


def tablero_desde_texto(filas: List[str]) -> Tuple[int, ...]:
    """Para tests: lista de cadenas de ARRIBA a ABAJO ('#' lleno, '.' vacío); las filas que faltan arriba quedan vacías."""
    abajo = []
    for s in reversed(filas):
        if len(s) != ANCHO:
            raise ValueError(f"fila de {len(s)} columnas, se esperaban {ANCHO}")
        abajo.append(sum(1 << c for c, ch in enumerate(s) if ch == "#"))
    if len(abajo) > ALTO:
        raise ValueError("más filas que ALTO")
    return tuple(abajo + [0] * (ALTO - len(abajo)))


def _aterrizar(tablero, forma, col: int) -> Optional[int]:
    """Fila de la caja donde aterriza la pieza al caer en línea recta desde arriba, o None si no cabe en la aparición."""
    alto = max(f for f, _ in forma) + 1
    masks = [(f, 1 << (c + col)) for f, c in forma]

    def choca(base):
        return any(base + f >= ALTO or tablero[base + f] & m for f, m in masks)

    base = ALTO - alto
    if choca(base):
        return None
    while base > 0 and not choca(base - 1):
        base -= 1
    return base


def colocaciones(tablero, pieza: str) -> List[Colocacion]:
    """Todas las (giro, columna) legales con caída directa, ordenadas por (giro, columna)."""
    out = []
    for g, forma in enumerate(GIROS[pieza]):
        ancho = max(c for _, c in forma) + 1
        for col in range(ANCHO - ancho + 1):
            base = _aterrizar(tablero, forma, col)
            if base is not None:
                out.append(Colocacion(pieza, g, col, tuple((base + f, col + c) for f, c in forma)))
    return out


def aplicar(tablero, col: Colocacion) -> Efecto:
    """Tablero nuevo (sin mutar el original), líneas borradas y si la partida termina."""
    filas = list(tablero)
    for f, c in col.celdas:
        filas[f] |= 1 << c
    llenas = {f for f, _ in col.celdas if filas[f] == (1 << ANCHO) - 1}
    en_lineas = sum(1 for f, _ in col.celdas if f in llenas)
    if llenas:
        filas = [r for i, r in enumerate(filas) if i not in llenas]
        filas += [0] * (ALTO - len(filas))
    terminado = any(filas[ALTO - 1 - i] for i in range(ZONA_APARICION))
    return Efecto(tuple(filas), len(llenas), len(llenas) * en_lineas, terminado)


class Juego:
    """Partida: secuencia de piezas uniforme y determinista por semilla (`pieza` actual y `siguiente`)."""

    def __init__(self, semilla: int, tablero=TABLERO_VACIO):
        self._rng = random.Random(semilla)
        self.tablero = tuple(tablero)
        self.pieza = self._rng.choice(PIEZAS)
        self.siguiente = self._rng.choice(PIEZAS)
        self.piezas_colocadas = 0
        self.lineas_borradas = 0
        self.terminado = False

    def colocaciones(self) -> List[Colocacion]:
        return colocaciones(self.tablero, self.pieza)

    def jugar(self, col: Colocacion) -> Efecto:
        if self.terminado:
            raise ValueError("la partida ya terminó")
        if col.pieza != self.pieza:
            raise ValueError(f"colocación de {col.pieza} con la pieza {self.pieza}")
        ef = aplicar(self.tablero, col)
        self.tablero = ef.tablero
        self.piezas_colocadas += 1
        self.lineas_borradas += ef.lineas
        self.pieza, self.siguiente = self.siguiente, self._rng.choice(PIEZAS)
        self.terminado = ef.terminado or not self.colocaciones()
        return ef
