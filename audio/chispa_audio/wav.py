"""Lectura y escritura de WAV PCM de 16 bits a 16 kHz con la biblioteca estándar."""
import io
import wave

import numpy as np

FS = 16000


class ErrAudio(ValueError):
    """El audio no cumple lo que espera Chispa (formato, frecuencia o contenido)."""


def leer_wav(origen, max_s=None):
    """Devuelve float32 mono en [-1, 1). `origen` es una ruta o bytes. Estéreo se promedia."""
    f = io.BytesIO(origen) if isinstance(origen, (bytes, bytearray)) else origen
    try:
        with wave.open(f, "rb") as w:
            canales, ancho, fs, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            if ancho != 2:
                raise ErrAudio(f"se espera PCM de 16 bits, no de {8 * ancho}")
            if fs != FS:
                raise ErrAudio(f"se espera {FS} Hz, no {fs} (la telefonía de 8 kHz se remuestrea antes)")
            if max_s is not None and n > max_s * FS:
                raise ErrAudio(f"el audio dura {n / FS:.1f} s y el tope es {max_s} s")
            crudo = w.readframes(n)
    except (wave.Error, EOFError) as e:
        raise ErrAudio(f"WAV ilegible: {e}") from e
    x = np.frombuffer(crudo, dtype="<i2").astype(np.float32) / 32768.0
    if canales > 1:
        x = x[: len(x) // canales * canales].reshape(-1, canales).mean(axis=1)
    return x.astype(np.float32)


def escribir_wav(x, destino=None):
    """Escribe float32 mono en [-1, 1] como WAV 16 kHz. Sin destino devuelve los bytes."""
    pcm = np.clip(np.round(np.asarray(x, dtype=np.float64) * 32768.0), -32768, 32767).astype("<i2")
    f = io.BytesIO() if destino is None else destino
    with wave.open(f, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FS)
        w.writeframes(pcm.tobytes())
    return f.getvalue() if destino is None else None
