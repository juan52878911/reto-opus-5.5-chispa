"""Cliente de `POST /v1/decide` (contrato: docs/03-api.md y server/api/openapi.yaml). Solo urllib."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

K = 6  # opciones de la pregunta choice
ID_COLOCACION, ID_RIESGO, ID_COMPLETA = "colocacion", "riesgo", "completa"
PREGUNTA_COLOCACION = "¿Dónde coloco la pieza?"
PREGUNTA_RIESGO = "Riesgo de quedarse sin salida"
PREGUNTA_COMPLETA = "¿Esta pieza puede completar una fila?"
NIVELES_RIESGO = {
    "1": "sin riesgo: tablero bajo y limpio",
    "2": "riesgo bajo",
    "3": "riesgo medio",
    "4": "riesgo alto",
    "5": "a punto de quedarse sin salida",
}


class ErrorRed(Exception):
    """No hubo respuesta HTTP 200 utilizable."""


def construir_peticiones(estados: Dict[str, str], opciones: List[Tuple[str, str]]) -> List[dict]:
    """Dos peticiones por turno, porque `state` es único por petición: [choice (con la lista de opciones en su estado),
    score + noul (solo tablero y pieza)]. `estados`: {id_pregunta: texto}; riesgo y completa comparten el suyo.
    `opciones`: [(id, descripción)] del choice, ids "1".."n"."""
    if estados[ID_RIESGO] != estados[ID_COMPLETA]:
        raise ValueError("riesgo y completa van en la misma petición: necesitan el mismo estado")
    return [
        {"state": estados[ID_COLOCACION],
         "questions": [{"id": ID_COLOCACION, "question": PREGUNTA_COLOCACION, "kind": "choice",
                        "options": [{"id": i, "description": d} for i, d in opciones]}]},
        {"state": estados[ID_RIESGO],
         "questions": [{"id": ID_RIESGO, "question": PREGUNTA_RIESGO, "kind": "score",
                        "options": [{"id": i, "description": d} for i, d in NIVELES_RIESGO.items()]},
                       {"id": ID_COMPLETA, "question": PREGUNTA_COMPLETA, "kind": "noul"}]},
    ]


def decidir(url: str, cuerpo: dict, timeout: float = 10.0) -> Tuple[Dict[str, dict], float]:
    """POST a /v1/decide. Devuelve ({id_pregunta: resultado}, latencia_ms medida en el cliente)."""
    datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/v1/decide", data=datos, method="POST",
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            crudo = r.read()
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ErrorRed(str(e)) from e
    ms = (time.perf_counter() - t0) * 1000.0
    try:
        resp = json.loads(crudo)
        res = {r["id"]: r for r in resp["results"]}
    except (ValueError, KeyError, TypeError) as e:
        raise ErrorRed(f"respuesta ilegible: {e}") from e
    return res, ms


def salud(url: str, timeout: float = 5.0) -> dict:
    """GET /healthz; ErrorRed si el servidor no responde."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/healthz", timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ErrorRed(str(e)) from e
