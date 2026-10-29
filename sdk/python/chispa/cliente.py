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

    def __init__(self, status: int, mensaje, codigo: str = "", question_id=None, retry_after: float | None = None):
        if isinstance(mensaje, dict):
            codigo = mensaje.get("code", codigo) or ""
            question_id = mensaje.get("question_id", question_id)
            mensaje = mensaje.get("message", "")
        super().__init__(f"HTTP {status}: " + (f"[{codigo}] " if codigo else "") + str(mensaje))
        self.status, self.codigo, self.mensaje, self.question_id = status, codigo, mensaje, question_id
        self.retry_after = retry_after  # segundos de `Retry-After` (tope 30 s) si el servidor lo mandó; en un 429, cuánto esperar


class ErrorTransporte(ChispaError):
    """No hubo respuesta válida tras todos los reintentos (red, 5xx, 429 o cuerpo ilegible)."""


# POLÍTICA DE REINTENTOS (única fuente; `docs/05-sdks.md` la describe y el cliente JS debe igualarla):
#  - se reintenta: error de red (conexión rechazada, cortada, respuesta ilegible) y 503 que no sea de timeout, con backoff
#    exponencial `espera * 2**(n-1)` y, si trae `Retry-After` en segundos, al menos esa espera (tope 30 s);
#  - NO se reintenta: el timeout propio del cliente (el servidor cancela y no guarda nada bajo el nonce, así que repetir
#    vuelve a gastar la cascada entera), el 503 `timeout` del servidor (aunque traiga `Retry-After`), el 504 y cualquier
#    otro estado (400, 405, 413, 429, 500, 502…): se lanza `ErrorSolicitud` en el acto;
#  - 401 (clave de API ausente o mala) y 429 (`rate_limited`) NO se reintentan: se lanza `ErrorSolicitud` en el acto. Un 401
#    no se arregla repitiendo; en un 429 `ErrorSolicitud.retry_after` trae los segundos que pidió el servidor y decide el llamador;
#  - el `timeout` por defecto (35 s) es mayor que el `-timeout` del servidor (30 s): el 503 del servidor llega antes de cortar.
_REINTENTABLES = {503}
_TOPE_RETRY_AFTER = 30.0
TIMEOUT_POR_DEFECTO = 35.0


def _es_timeout_propio(e: BaseException) -> bool:
    return isinstance(e, TimeoutError) or (isinstance(e, urllib.error.URLError) and isinstance(e.reason, TimeoutError))


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


def _validar_clave(api_key):
    """Quita el salto de línea final (clave leída de un fichero) y exige ASCII imprimible sin espacios. El error no incluye la clave."""
    if not api_key:
        return None
    if not isinstance(api_key, str):
        raise ValueError("api_key debe ser una cadena")
    api_key = api_key.rstrip("\r\n")
    if not api_key or not all(33 <= ord(c) <= 126 for c in api_key):
        raise ValueError("api_key inválida: debe ser ASCII imprimible, sin espacios ni caracteres de control (la clave no se muestra)")
    return api_key


class Chispa:
    """`Chispa("http://127.0.0.1:8090").decidir(estado, [Choice(...), Noul(...), Score(...)])`.

    Con `nonce_auto` (por defecto) cada pregunta sin nonce recibe un uuid fijado antes del primer intento:
    el servidor lo usa como clave de idempotencia, así que un reintento tras un corte no vuelve a decidir.
    Un nonce vacío cuenta como ausente (se genera uno). `api_key` (opcional) se envía como `Authorization: Bearer <clave>`
    si el servidor tiene `api_keys`; un 401 o 429 lanza `ErrorSolicitud` sin reintentar. Política de reintentos: ver el comentario sobre `_REINTENTABLES`.
    """

    def __init__(self, url: str, *, timeout: float = TIMEOUT_POR_DEFECTO, reintentos: int = 3, espera: float = 0.2,
                 nonce_auto: bool = True, dormir=time.sleep, api_key: str | None = None):
        self.url = url.rstrip("/")
        self.timeout, self.reintentos, self.espera, self.nonce_auto = timeout, reintentos, espera, nonce_auto
        self._dormir = dormir
        self.api_key = _validar_clave(api_key)  # clave en claro; viaja como `Authorization: Bearer` solo en /v1/decide

    def __repr__(self) -> str:
        return f"Chispa(url={self.url!r}, api_key={'***' if self.api_key else None})"  # nunca la clave

    def decidir(self, estado: str, preguntas: Sequence[Pregunta]) -> List[Resultado]:
        """Resultados en el orden de `preguntas`."""
        preguntas = list(preguntas)
        if not preguntas:
            raise ValueError("sin preguntas")
        if len({p.id for p in preguntas}) != len(preguntas):
            raise ValueError("ids de pregunta repetidos")
        if self.nonce_auto:
            preguntas = [p if p.nonce else replace(p, nonce=uuid.uuid4().hex) for p in preguntas]
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
        cab = {"Content-Type": "application/json"} if cuerpo is not None else {}
        if self.api_key and ruta == "/v1/decide":
            cab["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(self.url + ruta, data=cuerpo, method="POST" if cuerpo is not None else "GET", headers=cab)
        ultimo, pedida = None, 0.0
        for intento in range(self.reintentos + 1):
            if intento:
                self._dormir(max(self.espera * 2 ** (intento - 1), pedida))
            pedida = 0.0
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    crudo = r.read()
                try:
                    return json.loads(crudo)
                except ValueError as e:  # JSON ilegible: el único ValueError que se reintenta
                    ultimo = repr(e)
                    continue
            except urllib.error.HTTPError as e:
                texto = e.read().decode("utf-8", "replace")
                ra = _retry_after(e)
                if e.code not in _REINTENTABLES or _es_timeout(e, texto):
                    try:
                        texto = json.loads(texto).get("error", texto)
                    except (ValueError, AttributeError):
                        pass
                    raise ErrorSolicitud(e.code, texto, retry_after=ra) from None  # str (formato viejo) o dict (tipado)
                ultimo, pedida = f"HTTP {e.code}", ra or 0.0
            except (urllib.error.URLError, OSError) as e:
                if _es_timeout_propio(e):
                    raise ErrorTransporte(f"{self.url}{ruta}: {e!r}: sin respuesta en {self.timeout} s (no se reintenta)") from e
                ultimo = repr(e)
        raise ErrorTransporte(f"{self.url}{ruta}: {ultimo} tras {self.reintentos + 1} intentos")
