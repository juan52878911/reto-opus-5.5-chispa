"""Motor de «Chispa: Serpiente»: rejilla de 16×16, movimiento por giros relativos, determinista con semilla.

Coordenadas (fila, columna), fila 0 arriba. Direcciones en el sentido del reloj: 0 arriba, 1 derecha, 2 abajo, 3 izquierda.
Solo biblioteca estándar.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Tuple

LADO = 16
MAX_PASOS = 500
LONGITUD_INICIAL = 3
DIRS = ((-1, 0), (0, 1), (1, 0), (0, -1))
NOMBRE_DIR = ("arriba", "a la derecha", "abajo", "a la izquierda")
GIROS = ("izquierda", "recto", "derecha")
DELTA_GIRO = {"izquierda": 3, "recto": 0, "derecha": 1}

Celda = Tuple[int, int]


def en_rejilla(c: Celda) -> bool:
    return 0 <= c[0] < LADO and 0 <= c[1] < LADO


def nueva_dir(d: int, giro: str) -> int:
    return (d + DELTA_GIRO[giro]) % 4


def sumar(c: Celda, d: int) -> Celda:
    return c[0] + DIRS[d][0], c[1] + DIRS[d][1]


def mover(cuerpo: Sequence[Celda], d: int, comida: Optional[Celda]) -> Tuple[Tuple[Celda, ...], bool, str]:
    """Un paso hacia la dirección absoluta `d`. Devuelve (cuerpo nuevo, comió, choque).
    `choque` es "" o "muro" / "cuerpo"; con choque el cuerpo devuelto es el de antes. La cola libera su casilla
    salvo que la serpiente coma en ese paso (entonces crece)."""
    cabeza = sumar(cuerpo[0], d)
    if not en_rejilla(cabeza):
        return tuple(cuerpo), False, "muro"
    come = cabeza == comida
    ocupado = cuerpo if come else cuerpo[:-1]
    if cabeza in ocupado:
        return tuple(cuerpo), False, "cuerpo"
    nuevo = (cabeza,) + tuple(cuerpo)
    return (nuevo if come else nuevo[:-1]), come, ""


@dataclass
class Resultado:
    comio: bool
    choque: str


class Juego:
    def __init__(self, semilla: int):
        self.semilla = semilla
        self.rng = random.Random(semilla)
        mitad = LADO // 2
        self.cuerpo: Tuple[Celda, ...] = tuple((mitad, mitad - i) for i in range(LONGITUD_INICIAL))  # cabeza primero
        self.dir = 1
        self.pasos = 0
        self.comidas = 0
        self.terminado = False
        self.motivo = ""  # muro | cuerpo | tope | completa
        self.comida: Optional[Celda] = None
        self._poner_comida()

    @property
    def longitud(self) -> int:
        return len(self.cuerpo)

    def libres(self) -> List[Celda]:
        o = set(self.cuerpo)
        return [(f, c) for f in range(LADO) for c in range(LADO) if (f, c) not in o]

    def _poner_comida(self) -> None:
        libres = self.libres()
        self.comida = self.rng.choice(libres) if libres else None

    def paso(self, giro: str) -> Resultado:
        if self.terminado:
            raise ValueError("la partida ya terminó")
        d = nueva_dir(self.dir, giro)
        nuevo, come, choque = mover(self.cuerpo, d, self.comida)
        self.pasos += 1
        if choque:
            self.terminado, self.motivo = True, choque
            return Resultado(False, choque)
        self.cuerpo, self.dir = nuevo, d
        if come:
            self.comidas += 1
            self._poner_comida()
            if self.comida is None:
                self.terminado, self.motivo = True, "completa"
        if not self.terminado and self.pasos >= MAX_PASOS:
            self.terminado, self.motivo = True, "tope"
        return Resultado(come, "")


def a_texto(cuerpo: Sequence[Celda], comida: Optional[Celda]) -> List[str]:
    """Rejilla en texto: O cabeza, o cuerpo, * chispa, . vacío."""
    g = [["."] * LADO for _ in range(LADO)]
    for i, (f, c) in enumerate(cuerpo):
        g[f][c] = "O" if i == 0 else "o"
    if comida:
        g[comida[0]][comida[1]] = "*"
    return ["".join(r) for r in g]
