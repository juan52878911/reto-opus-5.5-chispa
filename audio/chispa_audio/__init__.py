"""Jev de audio de Chispa (fase 5): esqueleto sin modelos. Ver audio/DISENO.md."""
from .wav import ErrAudio, leer_wav, escribir_wav, FS
from .logmel import LogMel, LogMelFlujo
from .codificador import Codificador, Sesion, CodificadorFalso
from .cabeza import Cabeza, Opcion, Pregunta, Resultado, ErrPregunta, TorresFalsas, CAPA_ESCALAR
from .flujo import Flujo, Lectura

__all__ = [n for n in dir() if not n.startswith("_")]
