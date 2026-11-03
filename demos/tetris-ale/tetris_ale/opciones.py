"""Opciones autodescriptivas: una sola pregunta `choice` por pieza. La decisión la llevan los rasgos de cada opción."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import maestro as M
from .motor import Colocacion
from .rasgos import alturas, contar_huecos

K_MEJORES = 5
K_AZAR = 2
ID_COLOCACION = "colocacion"
PREGUNTA_COLOCACION = "¿Dónde coloco la pieza?"


@dataclass
class Opcion:
    id: str
    col: Colocacion
    rasgos: Dict[str, float]
    valor: float
    puesto: int          # puesto en el ranking del maestro (1 = su elegida)
    descripcion: str


def _n(x: int, singular: str, plural: str) -> str:
    return f"{x} {singular if x == 1 else plural}"


def descripcion(r: Dict[str, float]) -> str:
    """«limpia 1 línea, huecos +0, altura 7, irregularidad 4, pozos 2, aterriza a 3»."""
    n = int(r["lineas"])
    lim = f"limpia {_n(n, 'línea', 'líneas')}" if n else "no limpia líneas"
    d = int(r["delta_huecos"])
    al = r["altura_aterrizaje"]
    aterriza = str(int(al)) if al == int(al) else f"{al:.1f}".replace(".", ",")
    return (f"{lim}, huecos {'+' if d >= 0 else '-'}{abs(d)}, altura {int(r['altura_max'])}, "
            f"irregularidad {int(r['irregularidad'])}, pozos {int(r['pozos'])}, aterriza a {aterriza}")


def texto_estado(tablero, pieza: str, siguiente: Optional[str] = None) -> str:
    """Estado breve: pieza actual, siguiente si se conoce, altura y huecos del tablero."""
    s = f"Pieza {pieza}"
    if siguiente:
        s += f", siguiente {siguiente}"
    return f"{s}. Tablero: altura {max(alturas(tablero))}, huecos {contar_huecos(tablero)}."


def construir(tablero, cols: List[Colocacion], rng: random.Random, k: int = K_MEJORES, azar: int = K_AZAR,
              pesos=M.PESOS_DELLACHERIE) -> List[Opcion]:
    """Las `k` mejores según el maestro (tras el veto) más `azar` al azar del resto, barajadas, con ids "1"…"n".
    Si hay menos de k + azar candidatas se ofrecen todas."""
    rank = M.ranking(tablero, cols, pesos)
    elegidas = list(enumerate(rank[:k], 1))
    resto = list(enumerate(rank, 1))[k:]
    elegidas += sorted(rng.sample(resto, min(azar, len(resto))))
    rng.shuffle(elegidas)
    return [Opcion(str(i), c, r, v, puesto, descripcion(r)) for i, (puesto, (c, r, v)) in enumerate(elegidas, 1)]


def peticion(estado: str, opciones: List[Opcion]) -> dict:
    return {"state": estado,
            "questions": [{"id": ID_COLOCACION, "question": PREGUNTA_COLOCACION, "kind": "choice",
                           "options": [{"id": o.id, "description": o.descripcion} for o in opciones]}]}
