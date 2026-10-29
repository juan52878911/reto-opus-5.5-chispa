"""Interfaz del codificador causal con caché y un codificador falso para probar el resto sin modelos."""
from abc import ABC, abstractmethod

import numpy as np


class Sesion(ABC):
    """Estado compartido de un flujo de audio. Se codifica una vez; las preguntas leen `vector`."""

    @abstractmethod
    def empujar(self, fotogramas):
        """fotogramas (T, n_mels) → vector (dim,) float32 de norma 1 con el estado tras T fotogramas más."""


class Codificador(ABC):
    dim: int
    n_mels: int
    fotogramas_por_trozo: int  # el modelo real se invoca cada trozo (p. ej. 32 = 320 ms)

    @abstractmethod
    def abrir(self):
        """Nueva Sesion con estado vacío (un flujo = una llamada)."""


class _SesionFalsa(Sesion):
    def __init__(self, cod):
        self.cod, self.media, self.n = cod, np.zeros(cod.n_mels, np.float64), 0

    def empujar(self, fotogramas):
        for fila in np.asarray(fotogramas, dtype=np.float64):  # media móvil exponencial: causal
            self.n += 1
            a = max(self.cod.alfa, 1.0 / self.n)
            self.media += a * (fila - self.media)
        return self.cod.proyectar(self.media)


class CodificadorFalso(Codificador):
    """Proyección aleatoria fija (semilla) de la media móvil del log-mel. Sin entrenar ni aprender nada."""

    def __init__(self, dim=32, n_mels=64, fotogramas_por_trozo=32, alfa=0.05, semilla=7):
        self.dim, self.n_mels, self.fotogramas_por_trozo, self.alfa = dim, n_mels, fotogramas_por_trozo, alfa
        self._w = np.random.default_rng(semilla).standard_normal((n_mels, dim))

    def proyectar(self, media):
        v = (media - media.mean()) @ self._w  # restar la media global: el silencio y el volumen no dominan
        n = np.linalg.norm(v)
        if n < 1e-9:
            v = self._w[0].copy()
            n = np.linalg.norm(v)
        return (v / n).astype(np.float32)

    def abrir(self):
        return _SesionFalsa(self)
