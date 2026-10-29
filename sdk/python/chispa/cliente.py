"""Cliente HTTP de `POST /v1/decide`: reintentos con espera exponencial y nonce estable entre reintentos."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import replace
from typing import List, Sequence

from .tipos import Pregunta, Resultado


class ChispaError(Exception):
    """Base de los errores del SDK."""


class ErrorSolicitud(ChispaError):
    """El servidor respondió con un error (400, 405, 413…). `status`; `codigo`, `mensaje` y `question_id` del error tipado
    `{"error":{"code","message","question_id"}}`. También acepta el formato viejo `{"error":"texto"}` (`codigo` y `question_id` vacíos)."""

    def __init__(self, status: int, mensaje, codigo: str = "", question_id=None):
        if isinstance(mensaje, dict):
            codigo = mensaje.get("code", codigo) or ""
            question_id = mensaje.get("question_id", question_id)
            mensaje = mensaje.get("message", "")
        super().__init__(f"HTTP {status}: " + (f"[{codigo}] " if codigo else "") + str(mensaje))
        self.status, self.codigo, self.mensaje, self.question_id = status, codigo, mensaje, question_id


class ErrorTransporte(ChispaError):
    """No hubo respuesta válida tras todos los reintentos (red, 5xx, 429 o cuerpo ilegible)."""


_REINTENTABLES = {429, 500, 502, 503}
# Política igual que el cliente JS: el 503 se reintenta (respetando `Retry-After`, con backoff y tope), salvo el 503 de timeout del
# servidor (`error.code == "timeout"`, aunque traiga `Retry-After`) y el 504: repetirlos vuelve a gastar la cascada entera.
_TOPE_RETRY_AFTER = 30.0


def _es_timeout(e, texto: str) -> bool:
    if e.code == 504:
        return True
    try:
        err = json.loads(texto).get("error")
    except (ValueError, AttributeError):
        return False
    return e.code == 503 and isinstance(err, dict) and err.get("code") == "timeout"


def _retry_after(e) -> float | None:
    v = e.headers.get("Retry-After") if e.headers is not None else None
    try:
        return min(max(float(v), 0.0), _TOPE_RETRY_AFTER) if v is not None else None
    except ValueError:
        return None  # fecha HTTP u otra cosa: se trata como ausente


class Chispa:
    """`Chispa("http://127.0.0.1:8090").decidir(estado, [Choice(...), Noul(...), Score(...)])`.

    Con `nonce_auto` (por defecto) cada pregunta sin nonce recibe un uuid fijado antes del primer intento:
    el servidor lo usa como clave de idempotencia, así que un reintento tras un corte no vuelve a decidir.
    """

    def __init__(self, url: str, *, timeout: float = 10.0, reintentos: int = 3, espera: float = 0.2,
                 nonce_auto: bool = True, dormir=time.sleep):
        self.url = url.rstrip("/")
        self.timeout, self.reintentos, self.espera, self.nonce_auto = timeout, reintentos, espera, nonce_auto
        self._dormir = dormir

    def decidir(self, estado: str, preguntas: Sequence[Pregunta]) -> List[Resultado]:
        """Resultados en el orden de `preguntas`."""
        preguntas = list(preguntas)
        if not preguntas:
            raise ValueError("sin preguntas")
        if len({p.id for p in preguntas}) != len(preguntas):
            raise ValueError("ids de pregunta repetidos")
        if self.nonce_auto:
            preguntas = [p if p.nonce is not None else replace(p, nonce=uuid.uuid4().hex) for p in preguntas]
        cuerpo = json.dumps({"state": estado, "questions": [p.a_json() for p in preguntas]}).encode()
        resp = self._post("/v1/decide", cuerpo)
        try:
            res = [Resultado.de_json(r) for r in resp["results"]]
        except (KeyError, TypeError) as e:
            raise ErrorTransporte(f"respuesta fuera del contrato: {e!r}") from e
        if [r.id for r in res] != [p.id for p in preguntas]:
            raise ErrorTransporte("la respuesta no trae las preguntas en orden")
        return res

    def salud(self) -> bool:
        try:
            return self._post("/healthz", None).get("status") == "ok"
        except ChispaError:
            return False

    def _post(self, ruta: str, cuerpo):
        req = urllib.request.Request(self.url + ruta, data=cuerpo, method="POST" if cuerpo is not None else "GET",
                                     headers={"Content-Type": "application/json"} if cuerpo is not None else {})
        ultimo, pedida = None, 0.0
        for intento in range(self.reintentos + 1):
            if intento:
                self._dormir(max(self.espera * 2 ** (intento - 1), pedida))
            pedida = 0.0
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                texto = e.read().decode("utf-8", "replace")
                ra = _retry_after(e)
                if e.code not in _REINTENTABLES or _es_timeout(e, texto):
                    try:
                        texto = json.loads(texto).get("error", texto)
                    except (ValueError, AttributeError):
                        pass
                    raise ErrorSolicitud(e.code, texto) from None  # str (formato viejo) o dict (tipado)
                ultimo, pedida = f"HTTP {e.code}", ra or 0.0
            except (urllib.error.URLError, OSError, ValueError) as e:  # ValueError: JSON ilegible
                ultimo = repr(e)
        raise ErrorTransporte(f"{self.url}{ruta}: {ultimo} tras {self.reintentos + 1} intentos")
