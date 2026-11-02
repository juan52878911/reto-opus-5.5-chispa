"""e2e de «nadie opinó» en la batería: lee un servidor real y comprueba el recuento aparte, la alerta y la exactitud.
Uso: bateria_nadie.py URL (sin_torre|con_torre). Sale con 1 si algo no cumple."""
import json
import os
import sys
import tempfile

from chispa import bateria as B

OPS = {"alta": "necesita respuesta hoy o hay una obra detenida", "media": "puede esperar un par de días", "baja": "solo consulta sin fecha"}
TEXTOS = [("la obra está detenida y necesito respuesta hoy", "alta"), ("puede esperar unos días", "media"), ("solo una consulta de precios", "baja"),
          ("urgente hoy mismo", "alta"), ("sin fecha", "baja"), ("esta semana", "media")]


def main(url, caso):
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "c.jsonl"), "w", encoding="utf-8") as f:
            for i, (t, e) in enumerate(TEXTOS):
                f.write(json.dumps(dict(id=f"c{i}", tarea="u", tipo="choice", pregunta="¿Qué tan urgente es la solicitud?", texto=t, opciones=list(OPS),
                                        descripciones=OPS, etiqueta=e, idioma="es", split="test", fuente="x", licencia="MIT", uso_comercial=True)) + "\n")
        man = os.path.join(d, "m.json")
        json.dump({"nombre": "nadie", "conjuntos": [{"nombre": "urg", "ruta": "c.jsonl", "tipo": "choice"}], "umbrales": {"p50_ms": None, "p99_ms": None}}, open(man, "w"))
        avisos = []
        rep = B.bateria(man, url=url, concurrencia=2, aviso=avisos.append)
    g, errs = rep["global"], []
    print({k: g.get(k) for k in ("n", "exactitud", "sin_probs", "nadie_opino", "baja_confianza", "escalado")}, "alertas:", len(rep["alertas"]), "avisos:", len(avisos))
    if caso == "sin_torre":
        if g["nadie_opino"] != 1.0 or g["sin_probs"] != 1.0 or g["exactitud"] is not None:
            errs.append("sin torre: se esperaba nadie_opino = sin_probs = 1 y exactitud sin medir")
        if not any("torre" in a for a in rep["alertas"]) or "## Alertas" not in rep["informe"]:
            errs.append("sin torre: falta la alerta con la causa (torre) en el informe")
        if not any("no puede opinar" in a for a in avisos):
            errs.append("sin torre: la batería no avisó al arrancar")
    else:
        if g["nadie_opino"] != 0.0 or g["sin_probs"] != 0.0 or g["exactitud"] is None or g["baja_confianza"] != 1.0:
            errs.append("con torre: se esperaba escalar con probs (baja_confianza = 1) y exactitud medida")
        if rep["alertas"] or any("no puede opinar" in a for a in avisos):
            errs.append("con torre: no debe haber alertas ni aviso")
    for e in errs:
        print("FALLO " + e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
