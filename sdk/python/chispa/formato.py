"""Escritor mínimo de `.chispa` v3 en Python (espejo de `format/chispa3.Escribir`).

Solo se usa si no hay Go: permite dejar META, L1 y CALIB sin L0. El lector oficial es el de Go."""
from __future__ import annotations

import hashlib
import json
import struct
from typing import Dict

META, L0, L1, L2, ESQUEMAS, CALIB, CONJ = 1, 2, 3, 4, 5, 6, 7
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


def leer(datos: bytes) -> Dict[int, bytes]:
    """Secciones de un `.chispa` v3 (comprueba cabecera, CRC, tabla y sha256). El lector oficial es el de Go."""
    if datos[:8] != MAGIA or len(datos) < 32:
        raise ValueError("no es un .chispa")
    ver, banderas, n, total, crc = struct.unpack("<HHIQI", datos[8:28])
    if ver != 3 or banderas or total != len(datos) or not 0 < n <= 64 or 32 + 56 * n > total:
        raise ValueError("cabecera .chispa v3 inválida")
    tabla = datos[32:32 + 56 * n]
    if crc32c(datos[:24] + b"\0" * 4 + datos[28:32] + tabla) != crc:
        raise ValueError("crc de cabecera/tabla incorrecto")
    base, out = 32 + 56 * n, {}
    for i in range(n):
        t, _, off, ln = struct.unpack("<IIQQ", tabla[56 * i:56 * i + 24])
        if base + off + ln > total:
            raise ValueError("sección fuera del fichero")
        b = datos[base + off:base + off + ln]
        if hashlib.sha256(b).digest() != tabla[56 * i + 24:56 * i + 56]:
            raise ValueError("sha256 de sección incorrecto")
        out[t] = b
    return out


# --- CONJ (ver format/chispa3/conj.go para la disposición) ---
CONJ_VERSION, CABEZA_LR = 1, 1


def hash_esquema(pregunta: str, opciones) -> bytes:
    """`chispa3.HashEsquema`. Para CONJ las opciones van ordenadas por id (lo hace el servidor)."""
    h = hashlib.sha256()

    def w(s):
        b = s.encode("utf-8")
        h.update(struct.pack("<Q", len(b)) + b)
    w(pregunta)
    h.update(struct.pack("<Q", len(opciones)))
    for o in opciones:
        w(o)
    return h.digest()


def cuantizar_protos(P):
    """P (C,K,d) float, una ranura por fila → (escala (C,K) f32, proto (C,K,d) int8) con escala = máx|x|/127."""
    import numpy as np
    P = np.asarray(P, dtype=np.float64)
    m = np.abs(P).max(axis=-1)
    esc = np.where(m > 0, m / 127.0, 1.0)
    q = np.clip(np.rint(P / esc[..., None]), -127, 127).astype(np.int8)
    return esc.astype(np.float32), q


def conj(entradas) -> bytes:
    """Sección CONJ. Cada entrada: dict con `hash` (32 bytes), `T`, `beta`, `esc` (3), `w` (6), `clases` (estrictamente
    crecientes), `escala` (C,K) y `proto` (C,K,d) int8. Se ordenan por hash."""
    import numpy as np
    out = [struct.pack("<II", CONJ_VERSION, len(entradas))]
    for e in sorted(entradas, key=lambda e: e["hash"]):
        proto = np.ascontiguousarray(e["proto"], dtype=np.int8)
        c, k, d = proto.shape
        if len(e["hash"]) != 32 or len(e["clases"]) != c or len(e["esc"]) != 3 or len(e["w"]) != 6:
            raise ValueError("entrada de CONJ mal formada")
        if any(a >= b for a, b in zip(e["clases"], e["clases"][1:])):
            raise ValueError("CONJ: clases no crecientes")
        out.append(e["hash"] + struct.pack("<IIIII", CABEZA_LR, k, d, c, 6))
        out.append(np.array([e["T"], e["beta"], *e["esc"], *e["w"]], dtype="<f4").tobytes())
        for n in e["clases"]:
            b = n.encode("utf-8")
            out.append(struct.pack("<H", len(b)) + b)
        out.append(np.ascontiguousarray(e["escala"], dtype="<f4").tobytes())
        out.append(proto.tobytes())
    return b"".join(out)
