"""Datos de imitación de Pong, comunes a Laya y Chispa, y la pregunta de esquema fijo que usan los modelos ajustados.

Para ajustar, las opciones son fijas (`subir`, `bajar`, `quieta`) y lo que cambia en cada turno va en el texto de estado, en
orden fijo: «La pelota viene hacia tu pala. subir: la alcanza. bajar: falla. quieta: pero no llega.» (cualitativo) o
«… subir: queda a 12 px. …» (px). El maestro es el jugador óptimo (la acción que deja la pala más cerca del objetivo).

Partidas sin tiempo real (paso a paso); cada `cada` tics se decide: con prob. `ruido` se juega al azar (para visitar estados
malos), si no la del maestro; la etiqueta es siempre la del maestro. Una de cada 10 partidas va a `dev` (sin mezclar turnos).

    python -m pong imitar --salida DIR [--n 16000] [--ruido 0.3] [--semilla 1] [--t 20]

Escribe, para cada redacción (px, cualitativo): `ejemplos-<r>.jsonl` (texto, etiqueta, split, partida, blanda),
`train-<r>.jsonl` y `dev-<r>.jsonl` (texto, etiqueta), y `esquema.json` (para `chispa train`)."""
from __future__ import annotations

import argparse
import json
import math
import os
import random
from typing import Dict, List, Tuple

from . import opciones as O
from .motor import ALTO, ALTO_PALA, VEL_PALA, Estado, Juego, corte

ID = "pala_fija"
PREGUNTA = "¿Qué movimiento devuelve la pelota?"
DESCRIPCIONES = {"subir": "subir la pala", "bajar": "bajar la pala", "quieta": "dejar la pala quieta"}
NOMBRES = ("subir", "bajar", "quieta")
REDACCIONES = ("px", "cualitativo")


def _desenlace(d: int, d0: float) -> str:
    if d < ALTO_PALA / 2:
        return "la alcanza"
    return "pero no llega" if d < d0 else "falla"


def distancias(e: Estado, lado: str) -> Tuple[Dict[str, int], float, bool]:
    """({acción: distancia final al objetivo}, distancia actual, ¿viene la pelota?) con el mismo cálculo que `opciones`."""
    y, _ = O.objetivo(e, lado)
    c = corte(e, lado)
    pasos = O.HORIZONTE if c is None else max(1, min(O.HORIZONTE, int(c[1])))
    out = {}
    for nombre, a in O.ACCIONES:
        fin = min(ALTO - ALTO_PALA / 2, max(ALTO_PALA / 2, e.palas[lado] + a * VEL_PALA * pasos))
        out[nombre] = int(round(abs(fin - y)))
    return out, abs(e.palas[lado] - y), c is not None


def texto(e: Estado, lado: str, redaccion: str) -> str:
    d, d0, viene = distancias(e, lado)
    cab = "La pelota viene hacia tu pala." if viene else "La pelota se aleja; vuelve al centro."
    if redaccion == "px":
        partes = [f"{n}: queda a {d[n]} px" for n in NOMBRES]
    else:
        partes = [f"{n}: {_desenlace(d[n], d0)}" for n in NOMBRES]
    return cab + " " + ". ".join(partes) + "."


def maestro(e: Estado, lado: str) -> str:
    d, _, _ = distancias(e, lado)
    orden = {n: i for i, (n, _) in enumerate(O.ACCIONES)}
    return min(NOMBRES, key=lambda n: (d[n], n != "quieta", orden[n]))


def blanda(e: Estado, lado: str, t: float) -> Dict[str, float]:
    d, _, _ = distancias(e, lado)
    m = min(d.values())
    w = {n: math.exp(-(d[n] - m) / t) for n in NOMBRES}
    s = sum(w.values())
    return {n: round(w[n] / s, 6) for n in NOMBRES}


def esquema() -> dict:
    return {"id": ID, "pregunta": PREGUNTA, "tipo": "choice", "opciones": dict(DESCRIPCIONES)}


def peticion(estado: str) -> dict:
    """Pregunta de esquema fijo para `/v1/decide` (Chispa ajustada)."""
    return {"state": estado, "questions": [{"id": ID, "question": PREGUNTA, "kind": "choice",
                                            "options": [{"id": n, "description": DESCRIPCIONES[n]} for n in NOMBRES]}]}


def generar(n: int = 16000, semilla: int = 1, ruido: float = 0.3, t: float = 20.0, cada: int = 3, max_tics: int = 900) -> List[dict]:
    rng = random.Random(semilla)
    filas, partida = [], 0
    while len(filas) < n:
        partida += 1
        j = Juego(semilla * 100003 + partida)
        split = "dev" if partida % 10 == 0 else "train"
        while not j.e.terminada and j.e.tic < max_tics and len(filas) < n:  # partidas de ≤ 30 s: muchas partidas para el split
            if j.e.tic % cada == 0:
                for lado in ("izquierda", "derecha"):
                    e = j.e
                    m = maestro(e, lado)
                    filas.append({"partida": partida, "split": split, "lado": lado, "etiqueta": m, "blanda": blanda(e, lado, t),
                                  **{f"texto_{r}": texto(e, lado, r) for r in REDACCIONES}})
                    jugada = rng.choice(NOMBRES) if rng.random() < ruido else m
                    j.accion(lado, dict(O.ACCIONES)[jugada])
            j.paso()
    return filas[:n]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="imitar", description=__doc__.splitlines()[0])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--n", type=int, default=16000)
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--ruido", type=float, default=0.3)
    ap.add_argument("--t", type=float, default=20.0, help="T de la etiqueta blanda softmax(−distancia/T), en px")
    a = ap.parse_args(argv)
    os.makedirs(a.salida, exist_ok=True)
    filas = generar(a.n, a.semilla, a.ruido, a.t)
    with open(os.path.join(a.salida, "esquema.json"), "w", encoding="utf-8") as f:
        json.dump(esquema(), f, ensure_ascii=False, indent=1)
    for r in REDACCIONES:
        with open(os.path.join(a.salida, f"ejemplos-{r}.jsonl"), "w", encoding="utf-8") as f:
            for x in filas:
                f.write(json.dumps({"texto": x[f"texto_{r}"], "etiqueta": x["etiqueta"], "split": x["split"], "partida": x["partida"],
                                    "blanda": x["blanda"]}, ensure_ascii=False) + "\n")
        for sp in ("train", "dev"):
            with open(os.path.join(a.salida, f"{sp}-{r}.jsonl"), "w", encoding="utf-8") as f:
                for x in filas:
                    if x["split"] == sp:
                        f.write(json.dumps({"texto": x[f"texto_{r}"], "etiqueta": x["etiqueta"]}, ensure_ascii=False) + "\n")
    from collections import Counter
    print(json.dumps({"filas": len(filas), "split": Counter(x["split"] for x in filas),
                      "etiquetas": Counter(x["etiqueta"] for x in filas), "partidas": filas[-1]["partida"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
