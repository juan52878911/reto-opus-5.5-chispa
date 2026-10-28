"""Escritor mínimo de `.chispa` v3 en Python (espejo de `format/chispa3.Escribir`).

Solo se usa si no hay Go: permite dejar META, L1 y CALIB sin L0. El lector oficial es el de Go."""
from __future__ import annotations

import hashlib
import json
import struct
from typing import Dict

META, L0, L1, L2, ESQUEMAS, CALIB = 1, 2, 3, 4, 5, 6
MAGIA = b"\x89CHI\r\n\x1a\n"


def _tabla_crc32c():
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0x82F63B78 if c & 1 else c >> 1
        t.append(c)
    return t


_T = _tabla_crc32c()


def crc32c(b: bytes) -> int:
    c = 0xFFFFFFFF
    for x in b:
        c = _T[(c ^ x) & 0xFF] ^ (c >> 8)
    return c ^ 0xFFFFFFFF


def escribir(secciones: Dict[int, bytes]) -> bytes:
    tipos = sorted(secciones)
    tabla, datos, fin = b"", bytearray(), 0
    for t in tipos:
        ini = (fin + 15) & ~15
        datos += b"\0" * (ini - fin) + secciones[t]
        fin = ini + len(secciones[t])
        tabla += struct.pack("<IIQQ", t, 0, ini, len(secciones[t])) + hashlib.sha256(secciones[t]).digest()
    total = 32 + len(tabla) + fin

    def cab(crc):
        return MAGIA + struct.pack("<HHIQI", 3, 0, len(tipos), total, crc) + b"\0" * 4

    crc = crc32c(cab(0) + tabla)
    return cab(crc) + tabla + bytes(datos)


def meta(tareas, licencias=None, dorado="") -> bytes:
    return json.dumps({"version": 1, "tareas": list(tareas), "licencias": licencias or {}, "dorado": dorado}).encode()


def calib(tipos: dict, tau_escalate: float) -> bytes:
    return json.dumps({"tipos": tipos, "tau_escalate": tau_escalate}).encode()
