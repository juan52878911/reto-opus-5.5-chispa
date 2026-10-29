"""Regenera los fixtures de ESQUEMAS v2 (claves con descripción) con el exportador y un codificador diminuto.

    python -m model.l2.tests.gen_esquemas_v2

Escribe `fixtures/esquemas-v2.chispa` (META.version = 2; el ONNX de L2 es un relleno, no se ejecuta) y `fixtures/esquemas-v2.json` con las
claves esperadas (`HashEsquema` en hex), calculadas aparte con hashlib, para la paridad del runtime. Las torres son del modelo diminuto:
solo importan las claves."""
import hashlib
import json
import struct
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


def hash_esquema(pregunta, opciones):
    """`chispa3.HashEsquema` en Python puro: sha256 de len64(pregunta)·pregunta·len64(opciones)·(len64·opción)*."""
    h = hashlib.sha256()
    for s in [pregunta]:
        h.update(struct.pack("<Q", len(s.encode())) + s.encode())
    h.update(struct.pack("<Q", len(opciones)))
    for o in opciones:
        h.update(struct.pack("<Q", len(o.encode())) + o.encode())
    return h.digest()


def esperado(fs):
    claves, conj = [], []
    for r in fs:
        for o in (r["opciones"] if r["tipo"] == "choice" else [None]):
            v2 = E.opciones_clave(r, o, 2)
            if any(c["hash"] == hash_esquema(r["pregunta"], v2).hex() for c in claves):
                continue  # «tiempo» y «musica» comparten clave en las dos filas de choice: una sola torre
            claves.append({"tipo": r["tipo"], "pregunta": r["pregunta"], "opciones": v2, "hash": hash_esquema(r["pregunta"], v2).hex(),
                           "hash_v1": hash_esquema(r["pregunta"], E.opciones_clave(r, o, 1)).hex(),
                           "texto_torre": texto_opcion(r, o) if o else E.texto_consulta(r)})
        if r["tipo"] == "choice":
            ids = sorted(r["opciones"])
            v2 = [x for o in ids for x in (o, r["descripciones"].get(o, ""))]
            conj.append({"pregunta": r["pregunta"], "opciones": v2, "hash": hash_esquema(r["pregunta"], v2).hex(),
                         "hash_v1": hash_esquema(r["pregunta"], ids).hex()})
    return {"version": 2, "nota": "ESQUEMAS v2: choice = HashEsquema(pregunta, [opción, descripción]) por opción; noul/score = HashEsquema(pregunta, "
            "[o1, d1, o2, d2, …]) en el orden de la pregunta. CONJ v2 (solo choice): ídem con los ids ordenados. contrato-torre.md.",
            "claves": claves, "conj": conj}


def main():
    torch.manual_seed(1)
    modelo, enc, fs = ModeloL2().eval(), CodificadorDiminuto(), filas()
    torres = E.entradas_torres(modelo, enc, fs)
    calib = calib_prueba(modelo, enc, fs)
    with tempfile.TemporaryDirectory() as t:
        onnx = Path(t) / "l2.onnx"
        onnx.write_bytes(b"onnx-de-relleno")
        E.empaquetar(E.meta_de(fs), onnx, E.esquemas_json(torres, int(torres[0][2].shape[0])), calib["chispa"], FIX / "esquemas-v2.chispa")
    (FIX / "esquemas-v2.json").write_text(json.dumps(esperado(fs), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
