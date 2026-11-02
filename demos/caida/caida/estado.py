"""Texto del estado que viaja en `state` (el mismo para las tres preguntas)."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from . import api
from .agentes import descripcion
from .motor import ALTO, ANCHO, Colocacion, Juego, a_texto, alturas, huecos


def texto_estado(juego: Juego, opciones: Optional[List[Tuple[str, Colocacion, dict]]] = None) -> str:
    """Tablero y pieza. Con `opciones` ([(id, colocación, métricas)] en el orden que se ofrece) añade su lista (solo el choice)."""
    p = juego.pieza
    forma = "\n".join("".join("*" if (r, c, 2) in p.celdas else "#" if (r, c, 1) in p.celdas else "."
                              for c in range(max(c for _, c, _ in p.celdas) + 1))
                      for r in range(max(r for r, _, _ in p.celdas) + 1))
    h = alturas(juego.tablero)
    lineas = [f"Tablero {ANCHO}x{ALTO} (arriba primero; . vacío, # bloque, * chispa):"]
    lineas += a_texto(juego.tablero)
    lineas.append("Alturas por columna: " + " ".join(map(str, h)))
    lineas.append(f"Altura máxima {max(h)}, huecos {huecos(juego.tablero)}, piezas colocadas {juego.piezas_colocadas}.")
    lineas.append(f"Pieza: {p.nombre} ({len(p.celdas)} celdas, {'con' if p.tiene_chispa else 'sin'} chispa)")
    lineas.append(forma)
    if opciones is not None:
        lineas.append("Opciones:")
        for i, c, m in opciones:
            lineas.append(f"{i}) columna {c.col}, giro {c.rot}: {descripcion(c, m)}")
    return "\n".join(lineas)


def texto_pregunta(id_pregunta: str, juego: Juego, opciones: List[Tuple[str, Colocacion, dict]]) -> str:
    """El `state` de cada pregunta. ÚNICA fuente: la usan `peticiones_turno` (inferencia) y `entrenar_fewshot` (ejemplos).
    colocacion: tablero, pieza y la lista de opciones; riesgo y completa: solo tablero y pieza."""
    return texto_estado(juego, opciones if id_pregunta == api.ID_COLOCACION else None)


def peticiones_turno(juego: Juego, opciones: List[Tuple[str, Colocacion, dict]]) -> List[dict]:
    """Las peticiones de un turno: [choice, score+noul]. `state` es uno por petición, así que cada grupo lleva el suyo."""
    estados: Dict[str, str] = {q: texto_pregunta(q, juego, opciones) for q in (api.ID_COLOCACION, api.ID_RIESGO, api.ID_COMPLETA)}
    return api.construir_peticiones(estados, [(i, descripcion(c, m)) for i, c, m in opciones])
