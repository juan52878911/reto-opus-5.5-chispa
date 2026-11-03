"""Texto del estado que viaja en `state` y descripciones de las opciones. Es el mismo para todos los agentes."""
from __future__ import annotations

from typing import Dict, List, Tuple

from .analisis import analizar
from .motor import DIRS, GIROS, LADO, MAX_PASOS, NOMBRE_DIR, Juego

GIRO_TXT = {"izquierda": "girar a la izquierda", "recto": "seguir recto", "derecha": "girar a la derecha"}


def plural(n: int, uno: str, otros: str) -> str:
    return f"{n} {uno if n == 1 else otros}"


def casillas(n: int) -> str:
    return plural(n, "casilla", "casillas")


def posicion_comida(juego_cuerpo, d: int, comida) -> str:
    """Dónde queda la comida respecto a la cabeza y hacia dónde mira, en palabras y con distancias."""
    if comida is None:
        return "No queda comida."
    df, dc = comida[0] - juego_cuerpo[0][0], comida[1] - juego_cuerpo[0][1]
    adelante = df * DIRS[d][0] + dc * DIRS[d][1]
    derecha = df * DIRS[(d + 1) % 4][0] + dc * DIRS[(d + 1) % 4][1]
    partes = []
    if adelante:
        partes.append(f"{casillas(abs(adelante))} {'delante' if adelante > 0 else 'detrás'}")
    if derecha:
        partes.append(f"{casillas(abs(derecha))} a la {'derecha' if derecha > 0 else 'izquierda'}")
    return f"La chispa queda a {' y '.join(partes)} (distancia {abs(df) + abs(dc)})."


def descripcion(info: dict, longitud: int) -> str:
    """Descripción en español de una opción (la usan el estado y la petición)."""
    g = GIRO_TXT[info["giro"]]
    if info["choque"]:
        return f"{g}: choca enseguida contra {'el muro' if info['choque'] == 'muro' else 'su cuerpo'}"
    txt = f"{g}: {casillas(info['libres'])} libres antes de chocar"
    if info["come"]:
        txt += ", se come la chispa"
    elif info["dist_comida"] is not None:
        txt += f", la chispa queda a {casillas(info['dist_comida'])} por camino libre"
    else:
        txt += ", sin camino a la chispa"
    if info["cerrada"]:
        txt += f", la mete en una zona cerrada pequeña (alcanza {casillas(info['area'])})"
    return txt


def opciones(juego: Juego) -> List[Tuple[str, str]]:
    a = analizar(juego.cuerpo, juego.dir, juego.comida)
    return [(g, descripcion(a[g], juego.longitud)) for g in GIROS]


def texto_estado(juego: Juego) -> str:
    a = analizar(juego.cuerpo, juego.dir, juego.comida)
    l = [f"Chispa: Serpiente, rejilla de {LADO}x{LADO}. Paso {juego.pasos} de {MAX_PASOS}.",
         f"Longitud {juego.longitud}, comidas {juego.comidas}. La serpiente mira {NOMBRE_DIR[juego.dir]}.",
         posicion_comida(juego.cuerpo, juego.dir, juego.comida),
         "Casillas libres antes de chocar: " + ", ".join(f"{g} {a[g]['libres']}" for g in GIROS) + ".",
         "Zona cerrada pequeña: " + ", ".join(f"{g} {'sí' if a[g]['cerrada'] and not a[g]['choque'] else 'no'}" for g in GIROS) + "."]
    return "\n".join(l)
