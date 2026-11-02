"""`--torre <onnx>`: valida el ONNX de la torre de esquemas de L2 (model/l2/contrato-torre.md) y añade la sección TORR a un `.chispa`.

`onnx` y `onnxruntime` se importan solo aquí y solo si se pasa `--torre`."""
from __future__ import annotations

import math
import json
import os
import struct
from pathlib import Path
from typing import Callable

from . import formato
from .cliente import ChispaError

MAX_LEN_DEFECTO, PREFIJO_DEFECTO, OPSET_MIN = 128, "passage: ", 17
CLAVES_META = {"dim": ("chispa.torre.dim", "torre_dim", "dim"), "max_len": ("chispa.torre.max_len", "torre_max_len", "max_len"),
               "prefijo": ("chispa.torre.prefijo", "torre_prefijo", "prefijo")}


def _entero(v, nombre: str, origen: str, tope: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ChispaError(f"--torre: {nombre} de {origen} no es un entero: {v!r}")
    if not 0 < n <= tope:
        raise ChispaError(f"--torre: {nombre} de {origen} fuera de rango (1..{tope}): {n}")
    return n


def _resolver(campo, flag, props, defecto, convertir):
    """El flag explícito manda; si choca con los metadatos, error. Sin flag: metadatos y, si no, `defecto`."""
    meta = next((props[k] for k in CLAVES_META[campo] if k in props), None)
    meta = convertir(meta) if meta is not None else None
    if flag is not None:
        if meta is not None and meta != flag:
            raise ChispaError(f"--torre: --torre-{campo.replace('_', '-')} {flag!r} choca con los metadatos del ONNX ({meta!r})")
        return flag
    return meta if meta is not None else defecto


def validar_torre(ruta, dim=None, max_len=None, prefijo=None, log: Callable[[str], None] = print) -> dict:
    """Devuelve {dim, max_len, prefijo, onnx} listos para `formato.torr`, o lanza ChispaError diciendo qué no cumple."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ChispaError(f"--torre: no existe {ruta}")
    try:
        import onnx
        from onnx import TensorProto as TP
    except ImportError:
        raise ChispaError("--torre necesita el paquete `onnx` (pip install onnx) para validar el ONNX de la torre")
    datos = ruta.read_bytes()
    try:
        m = onnx.load_from_string(datos)
    except Exception as e:
        raise ChispaError(f"--torre: {ruta} no es un ONNX legible: {e}")
    fallos = []
    pesos = {x.name for x in m.graph.initializer}
    ent = {i.name: i for i in m.graph.input if i.name not in pesos}
    if sorted(ent) != ["attention_mask", "input_ids"]:
        fallos.append(f"las entradas deben ser exactamente input_ids y attention_mask (hay {sorted(ent)})")
    for n in ("input_ids", "attention_mask"):
        if n in ent:
            t = ent[n].type.tensor_type
            if t.elem_type != TP.INT64:
                fallos.append(f"la entrada {n} debe ser int64 (es {TP.DataType.Name(t.elem_type)})")
            if len(t.shape.dim) != 2:
                fallos.append(f"la entrada {n} debe tener rango 2 (tiene {len(t.shape.dim)})")
    salidas = [o.name for o in m.graph.output]
    dim_forma = None
    if "h" not in salidas:
        fallos.append(f"falta la salida h (hay {salidas})")
    else:
        t = next(o for o in m.graph.output if o.name == "h").type.tensor_type
        if t.elem_type != TP.FLOAT:
            fallos.append(f"la salida h debe ser float32 (es {TP.DataType.Name(t.elem_type)})")
        if len(t.shape.dim) != 2:
            fallos.append(f"la salida h debe ser (B, dim): rango {len(t.shape.dim)}")
        elif t.shape.dim[1].HasField("dim_value"):
            dim_forma = t.shape.dim[1].dim_value
    opset = max((o.version for o in m.opset_import if o.domain in ("", "ai.onnx")), default=0)
    if opset < OPSET_MIN:
        fallos.append(f"opset {opset} < {OPSET_MIN}")
    if fallos:
        raise ChispaError(f"--torre: {ruta} no cumple el contrato de la torre: " + "; ".join(fallos))

    props = {p.key: p.value for p in m.metadata_props}
    d = _resolver("dim", dim, props, None, lambda v: _entero(v, "dim", "los metadatos", 4096))
    if d is None:
        d = dim_forma
    elif dim_forma is not None and d != dim_forma:
        raise ChispaError(f"--torre: dim {d} choca con la forma de h del ONNX ({dim_forma})")
    if d is None:
        raise ChispaError("--torre: la salida h no tiene dim estática y el ONNX no la declara: pasa --torre-dim")
    ml = _resolver("max_len", max_len, props, MAX_LEN_DEFECTO, lambda v: _entero(v, "max_len", "los metadatos", 1 << 20))
    if ml > formato.TORR_MAX_LEN_TOPE:
        raise ChispaError(f"--torre: max_len {ml} > {formato.TORR_MAX_LEN_TOPE}: es el tope duro del tokenizador de e5 "
                          f"(el runtime trunca el pasaje a este max_len, que va en la sección TORR)")
    pf = _resolver("prefijo", prefijo, props, PREFIJO_DEFECTO, str)
    try:
        formato.validar_prefijo_torr(formato.TORR_VERSION, pf)
    except ValueError as e:
        raise ChispaError(f"--torre: {e}")
    try:
        formato.torr(datos, d, ml, pf)  # mismas cotas que el lector de Go
    except ValueError:
        raise ChispaError(f"--torre: parámetros fuera de rango (dim {d}, max_len {ml}, prefijo de {len(pf.encode())} bytes)")
    _probar(datos, d, log)
    tt = props.get("chispa.torre.texto_torre")  # ausente = v1
    if tt is not None and tt not in formato.TEXTOS_TORRE:
        raise ChispaError(f"--torre: chispa.torre.texto_torre {tt!r} del ONNX desconocido (se esperaba {' o '.join(map(repr, formato.TEXTOS_TORRE))})")
    return {"dim": d, "max_len": ml, "prefijo": pf, "onnx": datos, "texto_torre": tt or "v1"}


def _probar(datos: bytes, dim: int, log) -> None:
    """Inferencia de prueba con un lote de 2: forma (2, dim) y norma ≈ 1 (1e-3). Sin onnxruntime, avisa y sigue."""
    try:
        import numpy as np
        import onnxruntime as ort
    except ImportError:
        log("AVISO: sin onnxruntime: no se probó la inferencia de la torre (forma y norma de h)")
        return
    try:
        s = ort.InferenceSession(datos, providers=["CPUExecutionProvider"])
        ids = np.array([[0, 100, 2000, 2, 1, 1], [0, 7, 42, 99, 3, 2]], dtype=np.int64)
        mask = np.array([[1, 1, 1, 1, 0, 0], [1, 1, 1, 1, 1, 1]], dtype=np.int64)
        h = s.run(["h"], {"input_ids": ids, "attention_mask": mask})[0]
    except Exception as e:
        raise ChispaError(f"--torre: la inferencia de prueba falló: {e}")
    if h.shape != (2, dim):
        raise ChispaError(f"--torre: la inferencia de prueba da h de forma {tuple(h.shape)}, se esperaba (2, {dim})")
    for i, n in enumerate(np.linalg.norm(h.astype(np.float64), axis=1)):
        if not math.isfinite(n) or abs(n - 1.0) > 1e-3:
            raise ChispaError(f"--torre: h no está normalizada (norma {n:.5f} en la fila {i}, tolerancia 1e-3)")


def comprobar_dim_l2(secs: dict, dim: int) -> None:
    """Si el `.chispa` trae ESQUEMAS (L2), la dim de la torre debe ser la de sus ranuras (u32 inicial de ESQUEMAS)."""
    esq = secs.get(formato.ESQUEMAS)
    if esq is None:
        return
    if len(esq) < 4:
        raise ChispaError("--torre: la sección ESQUEMAS está truncada: no se puede comprobar su dim")
    # ESQUEMAS v1 empieza por dim; v2 por (2<<16 | dim): la versión va en los 16 bits altos.
    u = struct.unpack("<I", esq[:4])[0]
    if u >> 16 not in (0, 2):   # como DecodificarEsquemas: 1 en los bits altos no es válido
        raise ChispaError(f"--torre: versión de ESQUEMAS desconocida ({u >> 16})")
    dim_l2 = u & 0xFFFF
    if dim_l2 != dim:
        raise ChispaError(f"--torre: la dim de la torre ({dim}) no casa con la de L2/ESQUEMAS ({dim_l2})")


def descripciones_repetidas(opciones) -> dict:
    """{descripción (tras strip) → ids} de las opciones de una pregunta que comparten descripción (dos o más; las vacías no cuentan). Es
    la regla de texto de torre v2 (`runtime/torre.TextoOpcion`): esas opciones usan el texto v1, con id."""
    por = {}
    for o in opciones:
        d = o.description.strip()
        if d:
            por.setdefault(d, []).append(o.id)
    return {d: ids for d, ids in por.items() if len(ids) >= 2}


def avisar_descripciones_repetidas(opciones, version: str, log=print) -> None:
    """Avisa, con texto v2, de las descripciones repetidas de una pregunta (cuáles y qué opciones): esas opciones llevan el id en la torre."""
    if version != "v2_sin_id":
        return
    for d, ids in descripciones_repetidas(opciones).items():
        log(f"AVISO: descripción repetida en la pregunta ({', '.join(map(repr, ids))}: {d!r}); con texto_torre v2_sin_id esas opciones "
            "usan el texto v1 (con id) en la torre al vuelo")


def anadir_torr(salida, torre: dict, inf: dict, texto_torre=None) -> None:
    """Reescribe `salida` (.chispa v3) con TORR añadida. Paso común a los tres caminos: el entrenador de Go escribe el fichero
    entero, así que la sección se añade después, conservando las demás byte a byte; actualiza el informe."""
    salida = Path(salida)
    secs = formato.leer(salida.read_bytes())
    comprobar_dim_l2(secs, torre["dim"])
    texto = texto_torre or torre.get("texto_torre") or "v1"  # v2 escribe TORR v2; v1, TORR v1
    secs[formato.TORR] = formato.torr(torre["onnx"], torre["dim"], torre["max_len"], torre["prefijo"], texto)
    tmp = salida.with_name(salida.name + ".tmp")  # mismo directorio: os.replace es atómico
    try:
        tmp.write_bytes(formato.escribir(secs))
        os.replace(tmp, salida)
    finally:
        tmp.unlink(missing_ok=True)
    inf["bytes"] = salida.stat().st_size
    if "TORR" not in inf.get("secciones", []):
        inf.setdefault("secciones", []).append("TORR")
    inf["torre"] = {k: torre[k] for k in ("dim", "max_len", "prefijo")} | {"texto_torre": texto}


def texto_torre_de(secs: dict) -> str:
    """Versión del texto de torre de la META de un `.chispa` (`formato.leer`): ausente (o sin META) = v1; valor desconocido, ChispaError."""
    if formato.META not in secs:
        return "v1"
    try:
        v = json.loads(secs[formato.META]).get("texto_torre")
    except (ValueError, AttributeError) as e:
        raise ChispaError(f"el .chispa trae una META ilegible: {e}")
    if v is None:
        return "v1"
    if v not in formato.TEXTOS_TORRE:
        raise ChispaError(f"META.texto_torre {v!r} desconocido (se esperaba {' o '.join(map(repr, formato.TEXTOS_TORRE))})")
    return v


def resolver_texto_torre(l2=None, torre=None, flag=None, origen_l2="el l2.chispa") -> str:
    """Versión del texto de torre del `.chispa` final. `l2` y `torre` son las versiones de sus fuentes (None = no hay esa fuente); `flag` es
    `--texto-torre`. Si hay varias fuentes, deben coincidir (el servidor calcularía las torres con un texto distinto al que entrenó L2). Sin
    ninguna fuente que mande, `flag` o v1."""
    if flag is not None and flag not in formato.TEXTOS_TORRE:
        raise ChispaError(f"--texto-torre {flag!r} desconocido (se esperaba {' o '.join(map(repr, formato.TEXTOS_TORRE))})")
    fuentes = [(n, v) for n, v in ((origen_l2, l2), ("el ONNX de --torre (chispa.torre.texto_torre; ausente = v1)", torre),
                                   ("--texto-torre", flag)) if v is not None]
    if len({v for _, v in fuentes}) > 1:
        raise ChispaError("texto_torre no coincide: " + "; ".join(f"{n} dice {v}" for n, v in fuentes))
    return fuentes[0][1] if fuentes else "v1"


def fijar_texto_torre(salida, version: str) -> None:
    """Reescribe META de `salida` con `texto_torre` (solo si no es v1; si es v1 lo quita) y deja las demás secciones y campos intactos."""
    salida = Path(salida)
    secs = formato.leer(salida.read_bytes())
    d = json.loads(secs.get(formato.META, b"{}")) if formato.META in secs else {}
    if (d.get("texto_torre") or "v1") == version:
        return
    d.pop("texto_torre", None)
    if version != "v1":
        d["texto_torre"] = version
    secs[formato.META] = json.dumps(d).encode()
    tmp = salida.with_name(salida.name + ".tmp")
    try:
        tmp.write_bytes(formato.escribir(secs))
        os.replace(tmp, salida)
    finally:
        tmp.unlink(missing_ok=True)
