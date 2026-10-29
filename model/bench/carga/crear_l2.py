"""L2 de prueba para la carga: cabeza con pesos aleatorios y semilla fija sobre e5 de ~/hf.

La latencia de L2 no depende de los pesos; aquí no hay S3 para el checkpoint real. Escribe, en DIR:
ckpt/mejor.pt, calib.json, esquema.jsonl, y llama a `model.l2.exportar` (→ l2.chispa + l2.chispa.informe.json).

    python crear_l2.py DIR [--semilla 0]      (desde la raíz del repo, con PYTHONPATH=raíz)
"""
import argparse
import json
import os
import subprocess
import sys

import torch

RAIZ = os.getcwd()

from model.l2.modelo import ModeloL2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--semilla", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(os.path.join(a.dir, "ckpt"), exist_ok=True)
    torch.manual_seed(a.semilla)
    m = ModeloL2().eval()
    torch.save({"modelo": m.state_dict(), "cabezas": []}, os.path.join(a.dir, "ckpt", "mejor.pt"))
    cal = {"chispa": {"tipos": {"choice": {"T": 0.05, "a": 0.0, "b": 0.0, "theta": 0.5}}, "tau_escalate": 0.5}}
    json.dump(cal, open(os.path.join(a.dir, "calib.json"), "w"))
    esq = json.load(open(os.path.join(a.dir, "esquema.json"), encoding="utf-8"))
    ops = list(esq["opciones"])
    fila = {"id": "carga:0", "tarea": "carga", "tipo": "choice", "pregunta": esq["pregunta"], "opciones": ops,
            "descripciones": {o: "" for o in ops}, "fuente": "massive", "licencia": "CC-BY-4.0", "split": "dev"}
    open(os.path.join(a.dir, "esquema.jsonl"), "w", encoding="utf-8").write(json.dumps(fila, ensure_ascii=False) + "\n")
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "exportar_ligero.py"), RAIZ, "--ckpt", os.path.join(a.dir, "ckpt"),
                    "--calib", os.path.join(a.dir, "calib.json"), "--esquemas", os.path.join(a.dir, "esquema.jsonl"),
                    "--salida", os.path.join(a.dir, "l2.chispa"), "--trabajo", os.path.join(a.dir, "onnx")], check=True)


main()
