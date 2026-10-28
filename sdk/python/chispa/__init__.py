"""SDK de Chispa: cliente de `/v1/decide` (solo biblioteca estándar) y `chispa train`."""
from .cliente import Chispa, ChispaError, ErrorSolicitud, ErrorTransporte
from .tipos import Choice, Noul, Opcion, Pregunta, Resultado, Score

__all__ = ["Chispa", "ChispaError", "ErrorSolicitud", "ErrorTransporte", "Choice", "Noul", "Score", "Pregunta",
           "Opcion", "Resultado", "entrenar"]
__version__ = "0.1.0"


def entrenar(*args, **kw):
    """`chispa.train.entrenar`, importado al usarlo (el cliente no carga nada de entrenamiento)."""
    from .train import entrenar as f
    return f(*args, **kw)
