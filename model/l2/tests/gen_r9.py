"""Fixture R9 (`fixtures/esquemas-r9.json`): lo que `exportar.esquemas_json` escribe para noul en los dos órdenes de `opciones` y para multi.
Lo lee el test Go de `empaquetar_go` (paridad con la búsqueda y la decisión del servidor). Regenerar: `python -m model.l2.tests.gen_r9`."""
import json
from pathlib import Path

import torch

from model.l2 import exportar as E
from model.l2.modelo import ModeloL2
from model.l2.tests.gen_esquemas_v2 import fila
from model.l2.tests.test_t24_exportar import CodificadorDiminuto

FIX = Path(__file__).resolve().parent / "fixtures"
DESC = {"false": "Mensaje legítimo.", "true": "Mensaje no deseado."}


def filas():
    return [fila(0, "noul", "¿Es spam? A", ["false", "true"], DESC, "true"),
            fila(1, "noul", "¿Es spam? B", ["true", "false"], DESC, "true"),
            fila(2, "multi", "¿Qué temas toca?", ["precio", "envio", "garantia"], {"precio": "Cuánto cuesta.", "envio": "", "garantia": "Cobertura."}, "precio")]


def generar():
    torch.manual_seed(1)
    modelo, enc, fs = ModeloL2().eval(), CodificadorDiminuto(), filas()
    torres = E.entradas_torres(modelo, enc, fs)
    return {"esquemas": E.esquemas_json(torres, int(torres[0][3].shape[0])),
            "textos": {"verdadero_noul": [E.texto_torre_consulta(r) for r in fs[:2]]}}


if __name__ == "__main__":
    (FIX / "esquemas-r9.json").write_text(json.dumps(generar(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
