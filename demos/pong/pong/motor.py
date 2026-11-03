"""Motor de «Chispa: Pong», un juego original del género pong. Solo biblioteca estándar.

Campo de ANCHO × ALTO px lógicos; pala izquierda y derecha de ALTO_PALA px que se mueven VEL_PALA px por tic según su acción
(-1 sube, 0 quieta, +1 baja). La pelota rebota arriba y abajo; al tocar una pala sale con un ángulo según dónde pegó y un 4 %
más rápida (con tope). Si cruza la línea de una pala, punto para el otro y saque desde el centro hacia quien lo perdió.
Termina a PUNTOS_FIN puntos o a MAX_TICS tics (3 min a 30 tics/s). Determinista dada la semilla y la secuencia de acciones."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, Optional

ANCHO, ALTO = 640, 480
ALTO_PALA, GROSOR_PALA, MARGEN_PALA = 80, 12, 24
VEL_PALA = 8.0
VEL_SAQUE, VEL_MAX, ACELERACION = 7.0, 22.0, 1.06  # v2: la pelota acelera hasta que los peloteos largos acaban
RADIO = 7
TICS_POR_S = 30
PUNTOS_FIN = 7
MAX_TICS = 3 * 60 * TICS_POR_S
LADOS = ("izquierda", "derecha")
X_PALA = {"izquierda": MARGEN_PALA + GROSOR_PALA, "derecha": ANCHO - MARGEN_PALA - GROSOR_PALA}  # cara que golpea


@dataclass
class Estado:
    tic: int = 0
    bx: float = ANCHO / 2
    by: float = ALTO / 2
    vx: float = VEL_SAQUE
    vy: float = 0.0
    palas: Dict[str, float] = field(default_factory=lambda: {"izquierda": ALTO / 2, "derecha": ALTO / 2})  # centro y
    acciones: Dict[str, int] = field(default_factory=lambda: {"izquierda": 0, "derecha": 0})
    puntos: Dict[str, int] = field(default_factory=lambda: {"izquierda": 0, "derecha": 0})
    golpes: Dict[str, int] = field(default_factory=lambda: {"izquierda": 0, "derecha": 0})
    terminada: bool = False
    objetivos: Dict[str, Optional[float]] = field(default_factory=lambda: {"izquierda": None, "derecha": None})

    def copia(self) -> "Estado":
        return Estado(self.tic, self.bx, self.by, self.vx, self.vy, dict(self.palas), dict(self.acciones), dict(self.puntos),
                      dict(self.golpes), self.terminada, dict(self.objetivos))


def _limitar_pala(y: float) -> float:
    return min(ALTO - ALTO_PALA / 2, max(ALTO_PALA / 2, y))


def reflejar(y: float) -> float:
    """Posición y de una trayectoria que rebota en y = RADIO y y = ALTO − RADIO."""
    lo, hi = RADIO, ALTO - RADIO
    per = 2 * (hi - lo)
    t = (y - lo) % per
    return lo + (t if t <= hi - lo else per - t)


def hacia(e: Estado, lado: str) -> bool:
    return (e.vx < 0) if lado == "izquierda" else (e.vx > 0)


def corte(e: Estado, lado: str) -> Optional[tuple]:
    """(y prevista donde la pelota cruza la cara de la pala de `lado`, tics hasta llegar), o None si se aleja."""
    if not hacia(e, lado) or e.vx == 0:
        return None
    dx = (X_PALA[lado] + (RADIO if lado == "izquierda" else -RADIO)) - e.bx
    tics = dx / e.vx
    if tics < 0:
        return None
    return reflejar(e.by + e.vy * tics), tics


class Juego:
    def __init__(self, semilla: int = 1):
        self.rng = random.Random(semilla)
        self.e = Estado()
        self._sacar(random.Random(semilla).choice(LADOS))

    def _sacar(self, hacia_lado: str) -> None:
        e = self.e
        e.bx, e.by = ANCHO / 2, self.rng.uniform(ALTO * 0.3, ALTO * 0.7)
        ang = self.rng.uniform(-0.6, 0.6)
        sentido = -1 if hacia_lado == "izquierda" else 1
        e.vx, e.vy = sentido * VEL_SAQUE * math.cos(ang), VEL_SAQUE * math.sin(ang)

    def accion(self, lado: str, a: int, objetivo: Optional[float] = None) -> None:
        """`objetivo` (y del centro de la pala): la pala se mueve en el sentido `a` y se para al llegar a él."""
        self.e.acciones[lado] = max(-1, min(1, int(a)))
        self.e.objetivos[lado] = objetivo

    def paso(self) -> Optional[str]:
        """Avanza un tic. Devuelve el lado que anota en este tic (o None)."""
        e = self.e
        if e.terminada:
            return None
        e.tic += 1
        for lado in LADOS:
            a, obj, y = e.acciones[lado], e.objetivos[lado], e.palas[lado]
            nuevo = y + a * VEL_PALA
            if obj is not None and a and (y - obj) * a < 0 <= (nuevo - obj) * a:  # va hacia él y llega: se queda ahí
                nuevo, e.acciones[lado] = obj, 0
            e.palas[lado] = _limitar_pala(nuevo)
        e.bx += e.vx
        e.by += e.vy
        if e.by < RADIO or e.by > ALTO - RADIO:
            e.by = reflejar(e.by)
            e.vy = -e.vy
        anota = None
        for lado in LADOS:
            cara = X_PALA[lado]
            cruza = (e.vx < 0 and e.bx - RADIO <= cara) if lado == "izquierda" else (e.vx > 0 and e.bx + RADIO >= cara)
            if not cruza:
                continue
            off = (e.by - e.palas[lado]) / (ALTO_PALA / 2)
            if abs(off) <= 1.0 + RADIO / (ALTO_PALA / 2):
                v = min(VEL_MAX, math.hypot(e.vx, e.vy) * ACELERACION)
                ang = max(-1.0, min(1.0, off)) * 0.9
                sentido = 1 if lado == "izquierda" else -1
                e.vx, e.vy = sentido * v * math.cos(ang), v * math.sin(ang)
                e.bx = cara + sentido * RADIO
                e.golpes[lado] += 1
            elif (lado == "izquierda" and e.bx < 0) or (lado == "derecha" and e.bx > ANCHO):
                anota = "derecha" if lado == "izquierda" else "izquierda"
        if anota:
            e.puntos[anota] += 1
            self._sacar("izquierda" if anota == "derecha" else "derecha")
        if max(e.puntos.values()) >= PUNTOS_FIN or e.tic >= MAX_TICS:
            e.terminada = True
        return anota
