"""Datos de imitación: decisiones del maestro con ruido en la política para cubrir estados malos.

Salida (en `--salida`):
- `filas.jsonl`: una fila por turno en el esquema de filas de Chispa (`model/esquema.md`): `tipo` choice, `pregunta`, `texto` (el
  estado), `opciones` (ids "1"…"n"), `descripciones` (con los rasgos de ese turno), `etiqueta` (la opción del maestro).
- `blandas.jsonl`: aparte, `{id, blanda}` con el objetivo blando softmax(valor/T) sobre las opciones; es el formato de
  `python -m model.l2.entrenar --blandas`.
Las partidas se reparten en train/dev por semilla (una de cada 10 es dev), así que no hay fugas entre splits.
El ruido: con probabilidad `ruido` se juega una opción al azar en vez de la del maestro; la etiqueta sigue siendo la del maestro."""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from typing import Dict, Iterator, List

from . import maestro as M, opciones as O
from .motor import Juego

PREGUNTA = O.PREGUNTA_COLOCACION


def softmax(valores: List[float], t: float) -> List[float]:
    m = max(valores)
    e = [math.exp((v - m) / t) for v in valores]
    s = sum(e)
    return [x / s for x in e]


def filas(n: int, semilla: int = 1, ruido: float = 0.3, temperatura: float = 1.0, max_piezas: int = 150,
          pesos=M.PESOS_DELLACHERIE, sin_siguiente: bool = False) -> Iterator[tuple]:
    """Genera `n` pares (fila, blanda) jugando partidas sucesivas (semillas semilla, semilla+1, …)."""
    rng = random.Random(semilla)
    k, partida = 0, 0
    while k < n:
        sem = semilla + partida
        split = "dev" if partida % 10 == 9 else "train"
        partida += 1
        j = Juego(sem)
        while not j.terminado and j.piezas_colocadas < max_piezas and k < n:
            cols = j.colocaciones()
            ops = O.construir(j.tablero, cols, rng, pesos=pesos)
            if len(ops) >= 2:
                mejor = min(ops, key=lambda o: o.puesto)
                id_ = f"tetris:{split}:{k}"
                fila = {
                    "id": id_, "tarea": "tetris_colocacion", "tipo": "choice", "pregunta": PREGUNTA,
                    "texto": O.texto_estado(j.tablero, j.pieza, None if sin_siguiente else j.siguiente),
                    "opciones": [o.id for o in ops], "descripciones": {o.id: o.descripcion for o in ops},
                    "etiqueta": mejor.id, "idioma": "es", "split": split, "fuente": "simulador tetris-ale (maestro Dellacherie)",
                    "licencia": "CC0-1.0", "uso_comercial": True, "plantilla": f"semilla-{sem}",
                }
                p = softmax([o.valor for o in ops], temperatura)
                yield fila, {"id": id_, "blanda": {o.id: round(x, 6) for o, x in zip(ops, p)}}
                k += 1
                jugada = rng.choice(ops) if rng.random() < ruido else mejor
            else:
                jugada = ops[0]
            j.jugar(jugada.col)


def generar(salida: str, n: int = 16000, **kw) -> dict:
    os.makedirs(salida, exist_ok=True)
    t0, cpu0 = time.perf_counter(), time.process_time()
    cuenta: Dict[str, int] = {}
    with open(os.path.join(salida, "filas.jsonl"), "w", encoding="utf-8") as f, \
            open(os.path.join(salida, "blandas.jsonl"), "w", encoding="utf-8") as b:
        for fila, blanda in filas(n, **kw):
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            b.write(json.dumps(blanda, ensure_ascii=False) + "\n")
            cuenta[fila["split"]] = cuenta.get(fila["split"], 0) + 1
    return {"filas": n, "por_split": cuenta, "segundos": round(time.perf_counter() - t0, 1),
            "cpu_s": round(time.process_time() - cpu0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="generar", description=__doc__.splitlines()[0])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--n", type=int, default=16000)
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--ruido", type=float, default=0.3, help="probabilidad de jugar una opción al azar en vez de la del maestro")
    ap.add_argument("--sin-siguiente", action="store_true", help="el estado no nombra la pieza siguiente (como en el bucle ALE)")
    ap.add_argument("--temperatura", type=float, default=1.0, help="T del objetivo blando softmax(valor/T)")
    a = ap.parse_args(argv)
    print(json.dumps(generar(a.salida, a.n, semilla=a.semilla, ruido=a.ruido, temperatura=a.temperatura, sin_siguiente=a.sin_siguiente)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
