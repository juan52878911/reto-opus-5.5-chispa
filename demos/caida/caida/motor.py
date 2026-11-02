"""Motor determinista de «Chispa: Caída». Solo biblioteca estándar.

Tablero ANCHO×ALTO (9×15), fila 0 arriba. Celda: 0 vacía, 1 normal, 2 chispa.
La secuencia de piezas depende solo de la semilla (no de lo que juegue el agente).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

ANCHO = 9
ALTO = 15
VACIA, NORMAL, CHISPA = 0, 1, 2
PROB_CHISPA = 0.3  # probabilidad de que una pieza nueva lleve una celda chispa

# Piezas propias, como listas de (fila, columna). Las de 4 celdas NO tienen todas sus celdas unidas por lados
# (las formas clásicas de 4 celdas son todas las unidas por lados, así que estas no lo son).
PIEZAS: Dict[str, Tuple[Tuple[int, int], ...]] = {
    "domino": ((0, 0), (0, 1)),
    "diagonal": ((0, 0), (1, 1)),
    "recta3": ((0, 0), (0, 1), (0, 2)),
    "ele3": ((0, 0), (1, 0), (1, 1)),
    "pinza": ((0, 0), (0, 2), (1, 0), (1, 2)),    # dos dominós verticales con una columna libre en medio
    "punta": ((0, 0), (1, 0), (2, 0), (2, 2)),    # tres en vertical y una celda suelta a dos columnas
    "gancho": ((0, 0), (0, 1), (1, 3), (1, 4)),   # dos dominós horizontales que no se tocan por los lados
}
NOMBRES = tuple(PIEZAS)

Celdas = Tuple[Tuple[int, int, int], ...]  # (fila, col, tipo)


def normalizar(celdas: Sequence[Tuple[int, int, int]]) -> Celdas:
    f0 = min(r for r, _, _ in celdas)
    c0 = min(c for _, c, _ in celdas)
    return tuple(sorted((r - f0, c - c0, s) for r, c, s in celdas))


def girar(celdas: Celdas) -> Celdas:
    """Giro de 90° en sentido horario."""
    return normalizar([(c, -r, s) for r, c, s in celdas])


def rotaciones(celdas: Celdas) -> List[Celdas]:
    """Giros distintos (hasta 4) de la pieza, con la chispa incluida en la identidad."""
    out: List[Celdas] = []
    actual = normalizar(celdas)
    for _ in range(4):
        if actual not in out:
            out.append(actual)
        actual = girar(actual)
    return out


@dataclass(frozen=True)
class Pieza:
    nombre: str
    celdas: Celdas  # con tipo de celda (1 o 2)

    @property
    def tiene_chispa(self) -> bool:
        return any(s == CHISPA for _, _, s in self.celdas)


@dataclass(frozen=True)
class Colocacion:
    rot: int
    col: int
    fila: int  # fila donde queda la esquina superior izquierda de la caja de la pieza
    celdas: Celdas  # celdas absolutas en el tablero (fila, col, tipo)


@dataclass
class Efecto:
    """Resultado de colocar: tablero nuevo y estadísticas de la limpieza."""
    tablero: List[List[int]]
    filas: int
    celdas_columna: int  # celdas borradas por la regla de chispa en columnas fuera de las filas limpiadas
    columnas: Tuple[int, ...]
    puntos: int


def tablero_vacio() -> List[List[int]]:
    return [[VACIA] * ANCHO for _ in range(ALTO)]


def copiar(t: List[List[int]]) -> List[List[int]]:
    return [f[:] for f in t]


def _cabe(t, celdas: Celdas, df: int, dc: int) -> bool:
    for r, c, _ in celdas:
        rr, cc = r + df, c + dc
        if cc < 0 or cc >= ANCHO or rr >= ALTO or (rr >= 0 and t[rr][cc] != VACIA):
            return False
    return True


def colocaciones(t, pieza: Pieza) -> List[Colocacion]:
    """Todas las colocaciones válidas: giro × columna, con caída instantánea.
    Válida = la pieza cabe en las filas superiores de esa columna (si no cabe al aparecer, no hay colocación)."""
    out: List[Colocacion] = []
    for k, rot in enumerate(rotaciones(pieza.celdas)):
        ancho = max(c for _, c, _ in rot) + 1
        for col in range(ANCHO - ancho + 1):
            if not _cabe(t, rot, 0, col):
                continue
            f = 0
            while _cabe(t, rot, f + 1, col):
                f += 1
            out.append(Colocacion(k, col, f, tuple((r + f, c + col, s) for r, c, s in rot)))
    return out


def aplicar(t, col: Colocacion) -> Efecto:
    """Coloca (sin mutar `t`) y limpia.

    Regla: una fila llena se borra. Si entre sus celdas hay una chispa, se borra también TODA su columna.
    Gravedad: las filas se borran y lo de arriba baja tantas filas como filas borradas haya debajo (apilado
    normal); una columna borrada queda vacía y no necesita gravedad. No hay cascadas: las filas no se llenan
    por esa caída (la gravedad no cambia el contenido de una fila ni su orden de columnas).
    """
    n = copiar(t)
    for r, c, s in col.celdas:
        n[r][c] = s
    llenas = [r for r in range(ALTO) if all(x != VACIA for x in n[r])]
    cols = sorted({c for r in llenas for c in range(ANCHO) if n[r][c] == CHISPA})
    borradas_col = sum(1 for c in cols for r in range(ALTO) if r not in llenas and n[r][c] != VACIA)
    for c in cols:
        for r in range(ALTO):
            n[r][c] = VACIA
    if llenas:
        conserva = [n[r] for r in range(ALTO) if r not in llenas]
        n = [[VACIA] * ANCHO for _ in llenas] + conserva
    puntos = 100 * len(llenas) * len(llenas) + 10 * borradas_col
    return Efecto(n, len(llenas), borradas_col, tuple(cols), puntos)


def alturas(t) -> List[int]:
    out = []
    for c in range(ANCHO):
        h = 0
        for r in range(ALTO):
            if t[r][c] != VACIA:
                h = ALTO - r
                break
        out.append(h)
    return out


def huecos(t) -> int:
    n = 0
    for c in range(ANCHO):
        visto = False
        for r in range(ALTO):
            if t[r][c] != VACIA:
                visto = True
            elif visto:
                n += 1
    return n


def a_texto(t) -> List[str]:
    return ["".join(".#*"[x] for x in fila) for fila in t]


class Juego:
    """Una partida. `semilla` fija la secuencia de piezas. `jugar(colocacion)` coloca la pieza actual."""

    def __init__(self, semilla: int):
        self.semilla = semilla
        self._rng = random.Random(semilla)
        self.tablero = tablero_vacio()
        self.piezas_colocadas = 0
        self.filas_limpiadas = 0
        self.puntos = 0
        self.pieza: Optional[Pieza] = None
        self.terminado = False
        self._siguiente()

    def _siguiente(self) -> None:
        nombre = NOMBRES[self._rng.randrange(len(NOMBRES))]
        base = PIEZAS[nombre]
        k = self._rng.randrange(len(base)) if self._rng.random() < PROB_CHISPA else -1
        self.pieza = Pieza(nombre, tuple((r, c, CHISPA if i == k else NORMAL) for i, (r, c) in enumerate(base)))
        if not colocaciones(self.tablero, self.pieza):
            self.terminado = True

    def colocaciones(self) -> List[Colocacion]:
        return [] if self.terminado else colocaciones(self.tablero, self.pieza)

    def jugar(self, col: Colocacion) -> Efecto:
        if self.terminado:
            raise RuntimeError("la partida terminó")
        ef = aplicar(self.tablero, col)
        self.tablero = ef.tablero
        self.piezas_colocadas += 1
        self.filas_limpiadas += ef.filas
        self.puntos += ef.puntos + 10
        self._siguiente()
        return ef
