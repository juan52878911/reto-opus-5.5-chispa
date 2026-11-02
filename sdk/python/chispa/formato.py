"""Escritor mínimo de `.chispa` v3 en Python (espejo de `format/chispa3.Escribir`).

Solo se usa si no hay Go: permite dejar META, L1 y CALIB sin L0. El lector oficial es el de Go."""
from __future__ import annotations

import hashlib
import json
import struct
from typing import Dict

META, L0, L1, L2, ESQUEMAS, CALIB, CONJ, L0TF, TORR, SOPL1 = 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
TIPOS = (META, L0, L1, L2, ESQUEMAS, CALIB, CONJ, L0TF, TORR, SOPL1)
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


TEXTOS_TORRE = ("v1", "v2_sin_id")  # META.texto_torre (ausente = v1)
_HEX = frozenset("0123456789abcdef")


def validar_texto_torre(v, origen="texto_torre") -> str:
    """`v` si es una versión conocida del texto de torre; ValueError claro si no."""
    if v not in TEXTOS_TORRE:
        raise ValueError(f"{origen} {v!r} desconocido (se esperaba {' o '.join(map(repr, TEXTOS_TORRE))})")
    return v


def meta(tareas, licencias=None, dorado="", texto_torre=None) -> bytes:
    """META como la valida Go (`chispa3.Meta`): `licencias` es un mapa de strings y `dorado` un sha256 hex (64 minúsculas) o vacío.
    `texto_torre` (opcional) solo se escribe si no es v1 (ausente = v1)."""
    licencias = {} if licencias is None else licencias
    if not isinstance(licencias, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in licencias.items()):
        raise ValueError("META.licencias debe ser un mapa de strings a strings (nombre → licencia), p. ej. {\"massive\": \"CC-BY\"}")
    if not isinstance(dorado, str) or (dorado and (len(dorado) != 64 or not set(dorado) <= _HEX)):
        raise ValueError(f"META.dorado debe ser un sha256 hex (64 caracteres en minúscula) o vacío, no {dorado!r}")
    d = {"version": 1, "tareas": list(tareas), "licencias": licencias, "dorado": dorado}
    if texto_torre is not None and validar_texto_torre(texto_torre) != "v1":
        d["texto_torre"] = texto_torre
    return json.dumps(d).encode()


def calib(tipos: dict, tau_escalate: float, tau_l2c=None, tau_l2_esquema_nuevo=None, l1_lambda_calib=None,
          tipos_l2=None, tau_escalate_l2=None) -> bytes:
    """`tipos_l2` y `tau_escalate_l2` (opcionales) son lo que leen L2 y L2c en lugar de `tipos` y `tau_escalate`; L1 lee siempre los suyos."""
    d = {"tipos": tipos, "tau_escalate": tau_escalate}
    if tipos_l2 is not None:
        d["tipos_l2"] = tipos_l2
    if tau_escalate_l2 is not None:
        d["tau_escalate_l2"] = tau_escalate_l2
    if tau_l2c is not None:
        d["tau_l2c"] = tau_l2c
    if tau_l2_esquema_nuevo is not None:
        d["tau_l2_esquema_nuevo"] = tau_l2_esquema_nuevo
    if l1_lambda_calib is not None:  # λ de SOPL1 con el que se calibró el τ de L1; ausente = calibrado sin encogimiento
        d["l1_lambda_calib"] = l1_lambda_calib
    return json.dumps(d).encode()


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
        if t not in TIPOS:
            raise ValueError(f"tipo de sección {t} desconocido")
        out[t] = b
    return out


# --- CONJ (ver format/chispa3/conj.go para la disposición) ---
CONJ_VERSION, CONJ_VERSION2, CABEZA_LR = 1, 2, 1
ESQUEMAS_VERSION2 = 2


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


def hash_esquema2(pregunta: str, kind: str, opciones) -> bytes:
    """`chispa3.HashEsquema2`: sha256(pregunta · 0x1f · kind · 0x1f · por cada opción ordenada por id (orden de bytes):
    id · 0x1e · descripción · 0x1d), 16 primeros bytes. `opciones`: pares (id, descripción) en cualquier orden."""
    h = hashlib.sha256()
    h.update(pregunta.encode("utf-8") + b"\x1f" + kind.encode("utf-8") + b"\x1f")
    for i, d in sorted(((i.encode("utf-8"), d.encode("utf-8")) for i, d in opciones), key=lambda o: o[0]):
        h.update(i + b"\x1e" + d + b"\x1d")
    return h.digest()[:16]


def version_esquemas(b: bytes) -> int:
    """Versión (1 o 2) de una sección ESQUEMAS por su primera palabra (versión<<16 | dim; v1 lleva 0 arriba). Ilegible o corta: 1."""
    return ESQUEMAS_VERSION2 if len(b) >= 4 and struct.unpack_from("<I", b)[0] >> 16 == ESQUEMAS_VERSION2 else 1


def esquemas(dim: int, entradas, version: int = 1) -> bytes:
    """Sección ESQUEMAS (`chispa3.CodificarEsquemas`/`CodificarEsquemas2`). Cada entrada: dict con `hash` (32 bytes en v1,
    16 en v2), `escala` y `vec` (dim) int8. v2: la primera palabra es versión<<16 | dim. Se ordenan por hash."""
    import numpy as np
    if version not in (1, ESQUEMAS_VERSION2) or not 0 < dim <= 4096:
        raise ValueError("ESQUEMAS: versión o dim fuera de rango")
    ancho = 32 if version == 1 else 16
    es = sorted(entradas, key=lambda e: e["hash"])
    for a, b in zip(es, es[1:]):
        if a["hash"] == b["hash"]:
            raise ValueError("ESQUEMAS: hash repetido")
    vecs = [np.ascontiguousarray(e["vec"], dtype=np.int8) for e in es]
    if any(len(e["hash"]) != ancho or v.shape != (dim,) or not e["escala"] >= 0 or e["escala"] == float("inf")
           for e, v in zip(es, vecs)):
        raise ValueError("ESQUEMAS: entrada mal formada")
    out = [struct.pack("<II", (0 if version == 1 else version) << 16 | dim, len(es))]
    out += [e["hash"] for e in es]
    out.append(np.array([e["escala"] for e in es], dtype="<f4").tobytes())
    out += [v.tobytes() for v in vecs]
    return b"".join(out)


def cuantizar_protos(P):
    """P (C,K,d) float, una ranura por fila → (escala (C,K) f32, proto (C,K,d) int8) con escala = máx|x|/127."""
    import numpy as np
    P = np.asarray(P, dtype=np.float64)
    m = np.abs(P).max(axis=-1)
    esc = np.where(m > 0, m / 127.0, 1.0)
    q = np.clip(np.rint(P / esc[..., None]), -127, 127).astype(np.int8)
    return esc.astype(np.float32), q


def conj(entradas, version: int = CONJ_VERSION) -> bytes:
    """Sección CONJ (`version` 1: hash de 32 bytes, `clave_conj`; 2: hash de 16 bytes, `hash_esquema2`). Cada entrada: dict con `hash`, `T`, `beta`, `esc` (3), `w` (6), `clases` (estrictamente
    crecientes), `escala` (C,K) y `proto` (C,K,d) int8. Se ordenan por hash."""
    import numpy as np
    if version not in (CONJ_VERSION, CONJ_VERSION2):
        raise ValueError("CONJ: versión desconocida")
    ancho = 32 if version == CONJ_VERSION else 16
    out = [struct.pack("<II", version, len(entradas))]
    previo = None
    for e in sorted(entradas, key=lambda e: e["hash"]):
        if previo is not None and previo == e["hash"]:
            raise ValueError("CONJ: hash repetido")
        previo = e["hash"]
        proto = np.ascontiguousarray(e["proto"], dtype=np.int8)
        c, k, d = proto.shape
        if len(e["hash"]) != ancho or len(e["clases"]) != c or len(e["esc"]) != 3 or len(e["w"]) != 6:
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


# --- L0TF (ver format/chispa3/l0tf.go para la disposición) ---
L0TF_VERSION = 1


def l0tf(etiquetas, vocab, idf, inter, coef, f16=False) -> bytes:
    """Sección L0TF. `vocab`: n-gramas (2 a 5 puntos de código) en cualquier orden; `idf` (V,), `coef` (V,C) en el mismo
    orden que `vocab`; `inter` (C,); `etiquetas` estrictamente crecientes. Reordena el vocabulario por bytes UTF-8."""
    import numpy as np
    coef, idf, inter = np.asarray(coef), np.asarray(idf, dtype="<f4"), np.asarray(inter, dtype="<f4")
    v, c = coef.shape
    if len(vocab) != v or idf.shape != (v,) or inter.shape != (c,) or len(etiquetas) != c or c < 2:
        raise ValueError("L0TF mal formada")
    if any(a >= b for a, b in zip(etiquetas, etiquetas[1:])):
        raise ValueError("L0TF: etiquetas no crecientes")
    bs = [g.encode("utf-8") for g in vocab]
    orden = sorted(range(v), key=bs.__getitem__)
    bs = [bs[i] for i in orden]
    if len(set(bs)) != v or any(not 2 <= len(g.decode("utf-8")) <= 5 for g in bs):
        raise ValueError("L0TF: vocabulario repetido o con n-gramas fuera de 2 a 5 caracteres")
    orden = np.array(orden)
    coef = np.ascontiguousarray(coef[orden], dtype="<f2" if f16 else "<f4")
    out = [struct.pack("<IIII", L0TF_VERSION, v, c, 2 if f16 else 1)]
    for n in etiquetas:
        b = n.encode("utf-8")
        out.append(struct.pack("<H", len(b)) + b)
    out.append(inter.tobytes())
    out.append(np.ascontiguousarray(idf[orden]).tobytes())
    out.append(np.concatenate([[0], np.cumsum([len(g) for g in bs])]).astype("<u4").tobytes())
    out.append(b"".join(bs))
    out.append(coef.tobytes())
    return b"".join(out)


# --- TORR (ver format/chispa3/torr.go para la disposición) ---
TORR_VERSION = 1
TORR_PREFIJO_POR_VERSION = {1: "passage: "}  # regla por versión: una versión futura añade su fila
TORR_MAX_LEN_MIN = 3  # `chispa3.MaxLenMin`: <s>, al menos un token y </s>
TORR_MAX_LEN_TOPE = 512  # `chispa3.MaxLenTope` / `runtime/tok.TopeMaxLen`: e5-small tiene 512 posiciones; por encima, error


def validar_prefijo_torr(version: int, prefijo: str) -> None:
    """Lanza ValueError si `version` es desconocida o `prefijo` no es el que esa versión exige."""
    if version not in TORR_PREFIJO_POR_VERSION:
        raise ValueError(f"TORR v{version}: versión desconocida")
    esperado = TORR_PREFIJO_POR_VERSION[version]
    if prefijo != esperado:
        raise ValueError(f"TORR v{version}: prefijo {prefijo!r} no válido; se espera {esperado!r}")


def torr(onnx: bytes, dim: int = 256, max_len: int = 128, prefijo: str = "passage: ") -> bytes:
    """Sección TORR: u32 versión(1) · u32 dim · u32 max_len · u32 len_prefijo · prefijo UTF-8 · ONNX (`chispa3.CodificarTORR`)."""
    p = prefijo.encode("utf-8")
    if not 0 < dim <= 4096 or not TORR_MAX_LEN_MIN <= max_len <= TORR_MAX_LEN_TOPE or len(p) > 256 or not onnx:
        raise ValueError(f"TORR mal formada (dim={dim}, max_len={max_len}: se exige {TORR_MAX_LEN_MIN}..{TORR_MAX_LEN_TOPE})")
    return struct.pack("<IIII", TORR_VERSION, dim, max_len, len(p)) + p + onnx


def leer_torr(b: bytes) -> dict:
    """Inversa de `torr` (`chispa3.DecodificarTORR`): {dim, max_len, prefijo, onnx}."""
    if len(b) < 16:
        raise ValueError("TORR truncada")
    ver, dim, ml, n = struct.unpack("<IIII", b[:16])
    if ver != TORR_VERSION or not 0 < dim <= 4096 or not TORR_MAX_LEN_MIN <= ml <= TORR_MAX_LEN_TOPE or n > 256 or len(b) <= 16 + n:
        raise ValueError("TORR inválida")
    return {"dim": dim, "max_len": ml, "prefijo": b[16:16 + n].decode("utf-8"), "onnx": b[16 + n:]}


# --- SOPL1 (ver format/chispa3/sopl1.go para la disposición) ---
SOPL1_VERSION = 1   # sin normas
SOPL1_VERSION2 = 2  # cada entrada añade u32 K · C×K×f32 normas de la media sin normalizar de L2c (K = 0: sin normas)
SOPL1_VERSION3 = 3  # la 2 y cada entrada añade u32 M · M×u32 n_l2 (M = 0: sin n_l2; si no M = C): n del soporte de CONJ por clase
SOPL1_MAX_K = 256


def clave_conj(pregunta: str, ids) -> bytes:
    """`chispa3.ClaveConj`: HashEsquema de la pregunta y los ids ordenados (la clave de CONJ y de SOPL1)."""
    return hash_esquema(pregunta, sorted(ids))


def cuantizar_media(M):
    """M (C,d) float → (escala (C,) f32, media (C,d) int8) con escala = máx|x|/127 en float32 y redondeo a par,
    como `chispa3.CuantizarMedia`. Una fila de ceros lleva escala 0."""
    import numpy as np
    M = np.asarray(M, dtype=np.float32)
    mx = np.abs(M).max(axis=-1)
    esc = (mx / np.float32(127)).astype(np.float32)
    seguro = np.where(esc > 0, esc, np.float32(1))
    q = np.clip(np.rint(M / seguro[:, None]), -127, 127).astype(np.int8)
    q[esc == 0] = 0
    return esc, q


def _validar_sopl1_escala(esc):
    """Como `EntradaSopl1.validar`: cada escala es finita y ≥ 0 (NaN, ∞ y negativas se rechazan)."""
    import numpy as np
    a = np.asarray(esc, dtype=np.float32)
    if not np.all(np.isfinite(a) & (a >= 0)):
        raise ValueError("SOPL1: escala no finita o negativa")


def sopl1(dim: int, entradas) -> bytes:
    """Sección SOPL1: soporte few-shot por pregunta (k y media int8 de los embeddings de L1 por opción). Cada entrada:
    dict con `hash` (32 bytes, `clave_conj`), `ids` (estrictamente crecientes), `k` (C,), `escala` (C,) y `media` (C,dim) int8.
    Opcional `normas` (C,K) float: norma de cada ranura de la media SIN normalizar de L2c (‖(1/n)·Σ S_i,j‖ ≤ 1); con normas en alguna
    entrada la sección es la versión 2 (las entradas sin ellas llevan K = 0), si no es la versión 1 de siempre. Opcional `n_l2` (C,) enteros:
    ejemplos del soporte de CONJ por clase (el n de modelo.py, puede ser < k); con n_l2 en alguna entrada la sección es la versión 3 (0 = sin dato:
    L2c usa k). Se ordenan por hash."""
    import numpy as np
    if not 0 < dim <= 4096:
        raise ValueError("SOPL1: dim fuera de rango")
    con_normas = any(e.get("normas") is not None for e in entradas)
    con_n = any(e.get("n_l2") is not None for e in entradas)
    ver = SOPL1_VERSION3 if con_n else SOPL1_VERSION2 if con_normas else SOPL1_VERSION
    con_normas = ver >= SOPL1_VERSION2
    out = [struct.pack("<III", ver, dim, len(entradas))]
    previo = None
    for e in sorted(entradas, key=lambda e: e["hash"]):
        if previo is not None and previo == e["hash"]:
            raise ValueError("SOPL1: hashes repetidos")
        previo = e["hash"]
        media = np.ascontiguousarray(e["media"], dtype=np.int8)
        c = len(e["ids"])
        if len(e["hash"]) != 32 or c < 1 or media.shape != (c, dim) or len(e["k"]) != c or len(e["escala"]) != c:
            raise ValueError("entrada de SOPL1 mal formada")
        if any(a >= b for a, b in zip(e["ids"], e["ids"][1:])):
            raise ValueError("SOPL1: ids no crecientes")
        _validar_sopl1_escala(e["escala"])
        out.append(e["hash"] + struct.pack("<I", c))
        for n in e["ids"]:
            b = n.encode("utf-8")
            out.append(struct.pack("<H", len(b)) + b)
        out.append(np.asarray(e["k"], dtype="<u4").tobytes())
        out.append(np.asarray(e["escala"], dtype="<f4").tobytes())
        out.append(media.tobytes())
        if con_normas:
            nm = e.get("normas")
            nm = np.zeros((c, 0), dtype="<f4") if nm is None else np.ascontiguousarray(nm, dtype="<f4")
            if nm.ndim != 2 or nm.shape[0] != c or nm.shape[1] > SOPL1_MAX_K or not np.all((nm >= 0) & (nm <= 1.001)):  # NaN falla ambas
                raise ValueError("SOPL1: normas mal formadas (C×K, en [0, 1])")
            out.append(struct.pack("<I", nm.shape[1]) + nm.tobytes())
        if con_n:
            nl = e.get("n_l2")
            if nl is None:
                out.append(struct.pack("<I", 0))
            else:
                nl = np.asarray(nl)
                if nl.shape != (c,) or np.any(nl < 0) or np.any(nl != np.floor(nl)) or np.any(nl >= 2 ** 32):
                    raise ValueError("SOPL1: n_l2 mal formado (C enteros ≥ 0)")
                out.append(struct.pack("<I", c) + nl.astype("<u4").tobytes())
    return b"".join(out)


def leer_sopl1(b: bytes) -> dict:
    """Inversa de `sopl1` (`chispa3.DecodificarSopl1`): {dim, entradas: [{hash, ids, k, escala, media, normas}]}; `normas` es (C,K) o None (versión 1 o K = 0)."""
    import numpy as np
    if len(b) < 12:
        raise ValueError("SOPL1 truncada")
    ver, dim, n = struct.unpack("<III", b[:12])
    if ver not in (SOPL1_VERSION, SOPL1_VERSION2, SOPL1_VERSION3) or not 0 < dim <= 4096:
        raise ValueError("SOPL1 inválida")
    pos, es = 12, []
    for _ in range(n):
        h, c = b[pos:pos + 32], struct.unpack("<I", b[pos + 32:pos + 36])[0]
        pos += 36
        ids = []
        for _ in range(c):
            ln = struct.unpack("<H", b[pos:pos + 2])[0]
            ids.append(b[pos + 2:pos + 2 + ln].decode("utf-8"))
            pos += 2 + ln
        k = np.frombuffer(b, "<u4", c, pos); pos += 4 * c
        esc = np.frombuffer(b, "<f4", c, pos); pos += 4 * c
        media = np.frombuffer(b, np.int8, c * dim, pos).reshape(c, dim); pos += c * dim
        normas = None
        if ver >= SOPL1_VERSION2:
            kk = struct.unpack("<I", b[pos:pos + 4])[0]
            pos += 4
            if kk > SOPL1_MAX_K:
                raise ValueError("SOPL1 inválida")
            if kk:
                normas = np.frombuffer(b, "<f4", c * kk, pos).reshape(c, kk); pos += 4 * c * kk
        n_l2 = None
        if ver == SOPL1_VERSION3:
            m = struct.unpack("<I", b[pos:pos + 4])[0]
            pos += 4
            if m not in (0, c):
                raise ValueError("SOPL1 inválida")
            if m:
                n_l2 = np.frombuffer(b, "<u4", c, pos); pos += 4 * c
        _validar_sopl1_escala(esc)
        if any(a >= b2 for a, b2 in zip(ids, ids[1:])):
            raise ValueError("SOPL1 inválida: ids no crecientes")
        if normas is not None and not np.all((normas >= 0) & (normas <= 1.001)):
            raise ValueError("SOPL1 inválida: norma de ranura fuera de [0, 1.001] o NaN")
        if es and es[-1]["hash"] >= h:
            raise ValueError("SOPL1 inválida: hashes no crecientes")
        es.append({"hash": h, "ids": ids, "k": k, "escala": esc, "media": media, "normas": normas, "n_l2": n_l2})
    if pos != len(b):
        raise ValueError("SOPL1 con bytes sobrantes")
    return {"dim": dim, "entradas": es}
