"""Demostración: arnés sobre model/sondeo/*.jsonl con predicciones uniformes (no hay predicciones de e5 kNN
guardadas en model/eval0/out/, solo agregados). Uso: python -m model.evaluacion.demo_uniforme <dir-salida>"""
import json
import sys
from pathlib import Path

from . import chispa_eval as CE

SONDEO = Path(__file__).resolve().parents[1] / "sondeo"
TAREAS = ["intencion", "toxicidad", "herramientas", "whatsapp_comercio"]


def main(salida):
    out = Path(salida)
    out.mkdir(parents=True, exist_ok=True)
    for t in TAREAS:
        ruta = str(SONDEO / f"{t}.jsonl")
        filas = CE.asignar_ids(CE.leer_jsonl(ruta), ruta)
        preds = out / f"{t}.pred.jsonl"
        with open(preds, "w", encoding="utf-8") as f:
            for r in filas:
                k = len(r["opciones"])
                f.write(json.dumps({"id": r["id"], "probs": {o: 1 / k for o in r["opciones"]}}) + "\n")
        print(f"## {t}")
        CE.main(["--datos", ruta, "--pred", str(preds), "--salida", str(out / f"{t}.json")])


if __name__ == "__main__":
    main(sys.argv[1])
