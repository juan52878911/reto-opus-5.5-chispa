import zlib

import numpy as np


class PotionFalso:
    """Sustituye a StaticModel: bolsa de palabras con hash a 64 dimensiones (sin red ni modelo)."""

    def encode(self, textos):
        out = np.zeros((len(textos), 64), np.float32)
        for i, t in enumerate(textos):
            for w in t.lower().split():
                out[i, zlib.crc32(w.encode()) % 64] += 1
        return out
