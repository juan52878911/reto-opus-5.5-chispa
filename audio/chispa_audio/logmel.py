"""Log-mel en numpy. Causal: sin relleno centrado, el fotograma t solo ve muestras ya llegadas."""
import numpy as np

from .wav import FS


def _hz_a_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f, dtype=np.float64) / 700.0)


def _mel_a_hz(m):
    return 700.0 * (10.0 ** (np.asarray(m, dtype=np.float64) / 2595.0) - 1.0)


class LogMel:
    """Ventana de 25 ms, salto de 10 ms, FFT de 512, banco mel HTK de `n_mels` bandas."""

    def __init__(self, n_mels=64, n_fft=512, ventana=400, salto=160, fmin=50.0, fmax=7600.0, suelo=1e-10):
        if ventana > n_fft:
            raise ValueError("la ventana no cabe en la FFT")
        self.n_mels, self.n_fft, self.ventana, self.salto, self.suelo = n_mels, n_fft, ventana, salto, suelo
        self.pesos = np.hanning(ventana + 1)[:-1].astype(np.float64)  # hann periódica
        self.banco = self._banco(fmin, fmax)

    def _banco(self, fmin, fmax):
        frec = np.linspace(0, FS / 2, self.n_fft // 2 + 1)
        bordes = _mel_a_hz(np.linspace(_hz_a_mel(fmin), _hz_a_mel(fmax), self.n_mels + 2))
        b = np.zeros((self.n_mels, len(frec)))
        for i in range(self.n_mels):
            lo, c, hi = bordes[i : i + 3]
            b[i] = np.maximum(0, np.minimum((frec - lo) / (c - lo), (hi - frec) / (hi - c)))
        return b

    def n_fotogramas(self, n_muestras):
        return 0 if n_muestras < self.ventana else 1 + (n_muestras - self.ventana) // self.salto

    def calcular(self, x):
        """x: float mono → (T, n_mels) float32 de log(energía mel). T = 0 si x es más corto que la ventana."""
        x = np.asarray(x, dtype=np.float64)
        t = self.n_fotogramas(len(x))
        if t == 0:
            return np.zeros((0, self.n_mels), np.float32)
        idx = np.arange(self.ventana)[None, :] + self.salto * np.arange(t)[:, None]
        espectro = np.abs(np.fft.rfft(x[idx] * self.pesos, n=self.n_fft, axis=1)) ** 2
        return np.log(np.maximum(espectro @ self.banco.T, self.suelo)).astype(np.float32)


class LogMelFlujo:
    """Mismo cálculo por trozos: `empujar` devuelve solo los fotogramas nuevos."""

    def __init__(self, logmel=None):
        self.lm = logmel or LogMel()
        self._resto = np.zeros(0, np.float64)

    def empujar(self, muestras):
        buf = np.concatenate([self._resto, np.asarray(muestras, dtype=np.float64)])
        t = self.lm.n_fotogramas(len(buf))
        if t == 0:
            self._resto = buf
            return np.zeros((0, self.lm.n_mels), np.float32)
        usado = self.lm.salto * t  # lo que ya no hace falta: el siguiente fotograma empieza ahí
        self._resto = buf[usado:]
        return self.lm.calcular(buf[: usado - self.lm.salto + self.lm.ventana])
