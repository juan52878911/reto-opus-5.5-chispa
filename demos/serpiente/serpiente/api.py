"""Cliente de `POST /v1/decide` (contrato: docs/03-api.md y server/api/openapi.yaml). Solo urllib."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Dict, List, Tuple

ID_GIRO = "giro"
PREGUNTA_GIRO = "¿Hacia dónde muevo la serpiente en este paso?"


class ErrorRed(Exception):
    """No hubo respuesta HTTP 200 utilizable."""


def construir_peticion(estado: str, opciones: List[Tuple[str, str]]) -> dict:
    """Una pregunta `choice` con las opciones [(id, descripción)]."""
    return {"state": estado,
            "questions": [{"id": ID_GIRO, "question": PREGUNTA_GIRO, "kind": "choice",
                           "options": [{"id": i, "description": d} for i, d in opciones]}]}


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
