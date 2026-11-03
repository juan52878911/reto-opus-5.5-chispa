"""Análisis de las 3 opciones de giro desde una posición: lo comparten el texto de estado y el profesor."""
from __future__ import annotations

from collections import deque
from typing import Dict, Optional, Sequence, Set, Tuple

from .motor import DIRS, GIROS, Celda, en_rejilla, mover, nueva_dir, sumar


def vecinos(c: Celda):
    for d in DIRS:
        n = (c[0] + d[0], c[1] + d[1])
        if en_rejilla(n):
            yield n


def alcanzable(cabeza: Celda, bloqueadas: Set[Celda]) -> Dict[Celda, int]:
    """BFS desde la cabeza: {casilla: distancia} por casillas no bloqueadas (la cabeza cuenta con distancia 0)."""
    dist = {cabeza: 0}
    cola = deque([cabeza])
    while cola:
        c = cola.popleft()
        for n in vecinos(c):
            if n not in dist and n not in bloqueadas:
                dist[n] = dist[c] + 1
                cola.append(n)
    return dist


def libres_en_recta(cuerpo: Sequence[Celda], d: int) -> int:
    """Casillas libres seguidas desde la cabeza en la dirección absoluta `d` antes de chocar (muro o cuerpo; la cola
    cuenta como libre porque se aparta en el primer paso)."""
    ocupado = set(cuerpo[:-1])
    c, n = cuerpo[0], 0
    while True:
        c = sumar(c, d)
        if not en_rejilla(c) or c in ocupado:
            return n
        n += 1


def analizar(cuerpo: Sequence[Celda], d: int, comida: Optional[Celda]) -> Dict[str, dict]:
    """Por cada giro: choque ("" / muro / cuerpo), libres (casillas antes de chocar en esa dirección), come,
    area (casillas alcanzables tras el paso; la cola cuenta), cola (¿hay camino hasta la cola?), cerrada
    (area < longitud o sin camino a la cola), dist_comida (pasos desde la nueva cabeza; 0 si come; None si no hay camino)."""
    out: Dict[str, dict] = {}
    for g in GIROS:
        nd = nueva_dir(d, g)
        libres = libres_en_recta(cuerpo, nd)
        nuevo, come, choque = mover(cuerpo, nd, comida)
        info = {"giro": g, "dir": nd, "choque": choque, "libres": libres, "come": come,
                "area": 0, "cola": False, "cerrada": True, "dist_comida": None}
        if not choque:
            alc = alcanzable(nuevo[0], set(nuevo[:-1]))
            info["area"] = len(alc)
            info["cola"] = nuevo[-1] in alc
            info["cerrada"] = len(alc) < len(nuevo) or not info["cola"]
            info["dist_comida"] = 0 if come else (alc.get(comida) if comida else None)
        out[g] = info
    return out
