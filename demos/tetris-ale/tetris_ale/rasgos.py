"""Rasgos de una colocación (Dellacherie / El-Tetris), calculados sobre el tablero resultante, ya con las líneas borradas.

- altura_aterrizaje: altura (fila 1 = suelo) del centro de la pieza al caer, antes de borrar: (fila mínima + fila máxima)/2 + 1.
- lineas, celdas_erosionadas: líneas borradas y lineas × celdas de la pieza en ellas.
- transiciones_fila: cambios lleno/vacío por fila, con las paredes llenas, solo en las filas bajo la celda más alta.
- transiciones_columna: cambios por columna con el suelo lleno y el techo vacío (una columna vacía cuenta 1).
- huecos: celdas vacías con alguna llena encima; delta_huecos: huecos después − antes.
- pozos: pozos acumulados; un pozo de profundidad d suma 1 + 2 + … + d (las paredes cuentan como altas).
- altura_total (agregada), altura_max, irregularidad (bumpiness: Σ|h[i] − h[i+1]|)."""
from __future__ import annotations

from typing import Dict, List, Tuple

from .motor import ALTO, ANCHO, Colocacion, Efecto, aplicar

LLENA = (1 << ANCHO) - 1


def alturas(t) -> List[int]:
    h = [0] * ANCHO
    for f in range(ALTO - 1, -1, -1):
        fila = t[f]
        if not fila:
            continue
        for c in range(ANCHO):
            if not h[c] and fila >> c & 1:
                h[c] = f + 1
    return h


def contar_huecos(t) -> int:
    n, h = 0, alturas(t)
    for c in range(ANCHO):
        n += sum(1 for f in range(h[c]) if not t[f] >> c & 1)
    return n


def transiciones_fila(t) -> int:
    n = 0
    for f in range(max(alturas(t))):
        # con paredes llenas a ambos lados: bits de 0..ANCHO+1, la pared en los extremos
        fila = 1 | (t[f] << 1) | (1 << (ANCHO + 1))
        n += bin(fila ^ (fila >> 1)).count("1") - 1  # el bit superior de x ^ (x >> 1) no es una transición
    return n


def transiciones_columna(t) -> int:
    n = 0
    for c in range(ANCHO):
        previo = True  # suelo
        for f in range(ALTO):
            celda = bool(t[f] >> c & 1)
            n += celda != previo
            previo = celda
        n += previo is True  # techo vacío
    return n


def pozos(t) -> int:
    h, n = alturas(t), 0
    for c in range(ANCHO):
        izq = h[c - 1] if c > 0 else ALTO + 1
        der = h[c + 1] if c < ANCHO - 1 else ALTO + 1
        d = min(izq, der) - h[c]
        if d > 0:
            n += d * (d + 1) // 2
    return n


def irregularidad(h: List[int]) -> int:
    return sum(abs(a - b) for a, b in zip(h, h[1:]))


def altura_aterrizaje(col: Colocacion) -> float:
    fs = [f for f, _ in col.celdas]
    return (min(fs) + max(fs)) / 2 + 1


def rasgos(tablero, col: Colocacion, ef: Efecto = None) -> Dict[str, float]:
    ef = ef or aplicar(tablero, col)
    t = ef.tablero
    h = alturas(t)
    huecos = contar_huecos(t)
    return {
        "altura_aterrizaje": altura_aterrizaje(col),
        "lineas": ef.lineas,
        "celdas_erosionadas": ef.celdas_erosionadas,
        "transiciones_fila": transiciones_fila(t),
        "transiciones_columna": transiciones_columna(t),
        "huecos": huecos,
        "delta_huecos": huecos - contar_huecos(tablero),
        "pozos": pozos(t),
        "altura_total": sum(h),
        "altura_max": max(h),
        "irregularidad": irregularidad(h),
        "terminado": ef.terminado,
    }
