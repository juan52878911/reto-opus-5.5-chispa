"""Traza de una partida: JSONL (una cabecera y una línea por turno). Con ella la partida se reproduce sin modelo."""
from __future__ import annotations

import json
from typing import Iterator, List, Tuple

from . import api
from .motor import Juego, a_texto
from .partida import DECIDIR, AgenteChispa, Decision, jugar_partida

VERSION = 1


def _pregunta(r: dict) -> dict:
    return {"answer": r.get("answer", ""), "probs": r.get("probs", {}), "layer": r.get("layer", ""),
            "escalate": bool(r.get("escalate")), "escalate_reason": r.get("escalate_reason", ""),
            "ms_servidor": r.get("ms")}


def registro_turno(turno: int, antes, d: Decision, ef, juego_despues: Juego) -> dict:
    tablero, pieza = antes
    return {
        "tipo": "turno", "turno": turno,
        "tablero": a_texto(tablero),
        "pieza": {"nombre": pieza.nombre, "celdas": [list(c) for c in pieza.celdas]},
        "estado": d.estado,
        "opciones": d.opciones,
        "preguntas": {k: (_pregunta(v) if isinstance(v, dict) and "kind" in v else v) for k, v in d.preguntas.items()},
        "elegida": d.id_elegida, "rot": d.col.rot, "col": d.col.col,
        "celdas_elegidas": [list(c) for c in d.col.celdas],
        "decidio": d.decidio or None, "escudo": d.escudo, "motivo_escudo": d.motivo_escudo, "forzada": d.forzada,
        "ms_cliente": d.ms_cliente, "ms_servidor": d.ms_servidor,
        "filas": ef.filas, "columnas_borradas": list(ef.columnas), "puntos_turno": ef.puntos + 10,
        "puntos": juego_despues.puntos, "filas_total": juego_despues.filas_limpiadas,
        "terminada": juego_despues.terminado,
    }


def grabar(ruta: str, semilla: int, url: str, max_piezas: int, decidir: str = "tau") -> dict:
    """Juega una partida de Chispa contra `url` y escribe la traza en `ruta`. Devuelve el resumen de la partida."""
    agente = AgenteChispa(url, decidir=decidir)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(json.dumps({"tipo": "cabecera", "version": VERSION, "semilla": semilla, "url": url,
                            "max_piezas": max_piezas, "k": api.K, "decidir": decidir}, ensure_ascii=False) + "\n")
        n = [0]

        def cada(antes, d, ef, j):
            n[0] += 1
            f.write(json.dumps(registro_turno(n[0], antes, d, ef, j), ensure_ascii=False) + "\n")

        return jugar_partida(semilla, agente, max_piezas, cada)


def leer(ruta: str) -> Tuple[dict, List[dict]]:
    with open(ruta, encoding="utf-8") as f:
        filas = [json.loads(x) for x in f if x.strip()]
    if not filas or filas[0].get("tipo") != "cabecera":
        raise ValueError("traza sin cabecera")
    return filas[0], [x for x in filas[1:] if x.get("tipo") == "turno"]


def reproducir(ruta: str) -> Iterator[dict]:
    """Reproduce la partida sin modelo: motor + semilla + jugadas de la traza. Comprueba que el tablero
    de cada turno coincide con el grabado (lanza AssertionError si no)."""
    cab, turnos = leer(ruta)
    j = Juego(cab["semilla"])
    for t in turnos:
        assert a_texto(j.tablero) == t["tablero"], f"turno {t['turno']}: el tablero no coincide"
        assert j.pieza.nombre == t["pieza"]["nombre"], f"turno {t['turno']}: pieza distinta"
        col = next(c for c in j.colocaciones() if (c.rot, c.col) == (t["rot"], t["col"]))
        yield t
        j.jugar(col)
    assert j.puntos == (turnos[-1]["puntos"] if turnos else 0)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jugar", description="Juega una partida de Chispa contra un servidor y escribe la traza JSONL")
    ap.add_argument("--url", required=True)
    ap.add_argument("--salida", required=True, help="fichero .jsonl de la traza")
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--max-piezas", type=int, default=100)
    ap.add_argument("--decidir", choices=DECIDIR, default="tau",
                    help="tau: si Chispa escala juega el profesor (escudo); argmax: se juega su argmax si trae probs")
    a = ap.parse_args(argv)
    try:
        api.salud(a.url)
    except api.ErrorRed as e:
        print(f"jugar: el servidor {a.url} no responde a /healthz: {e}")
        return 2
    r = grabar(a.salida, a.semilla, a.url, a.max_piezas, a.decidir)
    ds = r["decisiones"]
    n = {k: sum(d.decidio == k for d in ds) for k in ("chispa_tau", "chispa_bajo_tau", "escudo")}
    print(f"jugar: semilla {a.semilla} (decidir {a.decidir}): {r['piezas']} piezas, {r['filas']} filas, {r['puntos']} puntos, "
          f"chispa_tau {n['chispa_tau']}, chispa_bajo_tau {n['chispa_bajo_tau']}, escudo {n['escudo']} de {len(ds)}; traza en {a.salida}")
    return 0
