"""Pregunta `choice` autodescriptiva por decisión: 3 opciones (subir, bajar, quieta) barajadas, cada una con la distancia a la
que quedaría el centro de la pala del punto de corte previsto. El texto es el mismo para los dos modelos."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Tuple

from .motor import ALTO, Estado, VEL_PALA, ALTO_PALA, corte

ID_PREGUNTA = "pala"
PREGUNTA = "¿Qué hago con la pala?"
ACCIONES = (("subir", -1), ("bajar", 1), ("quieta", 0))
HORIZONTE = 12  # tics que se proyecta la acción (≈ 0,4 s)


@dataclass(frozen=True)
class Opcion:
    id: str
    nombre: str
    accion: int
    distancia: int
    descripcion: str


def objetivo(e: Estado, lado: str) -> Tuple[float, str]:
    """(y a la que conviene llevar la pala, frase de estado). Si la pelota se aleja, volver al centro."""
    c = corte(e, lado)
    if c is None:
        return ALTO / 2, "La pelota se aleja; conviene esperar en el centro"
    y, tics = c
    return y, f"La pelota viene hacia ti y llega en {tics / 30:.1f} s; punto de corte a {round(y)} px de altura"


def construir(e: Estado, lado: str, rng: random.Random) -> Tuple[str, List[Opcion]]:
    y, frase = objetivo(e, lado)
    c = corte(e, lado)
    pasos = HORIZONTE if c is None else max(1, min(HORIZONTE, int(c[1])))
    ops = []
    for nombre, a in ACCIONES:
        fin = min(ALTO - ALTO_PALA / 2, max(ALTO_PALA / 2, e.palas[lado] + a * VEL_PALA * pasos))
        d = int(round(abs(fin - y)))
        ops.append((nombre, a, d))
    rng.shuffle(ops)
    out = []
    for i, (nombre, a, d) in enumerate(ops, 1):
        punto = "punto de corte" if c is not None else "centro"
        out.append(Opcion(str(i), nombre, a, d, f"{nombre}: la pala queda a {d} px del {punto}"))
    estado = f"{frase}. Tu pala está a {round(e.palas[lado])} px."
    return estado, out


def optima(ops: List[Opcion]) -> Opcion:
    """La de menor distancia; empate: quieta, luego el orden de ACCIONES."""
    orden = {n: i for i, (n, _) in enumerate(ACCIONES)}
    return min(ops, key=lambda o: (o.distancia, o.accion != 0, orden[o.nombre]))


def peticion_chispa(estado: str, ops: List[Opcion]) -> dict:
    return {"state": estado, "questions": [{"id": ID_PREGUNTA, "question": PREGUNTA, "kind": "choice",
                                            "options": [{"id": o.id, "description": o.descripcion} for o in ops]}]}


def peticion_laya(estado: str, ops: List[Opcion]) -> dict:
    """Para `laya_servidor.py` (envuelve `laya.Router.predict`): misma pregunta y mismas opciones."""
    return {"state": estado, "instructions": PREGUNTA, "criteria": {o.id: o.descripcion for o in ops}}
