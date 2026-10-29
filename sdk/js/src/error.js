/**
 * Error del cliente. `codigo` es el `error.code` del servidor (invalid_kind, field_too_long…) o uno propio:
 * `network_error`, `timeout`, `bad_response`. `status` es el HTTP, o 0 si no hubo respuesta o falló la validación local.
 */
export class ErrorChispa extends Error {
  constructor({ codigo, mensaje, idPregunta, status = 0, retryAfterMs, cause }) {
    super(`${codigo ? `[${codigo}] ` : ""}${mensaje}`, cause === undefined ? undefined : { cause });
    this.name = "ErrorChispa";
    this.codigo = codigo;
    this.mensaje = mensaje;
    this.idPregunta = idPregunta;
    this.status = status;
    this.retryAfterMs = retryAfterMs; // Retry-After numérico (503, 429…) con tope de 30 s; undefined si no vino
  }
}
