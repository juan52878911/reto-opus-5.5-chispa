"""Diseño de la decisión v2, igual para los dos modelos (pedido de Juan: que los dos jueguen bien entre ellos).

- Solo se pregunta al modelo cuando la pelota viene hacia su pala; cuando se aleja, la pala vuelve al centro por regla.
- El estado se calcula sobre la posición que tendrá la pala cuando llegue la respuesta (posición actual + acción en curso ×
  latencia típica de ese modelo), así una respuesta tardía sigue siendo válida.
- El texto describe la situación con palabras («la pelota llegará muy por encima de tu pala»); las opciones son fijas:
  subir, bajar, quieta (barajadas en la petición). La acción elegida mueve la pala hacia el punto de corte y la para allí.
- El maestro elige el sentido hacia el punto de corte, o quieta si la pala ya lo cubre (a menos de ALINEADA px)."""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from .motor import ALTO, ALTO_PALA, VEL_PALA, Estado, corte, hacia

ID = "pala"
PREGUNTA = "¿Qué movimiento devuelve la pelota?"
DESCRIPCIONES = {"subir": "subir", "bajar": "bajar", "quieta": "quieta"}  # las mismas cadenas con las que Laya entrena su pregunta
NOMBRES = ("subir", "bajar", "quieta")
ACCION = {"subir": -1, "bajar": 1, "quieta": 0}
ALINEADA = ALTO_PALA / 4  # 20 px: el centro de la pala cubre el punto de corte con margen


def limitar(y: float) -> float:
    return min(ALTO - ALTO_PALA / 2, max(ALTO_PALA / 2, y))


def posicion_prevista(e: Estado, lado: str, tics: float) -> float:
    """Dónde estará el centro de la pala dentro de `tics`, con la acción y el objetivo en curso."""
    y, a, obj = e.palas[lado], e.acciones[lado], e.objetivos[lado]
    nuevo = y + a * VEL_PALA * tics
    if obj is not None and a and (y - obj) * a < 0 <= (nuevo - obj) * a:
        nuevo = obj
    return limitar(nuevo)


def viene(e: Estado, lado: str) -> bool:
    return hacia(e, lado) and corte(e, lado) is not None


def relacion(e: Estado, lado: str, tics_lat: float) -> Tuple[float, float, float]:
    """(punto de corte y, posición prevista de la pala, diferencia corte − pala). Solo si la pelota viene."""
    y, _ = corte(e, lado)
    p = posicion_prevista(e, lado, tics_lat)
    return y, p, y - p


def _cuanto(d: float) -> str:
    d = abs(d)
    return "muy " if d > 150 else ("un poco " if d < 60 else "")


def texto(d: float) -> str:
    """Estado con palabras a partir de la diferencia corte − pala (en el eje y del juego, que crece hacia abajo)."""
    if abs(d) < ALINEADA:
        return "La pelota viene hacia tu pala y llegará a la altura de la pala."
    lugar = "por encima" if d < 0 else "por debajo"
    return f"La pelota viene hacia tu pala y llegará {_cuanto(d)}{lugar} de la pala."


def maestro(d: float) -> str:
    if abs(d) < ALINEADA:
        return "quieta"
    return "subir" if d < 0 else "bajar"


def peticion_chispa(estado: str, rng: Optional[random.Random] = None) -> dict:
    nombres = list(NOMBRES)
    if rng:
        rng.shuffle(nombres)
    return {"state": estado, "questions": [{"id": ID, "question": PREGUNTA, "kind": "choice",
                                            "options": [{"id": n, "description": DESCRIPCIONES[n]} for n in nombres]}]}


def peticion_laya(estado: str, rng: Optional[random.Random] = None) -> dict:
    nombres = list(NOMBRES)
    if rng:
        rng.shuffle(nombres)
    return {"state": estado, "instructions": PREGUNTA, "criteria": {n: DESCRIPCIONES[n] for n in nombres}}


def aplicar(juego, lado: str, nombre: str, y_corte: float) -> None:
    """La acción elegida mueve la pala hacia el punto de corte y la para allí (quieta: se para)."""
    a = ACCION[nombre]
    juego.accion(lado, a, y_corte if a else None)


def regla_alejandose(juego, lado: str) -> None:
    """La pelota se aleja: volver al centro (sin preguntar al modelo)."""
    y = juego.e.palas[lado]
    c = ALTO / 2
    juego.accion(lado, 0 if abs(y - c) < VEL_PALA else (1 if c > y else -1), c)
