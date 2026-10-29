"""Regenera los fixtures de ESQUEMAS v2 (`HashEsquema2`) con el exportador y un codificador diminuto.

    python -m model.l2.tests.gen_esquemas_v2

Escribe `fixtures/esquemas-v2.chispa` (el ONNX de L2 es un relleno, no se ejecuta) y `fixtures/esquemas-v2.json` con las
claves esperadas (`HashEsquema2` en hex), calculadas aparte con hashlib, para la paridad del runtime. Las torres son del modelo diminuto:
solo importan las claves."""
import hashlib
import json
import tempfile
from pathlib import Path

import torch

from model.l2 import exportar as E
from model.l2.modelo import ModeloL2, texto_opcion
from model.l2.tests.test_t24_exportar import CodificadorDiminuto, calib_prueba

FIX = Path(__file__).resolve().parent / "fixtures"
P = "¿Qué quiere la persona?"
DESC = {"alarma": "Poner una alarma.", "tiempo": "Preguntar por el clima.", "musica": ""}


def fila(i, tipo, pregunta, opciones, descripciones, etiqueta):
    return {"id": "v2:train:%d" % i, "tarea": "esq-v2", "tipo": tipo, "pregunta": pregunta, "texto": "mensaje %d" % i, "opciones": opciones,
            "descripciones": descripciones, "etiqueta": etiqueta, "idioma": "es", "split": "train", "fuente": "inventada", "licencia": "MIT",
            "uso_comercial": True}


def filas():
    ops = ["alarma", "tiempo", "musica"]
    return [fila(0, "choice", P, ops, DESC, "alarma"),
            # mismas pregunta y opciones, otra descripción de «alarma»: en v1 compartían torre; en v2 son claves distintas
            fila(1, "choice", P, ops, {**DESC, "alarma": "Despertar a una hora."}, "tiempo"),
            fila(2, "noul", "¿Es spam? ñandú, café", ["false", "true"], {"false": "Mensaje legítimo.", "true": "Mensaje no deseado."}, "true"),
            fila(3, "score", "Valora la urgencia", ["1", "2", "3"], {"1": "Baja", "2": "Media", "3": "Alta"}, "2")]


def hash_esquema2(pregunta, kind, opciones):
    """`chispa3.HashEsquema2` en Python puro (hashlib): sha256(pregunta·0x1f·kind·0x1f·(id·0x1e·descripción·0x1d)* por id) [:16]."""
    h = hashlib.sha256(pregunta.encode() + b"\x1f" + kind.encode() + b"\x1f")
    for i, d in sorted((i.encode(), d.encode()) for i, d in opciones):
        h.update(i + b"\x1e" + d + b"\x1d")
    return h.digest()[:16]


def esperado(fs):
    claves, conj = [], []
    for r in fs:
        for o in (r["opciones"] if r["tipo"] == "choice" else [None]):
            _, kind, ops = E.clave_torre(r, o)
            h = hash_esquema2(r["pregunta"], kind, ops).hex()
            if any(c["hash"] == h for c in claves):
                continue  # «tiempo» y «musica» comparten clave en las dos filas de choice: una sola torre
            claves.append({"tipo": r["tipo"], "pregunta": r["pregunta"], "kind": kind, "opciones": [{"id": i, "description": d} for i, d in ops],
                           "hash": h, "texto_torre": texto_opcion(r, o) if o else E.texto_torre_consulta(r)})
        if r["tipo"] == "choice":
            ops = [(o, r["descripciones"].get(o, "")) for o in r["opciones"]]
            conj.append({"pregunta": r["pregunta"], "kind": "choice", "opciones": [{"id": i, "description": d} for i, d in ops],
                         "hash": hash_esquema2(r["pregunta"], "choice", ops).hex()})
    return {"version": 2, "nota": "ESQUEMAS v2 (HashEsquema2, 16 bytes): choice = una entrada por opción (kind choice, [opción]); noul/score = una por "
            "pregunta con todas las opciones (kind = tipo). CONJ v2 (solo choice): kind choice con todas las opciones. contrato-torre.md.",
            "claves": claves, "conj": conj}


def main():
    torch.manual_seed(1)
    modelo, enc, fs = ModeloL2().eval(), CodificadorDiminuto(), filas()
    torres = E.entradas_torres(modelo, enc, fs)
    calib = calib_prueba(modelo, enc, fs)
    with tempfile.TemporaryDirectory() as t:
        onnx = Path(t) / "l2.onnx"
        onnx.write_bytes(b"onnx-de-relleno")
        E.empaquetar(E.meta_de(fs), onnx, E.esquemas_json(torres, int(torres[0][3].shape[0])), calib["chispa"], FIX / "esquemas-v2.chispa")
    (FIX / "esquemas-v2.json").write_text(json.dumps(esperado(fs), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
