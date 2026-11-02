"""Genera los ejemplos few-shot (de partidas del profesor), los esquemas y el comando `chispa train`. Solo biblioteca estándar.

Un `.chispa` por pregunta (L0 se elige por el conjunto de etiquetas): se escriben tres juegos de ficheros
`ejemplos-<id>.jsonl` (columnas `texto` y `etiqueta`) y `esquema-<id>.json`, más `entrenar.sh` con los tres comandos
`chispa train` (SIN --conjunta: L0/L1 con ejemplos y, si hay L2 y torre, L2 zero-shot con torre al vuelo).

Etiquetas:
- colocacion: el id (1..K) de la jugada del profesor. El profesor es siempre la opción 1 en vivo, así que para que
  haya ejemplos de todas las opciones la lista de opciones del ejemplo se ROTA (offset = turno mod K) y se renumera
  1..K; la etiqueta es la posición de la mejor del profesor tras rotar. El texto lista las opciones en ese orden.
- riesgo: nivel 1–5 por la altura máxima ANTES de colocar (≤4→1, 5–7→2, 8–10→3, 11–12→4, ≥13→5).
- completa: "true" si alguna colocación de la pieza limpia ≥ 1 fila, si no "false".
Las partidas llevan ruido (`--ruido`: fracción de jugadas al azar en vez de la del profesor) para que el tablero
llegue a alturas altas y existan ejemplos de todos los niveles de riesgo; las etiquetas siguen siendo las del profesor.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shlex
import sys
from collections import defaultdict
from typing import Dict, List

from . import api
from .agentes import descripcion, puede_completar_fila, ranking, riesgo_derivado
from .estado import texto_estado
from .motor import Juego


def generar(n: int, semilla: int = 1000, ruido: float = 0.25, max_partidas: int = 3000, max_piezas: int = 120) -> Dict[str, List[dict]]:
    """Devuelve {id_pregunta: [{"texto","etiqueta"}]} con `n` ejemplos por pregunta, repartidos por igual entre clases."""
    clases = {api.ID_COLOCACION: [str(i) for i in range(1, api.K + 1)],
              api.ID_RIESGO: list(api.NIVELES_RIESGO), api.ID_COMPLETA: ["false", "true"]}
    for q, cs in clases.items():
        if n < len(cs):
            raise ValueError(f"n={n} < {len(cs)} clases de «{q}»: cada opción necesita al menos un ejemplo")
    cupo = {q: -(-n // len(cs)) for q, cs in clases.items()}
    cubo: Dict[str, Dict[str, List[dict]]] = {q: defaultdict(list) for q in clases}
    rng = random.Random(semilla)
    turno = 0
    for p in range(max_partidas):
        if all(len(cubo[q][c]) >= cupo[q] for q in clases for c in clases[q]):
            break
        j = Juego(semilla + p)
        while not j.terminado and j.piezas_colocadas < max_piezas:
            r = ranking(j)
            if len(r) >= api.K:
                top = r[:api.K]
                off = turno % api.K
                rot = top[off:] + top[:off]
                ops = [(str(i + 1), c, m) for i, (c, _, m) in enumerate(rot)]
                texto = texto_estado(j, ops)
                etiqueta = str(next(i for i, (c, _, _) in enumerate(rot) if c is top[0][0]) + 1)
                _poner(cubo, cupo, api.ID_COLOCACION, texto, etiqueta)
                turno += 1
            # riesgo y completa se describen sobre el estado SIN la lista de opciones del choice
            ops1 = [(str(i + 1), c, m) for i, (c, _, m) in enumerate(r[:api.K])]
            texto1 = texto_estado(j, ops1)
            _poner(cubo, cupo, api.ID_RIESGO, texto1, str(riesgo_derivado(j.tablero)))
            _poner(cubo, cupo, api.ID_COMPLETA, texto1, "true" if puede_completar_fila(j) else "false")
            j.jugar(r[rng.randrange(len(r))][0] if rng.random() < ruido else r[0][0])
    out: Dict[str, List[dict]] = {}
    for q, cs in clases.items():
        faltan = [c for c in cs if not cubo[q][c]]
        if faltan:
            raise ValueError(f"«{q}»: sin ejemplos de las clases {faltan}; sube --max-partidas o --ruido")
        # reparto por rondas entre clases hasta n
        filas, i = [], 0
        while len(filas) < n and any(i < len(cubo[q][c]) for c in cs):
            filas += [cubo[q][c][i] for c in cs if i < len(cubo[q][c])]
            i += 1
        out[q] = filas[:n]
    return out


def _poner(cubo, cupo, q, texto, etiqueta):
    b = cubo[q][etiqueta]
    if len(b) < cupo[q]:
        b.append({"texto": texto, "etiqueta": etiqueta})


def esquemas() -> Dict[str, dict]:
    return {
        api.ID_COLOCACION: {"id": api.ID_COLOCACION, "pregunta": api.PREGUNTA_COLOCACION, "tipo": "choice",
                            "opciones": {str(i): f"la colocación número {i} de la lista de opciones" for i in range(1, api.K + 1)}},
        api.ID_RIESGO: {"id": api.ID_RIESGO, "pregunta": api.PREGUNTA_RIESGO, "tipo": "score", "opciones": dict(api.NIVELES_RIESGO)},
        api.ID_COMPLETA: {"id": api.ID_COMPLETA, "pregunta": api.PREGUNTA_COMPLETA, "tipo": "noul",
                          "opciones": {"false": "ninguna colocación de la pieza completa una fila",
                                       "true": "alguna colocación de la pieza completa una fila"}},
    }


def comandos(carpeta: str, l1: str, l2: str, torre: str, python: str = "python") -> List[str]:
    """Un `chispa train` por pregunta, desde la raíz del repositorio. Sin --conjunta; L2 zero-shot con torre."""
    out = []
    for q in (api.ID_COLOCACION, api.ID_RIESGO, api.ID_COMPLETA):
        out.append("PYTHONPATH=sdk/python " + " ".join(shlex.quote(x) for x in [
            python, "-m", "chispa", "train",
            "--ejemplos", os.path.join(carpeta, f"ejemplos-{q}.jsonl"),
            "--esquema", os.path.join(carpeta, f"esquema-{q}.json"),
            "--l1", l1, "--l2", l2, "--torre", torre,
            "--salida", os.path.join(carpeta, f"{q}.chispa")]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="entrenar_fewshot", description=__doc__.split("\n\n")[0])
    ap.add_argument("--salida", required=True, help="carpeta donde escribir ejemplos, esquemas y entrenar.sh")
    ap.add_argument("--n", type=int, default=60, help="ejemplos por pregunta (≥ nº de clases; con ≥ 10 por opción entrena también L0)")
    ap.add_argument("--semilla", type=int, default=1000)
    ap.add_argument("--ruido", type=float, default=0.25)
    ap.add_argument("--max-partidas", type=int, default=3000)
    ap.add_argument("--l1", default="potion.chispa-l1", help=".chispa-l1 de L1")
    ap.add_argument("--l2", default="servidor.chispa", help=".chispa ya exportado de L2 (model/l2/exportar.py)")
    ap.add_argument("--torre", default="torre.onnx", help="ONNX de la torre de esquemas")
    a = ap.parse_args(argv)
    try:
        datos = generar(a.n, a.semilla, a.ruido, a.max_partidas)
    except ValueError as e:
        print(f"entrenar_fewshot: {e}", file=sys.stderr)
        return 1
    os.makedirs(a.salida, exist_ok=True)
    for q, filas in datos.items():
        with open(os.path.join(a.salida, f"ejemplos-{q}.jsonl"), "w", encoding="utf-8") as f:
            for fila in filas:
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    for q, esq in esquemas().items():
        with open(os.path.join(a.salida, f"esquema-{q}.json"), "w", encoding="utf-8") as f:
            json.dump(esq, f, ensure_ascii=False, indent=2)
    cmds = comandos(a.salida, a.l1, a.l2, a.torre)
    ruta = os.path.join(a.salida, "entrenar.sh")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/env bash\n# Desde la raíz del repositorio.\nset -euo pipefail\n" + "\n".join(cmds) + "\n")
    os.chmod(ruta, 0o755)
    print(f"entrenar_fewshot: {a.n} ejemplos por pregunta en {a.salida}\nComandos (también en {ruta}):")
    print("\n".join(cmds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
