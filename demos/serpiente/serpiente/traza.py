"""Traza de una partida: JSONL (una cabecera y una línea por paso). Con ella la partida se reproduce sin modelo."""
from __future__ import annotations

import json
from typing import Iterator, List, Tuple

from . import api
from .motor import Juego
from .partida import DECIDIR, AgenteChispa, Decision, jugar_partida

VERSION = 1


def registro_paso(paso: int, antes, d: Decision, r, j: Juego) -> dict:
    cuerpo, direccion, comida = antes
    ch = d.respuesta if isinstance(d.respuesta, dict) else {}
    return {
        "tipo": "paso", "paso": paso,
        "cuerpo": [list(c) for c in cuerpo], "dir": direccion, "comida": list(comida) if comida else None,
        "estado": d.estado, "opciones": d.opciones,
        "probs": ch.get("probs", {}), "escalate": bool(ch.get("escalate")), "escalate_reason": ch.get("escalate_reason", ""),
        "layer": ch.get("layer", ""),
        "giro": d.giro, "decidio": d.decidio or None, "confianza": d.confianza,
        "escudo": d.escudo, "motivo_escudo": d.motivo_escudo, "forzada": d.forzada, "coincide": d.coincide,
        "ms_cliente": d.ms_cliente, "ms_servidor": d.ms_servidor,
        "comio": r.comio, "choque": r.choque, "longitud": j.longitud, "comidas": j.comidas,
        "terminada": j.terminado, "fin": j.motivo,
    }


def grabar(ruta: str, semilla: int, url: str, decidir: str = "tau") -> dict:
    """Juega una partida de Chispa contra `url` y escribe la traza en `ruta`. Devuelve el resumen de la partida."""
    agente = AgenteChispa(url, decidir=decidir)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(json.dumps({"tipo": "cabecera", "version": VERSION, "semilla": semilla, "url": url,
                            "decidir": decidir}, ensure_ascii=False) + "\n")
        n = [0]

        def cada(antes, d, r, j):
            n[0] += 1
            f.write(json.dumps(registro_paso(n[0], antes, d, r, j), ensure_ascii=False) + "\n")

        return jugar_partida(semilla, agente, cada)


def leer(ruta: str) -> Tuple[dict, List[dict]]:
    with open(ruta, encoding="utf-8") as f:
        filas = [json.loads(x) for x in f if x.strip()]
    if not filas or filas[0].get("tipo") != "cabecera":
        raise ValueError("traza sin cabecera")
    return filas[0], [x for x in filas[1:] if x.get("tipo") == "paso"]


def reproducir(ruta: str) -> Iterator[dict]:
    """Reproduce la partida sin modelo: motor + semilla + giros de la traza. Lanza AssertionError si la serpiente o la
    comida de algún paso no coinciden con lo grabado."""
    cab, pasos = leer(ruta)
    j = Juego(cab["semilla"])
    for t in pasos:
        assert [list(c) for c in j.cuerpo] == t["cuerpo"], f"paso {t['paso']}: la serpiente no coincide"
        assert (list(j.comida) if j.comida else None) == t["comida"], f"paso {t['paso']}: la comida no coincide"
        yield t
        j.paso(t["giro"])
    if pasos:
        assert j.terminado and j.comidas == pasos[-1]["comidas"]


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="jugar", description="Juega una partida de Chispa contra un servidor y escribe la traza JSONL")
    ap.add_argument("--url", required=True)
    ap.add_argument("--salida", required=True, help="fichero .jsonl de la traza")
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--decidir", choices=DECIDIR, default="tau",
                    help="tau: si Chispa escala juega el profesor (escudo); argmax: se juega su argmax si trae probs")
    a = ap.parse_args(argv)
    try:
        api.salud(a.url)
    except api.ErrorRed as e:
        print(f"jugar: el servidor {a.url} no responde a /healthz: {e}")
        return 2
    r = grabar(a.salida, a.semilla, a.url, a.decidir)
    ds = r["decisiones"]
    n = {k: sum(d.decidio == k for d in ds) for k in ("chispa_tau", "chispa_bajo_tau", "escudo")}
    print(f"jugar: semilla {a.semilla} (decidir {a.decidir}): {r['pasos']} pasos, {r['comidas']} comidas, fin {r['fin']}, "
          f"chispa_tau {n['chispa_tau']}, chispa_bajo_tau {n['chispa_bajo_tau']}, escudo {n['escudo']} de {len(ds)}; traza en {a.salida}")
    return 0
