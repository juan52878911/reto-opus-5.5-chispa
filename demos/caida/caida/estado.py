"""Texto del estado que viaja en `state` (el mismo para las tres preguntas)."""
from __future__ import annotations

from typing import List, Tuple

from .agentes import descripcion
from .motor import ALTO, ANCHO, Colocacion, Juego, a_texto, alturas, huecos


def texto_estado(juego: Juego, opciones: List[Tuple[str, Colocacion, dict]]) -> str:
    """`opciones`: [(id, colocación, métricas)] en el orden que se ofrece."""
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
    lineas.append("Opciones:")
    for i, c, m in opciones:
        lineas.append(f"{i}) columna {c.col}, giro {c.rot}: {descripcion(c, m)}")
    return "\n".join(lineas)
