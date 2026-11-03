"""Utilidades comunes (solo biblioteca estándar)."""
from __future__ import annotations

import json
import math
import os
from typing import Optional, Sequence


def percentil(valores: Sequence[float], p: float) -> Optional[float]:
    """Percentil p (0–100) con interpolación lineal; None si no hay datos."""
    if not valores:
        return None
    v = sorted(valores)
    k = (len(v) - 1) * p / 100.0
    a, b = math.floor(k), math.ceil(k)
    return v[a] + (v[b] - v[a]) * (k - a)


def redondea(x: Optional[float], n: int = 3) -> Optional[float]:
    return None if x is None else round(x, n)


def escribir_json(ruta: str, obj) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(ruta)), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
