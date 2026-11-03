"""Percepción por RAM y controlador en lazo cerrado para `ALE/Tetris-v5` (frameskip=1, sin sticky).

Mapa de la RAM (verificado en el CT 109 contra los píxeles, 4650 fotogramas, ver LEEME):
- tablero de 22 × 10 con la pieza que cae incluida; fila r (0 = arriba):
  columnas 0–5 en el byte 21 − r, bits 5…0; columnas 6–9 en el byte 43 − r, bits 0…3;
- byte 95: fila de la pieza contando desde abajo (19–21 al aparecer, baja hasta 0); un salto de ≥ 2 hacia arriba = pieza nueva
  (un giro puede subirla 1).
Tablero asentado = tablero de la RAM justo antes del salto; pieza que cae = tablero − asentado.

Entradas (medidas): el juego lee el mando cada 4 fotogramas. LEFT/RIGHT mantenidos mueven una columna por lectura; FIRE gira una
vez por pulsación (hay que mantenerlo ≥ 4 fotogramas y soltarlo otros 4); DOWN baja
una fila cada 2–4 fotogramas (sin DOWN, una cada 16). El controlador pulsa y suelta y comprueba en la RAM tras cada paso."""
from typing import FrozenSet, List, Optional, Tuple

NOOP, FIRE, RIGHT, LEFT, DOWN = 0, 1, 2, 3, 4
FILAS, COLUMNAS = 22, 10
BYTE_FILA = 95

Celdas = FrozenSet[Tuple[int, int]]


def tablero_ram(ram) -> List[List[int]]:
    t = [[0] * COLUMNAS for _ in range(FILAS)]
    for r in range(FILAS):
        a, b = int(ram[21 - r]), int(ram[43 - r])
        for c in range(6):
            t[r][c] = (a >> (5 - c)) & 1
        for c in range(6, 10):
            t[r][c] = (b >> (c - 6)) & 1
    return t


def celdas(t) -> Celdas:
    return frozenset((r, c) for r in range(FILAS) for c in range(COLUMNAS) if t[r][c])


def normalizar(cs) -> Celdas:
    r0, c0 = min(r for r, _ in cs), min(c for _, c in cs)
    return frozenset((r - r0, c - c0) for r, c in cs)


# forma normalizada → tetrominó (las 19 orientaciones distintas de los 7)
_BASE = {"I": [(0, 0), (0, 1), (0, 2), (0, 3)], "O": [(0, 0), (0, 1), (1, 0), (1, 1)], "T": [(0, 0), (0, 1), (0, 2), (1, 1)],
         "S": [(0, 1), (0, 2), (1, 0), (1, 1)], "Z": [(0, 0), (0, 1), (1, 1), (1, 2)], "J": [(0, 0), (0, 1), (0, 2), (1, 2)],
         "L": [(0, 0), (0, 1), (0, 2), (1, 0)]}


def _giros(cs):
    out, f = [], normalizar(cs)
    for _ in range(4):
        if f not in out:
            out.append(f)
        f = normalizar([(c, -r) for r, c in f])
    return out


GIROS = {k: _giros(v) for k, v in _BASE.items()}
TIPO_DE_FORMA = {f: k for k, fs in GIROS.items() for f in fs}


class Lectura:
    """Lo que el controlador ve en un fotograma."""

    def __init__(self, ram, asentado: Celdas):
        self.tablero = celdas(tablero_ram(ram))
        self.fila = int(ram[BYTE_FILA])
        self.pieza = self.tablero - asentado
        self.forma = normalizar(self.pieza) if len(self.pieza) == 4 else None
        self.columna = min(c for _, c in self.pieza) if self.pieza else None


class Partida:
    """Envuelve el entorno: `siguiente_pieza()` avanza hasta que aparece una pieza y devuelve (asentado, tipo);
    `colocar(forma, columna)` la lleva hasta ahí y la suelta. Cuenta fotogramas, líneas (recompensa) y fallos del controlador."""

    def __init__(self, env, semilla: int, al_paso=None):
        self.env, self.ale = env, env.unwrapped.ale
        self.obs, _ = env.reset(seed=semilla)
        self.al_paso = al_paso  # callback(obs, accion) para la traza/vídeo
        self.terminada, self.fotogramas, self.recompensa = False, 0, 0.0
        self.ram = self.ale.getRAM().copy()
        self.asentado: Celdas = frozenset()
        self.fallos = 0
        self._nueva = False
        self.registro = []  # fallos del controlador: (motivo, fila, columna leída, columna objetivo)

    def paso(self, a: int):
        if self.terminada:
            return
        self.obs, r, term, trunc, _ = self.env.step(a)
        self.fotogramas += 1
        self.recompensa += float(r)
        prev, self.ram = self.ram, self.ale.getRAM().copy()
        if int(self.ram[BYTE_FILA]) >= int(prev[BYTE_FILA]) + 2:  # pieza nueva (un giro puede subirla 1 fila): lo de antes queda asentado
            self.asentado = celdas(tablero_ram(prev))
            self._nueva = True
        if self.al_paso:
            self.al_paso(self.obs, a)
        self.terminada = term or trunc

    def lectura(self) -> Lectura:
        return Lectura(self.ram, self.asentado)

    def siguiente_pieza(self, tope=400) -> Optional[Tuple[Celdas, str]]:
        """Espera (NOOP) a que la pieza que cae tenga 4 celdas reconocibles, recién aparecida."""
        for _ in range(tope):
            le = self.lectura()
            if self._nueva and le.forma in TIPO_DE_FORMA and le.fila >= 18:  # tras el reset la RAM ya trae una pieza fantasma
                return self.asentado, TIPO_DE_FORMA[le.forma]
            if self.terminada:
                return None
            self.paso(NOOP)
        return None

    def colocar(self, forma: Celdas, columna: int, tope=600) -> bool:
        """Gira hasta `forma`, mueve hasta `columna` y suelta con DOWN hasta la pieza siguiente. False si no lo consigue."""
        self._nueva = False
        for _ in range(40):  # recién aparecida, al girar puede asomar por encima de la fila 0 y leerse con 3 celdas
            if self.terminada or self._nueva or self.lectura().fila <= 18:
                break
            self.paso(DOWN)
        giros, vistas = 0, [self.lectura().forma]
        while not self.terminada and self.lectura().forma != forma and giros < 6:
            for _ in range(4):  # el juego lee la entrada cada 4 fotogramas y gira una vez por pulsación
                self.paso(FIRE)
            for _ in range(4):
                self.paso(NOOP)
            vistas.append(self.lectura().forma)
            giros += 1
        if self.lectura().forma != forma:
            self.fallos += 1
            self.registro.append(("giro", self.lectura().fila, self.lectura().columna, columna, sorted(forma), [sorted(v) if v else None for v in vistas]))
            return False
        for _ in range(tope):
            if self.terminada or self._nueva:
                break
            le = self.lectura()
            if le.columna is None or le.forma != forma:
                self.paso(NOOP)
                continue
            if le.columna < columna:
                self.paso(RIGHT)
            elif le.columna > columna:
                self.paso(LEFT)
            else:
                break
        if self.lectura().columna != columna:
            self.fallos += 1
            self.registro.append(("columna", self.lectura().fila, self.lectura().columna, columna))
        for _ in range(tope):
            if self.terminada or self._nueva:
                break
            self.paso(DOWN)
        return True
