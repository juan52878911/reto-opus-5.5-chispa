"""Interfaz para la parte ALE (otra pieza). Sin implementar: aquí no se importa ni se instala `ale-py`.

Bucle previsto con `ALE/Tetris-v5` (`frameskip=1`, `repeat_action_probability=0`, semillas fijas):

    obs → Percepcion.leer → (tablero, pieza, siguiente) → colocaciones / opciones / agente → Colocacion
        → Controlador.acciones → botones de Atari hasta que la pieza se fija → siguiente obs

`Colocacion.giro` y `Colocacion.col` son los parámetros que hay que mapear a los giros y movimientos de Atari: el giro 0 es la
forma de reposo y cada giro siguiente es un cuarto de vuelta horario (ver `motor.py`)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, List, Optional, Tuple

from .motor import Colocacion


class Percepcion(ABC):
    """Observación del emulador (RAM o píxeles) → estado del tablero y piezas, en la convención del simulador."""

    @abstractmethod
    def leer(self, observacion: Any) -> Tuple[Tuple[int, ...], str, Optional[str]]:
        """Devuelve `(tablero, pieza, siguiente)`:
        - `tablero`: tupla de `ALTO` enteros, fila 0 ABAJO, bit `c` = columna `c` (como `motor.TABLERO_VACIO`), SIN la pieza que cae.
        - `pieza`: una letra de `motor.PIEZAS` (la pieza que cae ahora).
        - `siguiente`: la pieza siguiente, o None si la observación no la da."""


class Controlador(ABC):
    """Colocación elegida → secuencia de acciones de Atari que la ejecutan."""

    @abstractmethod
    def acciones(self, colocacion: Colocacion, observacion: Any) -> List[int]:
        """Devuelve los índices de acción del espacio de acciones de ALE (giros, desplazamientos y caída) que dejan la pieza
        en (`colocacion.giro`, `colocacion.col`). Debe terminar con la pieza fijada; si la observación no coincide con lo
        esperado (p. ej. la pieza se desvió), puede devolver una secuencia corta y se pide otra colocación."""
