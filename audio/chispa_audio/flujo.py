"""Streaming: muestras → log-mel → codificador → cabeza, con compuerta de silencio y acuerdo de k lecturas."""
from dataclasses import dataclass

import numpy as np

from .cabeza import Cabeza
from .logmel import LogMel, LogMelFlujo


@dataclass
class Lectura:
    t_ms: float          # instante de audio al final del trozo
    resultados: list     # un Resultado por pregunta, en orden


class Flujo:
    """Una llamada. `empujar(muestras)` devuelve una Lectura por cada trozo completo de audio.

    `decision(i)` solo da respuesta si las últimas `acuerdo` lecturas de la pregunta i coinciden y
    ninguna escaló (seguridad al actuar, al estilo DJ R3X); si no, None.
    """

    def __init__(self, codificador, cabeza, preguntas, acuerdo=3, umbral_silencio=-15.0, logmel=None):
        self.cod, self.cabeza, self.preguntas, self.acuerdo = codificador, cabeza, list(preguntas), acuerdo
        self.umbral_silencio = umbral_silencio  # log-mel (banda máxima, media en el trozo) por debajo del cual no hay señal
        self.lm = logmel or LogMel(n_mels=codificador.n_mels)
        self._mel, self._ses = LogMelFlujo(self.lm), codificador.abrir()
        self._pend = np.zeros((0, codificador.n_mels), np.float32)
        self._fotogramas = 0
        self.lecturas = []

    def empujar(self, muestras):
        nuevas = []
        self._pend = np.concatenate([self._pend, self._mel.empujar(muestras)])
        k = self.cod.fotogramas_por_trozo
        while len(self._pend) >= k:
            trozo, self._pend = self._pend[:k], self._pend[k:]
            self._fotogramas += k
            v = self._ses.empujar(trozo)  # el estado avanza aunque el trozo sea silencio
            if float(trozo.max(axis=1).mean()) < self.umbral_silencio:
                res = [Cabeza.sin_opinion(q) for q in self.preguntas]
            else:
                res = self.cabeza.decidir_lote(v, self.preguntas)
            nuevas.append(Lectura(self._fotogramas * self.lm.salto / 16.0, res))
        self.lecturas += nuevas
        return nuevas

    def decision(self, i):
        ult = self.lecturas[-self.acuerdo:]
        if len(ult) < self.acuerdo or any(l.resultados[i].escalate for l in ult):
            return None
        resp = {l.resultados[i].answer for l in ult}
        return ult[-1].resultados[i].answer if len(resp) == 1 else None
