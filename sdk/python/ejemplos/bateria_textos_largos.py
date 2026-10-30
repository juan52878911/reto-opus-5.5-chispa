"""Conjunto sintético de la batería con textos largos y varias preguntas por texto (para `chispa evaluar --bateria ... --agrupar`).

Cada texto mide ~`--kb` KB (relleno repetido más una frase con la señal) y lleva `--preguntas` preguntas distintas. Sin `--agrupar` la batería manda una
pregunta por petición y nunca pone a prueba el presupuesto por petición del servidor (max_trozos); con `--agrupar` las preguntas de un texto
viajan juntas, como en un cliente que las agrupa. Es sintético: sirve para detectar fallos de presupuesto, memoización y agrupación, no para medir calidad.

    python bateria_textos_largos.py DIRECTORIO [--textos 6] [--preguntas 4] [--kb 24]
    chispa evaluar --bateria DIRECTORIO/manifiesto.json --url http://127.0.0.1:8080 --agrupar
"""
import argparse
import json
import os

RELLENO = "El cliente describe con detalle el historial de la cuenta, los pagos realizados y las gestiones previas con la oficina. "
TEMAS = ["pagos", "tarjeta", "fraude", "credito", "soporte", "cuenta"]


def filas(textos: int = 6, preguntas: int = 4, kb: int = 24) -> list:
    out = []
    for t in range(textos):
        señal = TEMAS[t % len(TEMAS)]
        texto = (RELLENO * (kb * 1024 // len(RELLENO) + 1))[:kb * 1024] + f" Consulta final sobre {señal}."
        for q in range(preguntas):
            ops = ["si", "no"] if q % 2 == 0 else [señal, "otro"]
            out.append({"id": f"largo{t}-q{q}", "tarea": "largos", "tipo": "choice", "pregunta": f"Pregunta {q}: ¿el texto trata de {ops[0]}?",
                        "texto": texto, "opciones": ops, "descripciones": {o: f"Responde {o}" for o in ops}, "etiqueta": ops[0],
                        "idioma": "es", "split": "test", "fuente": "sintetico", "licencia": "MIT", "uso_comercial": True})
    return out


def escribir(destino: str, **k) -> str:
    os.makedirs(destino, exist_ok=True)
    with open(os.path.join(destino, "largos.jsonl"), "w", encoding="utf-8") as f:
        f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in filas(**k)))
    man = os.path.join(destino, "manifiesto.json")
    with open(man, "w", encoding="utf-8") as f:
        json.dump({"nombre": "textos-largos", "conjuntos": [{"nombre": "largos", "ruta": "largos.jsonl", "tipo": "choice", "grupo": "sintetico"}]}, f, indent=2)
    return man


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("destino")
    ap.add_argument("--textos", type=int, default=6)
    ap.add_argument("--preguntas", type=int, default=4)
    ap.add_argument("--kb", type=int, default=24)
    a = ap.parse_args()
    print(escribir(a.destino, textos=a.textos, preguntas=a.preguntas, kb=a.kb))
