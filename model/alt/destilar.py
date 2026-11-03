"""Etiquetas blandas de Qwen3-4B (vLLM) para el train de la alternativa (b): solo filas de los ficheros del manifiesto.

Mismo prompt y misma puntuación que `model/maestro/blandas.py` (logprob del primer token de cada letra, softmax sobre las letras
de las opciones), pero con vLLM para que quepan decenas de miles de filas en una hora de g5. vLLM devuelve las `--top-logprobs`
mejores: una letra fuera de ellas recibe el logprob mínimo devuelto menos 5 (masa ≈ 0). Se etiquetan solo filas train con ≤ 26
opciones que `entrenar.tope_por_tarea` va a escoger (mismo orden de carga y semilla), una muestra de `--max-filas`; el resto
entrena solo con la etiqueta dura. Reescribe en su sitio los ficheros del manifiesto añadiendo `blanda` (el sellado viene después,
en `entrenar --sellar`). Las PQRS y lo que no admita el manifiesto no pasan nunca por aquí.

    python -m model.alt.destilar --datos RAIZ --modelo Qwen/Qwen3-4B-Instruct-2507 --max-filas 150000 --minutos 55 --resumen R.json"""
import argparse
import gzip
import json
import math
import random
import sys
import time
from pathlib import Path

from model.l2.datos import iterar
from model.maestro.blandas import LETRAS, construir_prompt, ids_letras

from .manifiesto import cargar, verificar_filas

MODELO = "Qwen/Qwen3-4B-Instruct-2507"   # Apache-2.0
MAX_CHARS_TEXTO = 3000


def tope_por_tarea(filas, tope, semilla=0):
    """Copia de `entrenar.tope_por_tarea` (aquel módulo importa torch y este corre en el venv de vLLM)."""
    if not tope:
        return filas
    rng, por = random.Random(semilla), {}
    for r in filas:
        por.setdefault(r["tarea"], []).append(r)
    out = []
    for t in sorted(por):
        g = por[t]
        rng.shuffle(g)
        out += g[:tope]
    return out


def elegir(manifiesto, raiz, max_filas, tope_tarea, semilla=0):
    """Ids a etiquetar: train escogido por el tope por tarea, con 2..26 opciones; muestra determinista de `max_filas`."""
    train = [r for c in manifiesto.conjuntos for r in iterar([str(Path(raiz) / c["fichero"])]) if r["split"] == "train"]
    verificar_filas(train, manifiesto)
    aptas = [r for r in tope_por_tarea(train, tope_tarea, semilla) if 2 <= len(r["opciones"]) <= len(LETRAS)]
    random.Random(semilla + 1).shuffle(aptas)
    return aptas[:max_filas] if max_filas else aptas


def distribucion(top, opciones, letras_id):
    """{opcion: prob} desde el dict token_id → logprob de vLLM (softmax solo sobre las letras de las opciones)."""
    piso = (min(top.values()) if top else 0.0) - 5.0
    lps = [top.get(letras_id[i], piso) for i in range(len(opciones))]
    m = max(lps)
    es = [math.exp(x - m) for x in lps]
    z = sum(es)
    return {o: e / z for o, e in zip(opciones, es)}


def recortar(fila):
    return dict(fila, texto=fila["texto"][:MAX_CHARS_TEXTO])


def etiquetar(filas, modelo, minutos, top_logprobs=20, trozo=4096, log=print):
    from vllm import LLM, SamplingParams
    llm = LLM(model=modelo, dtype="bfloat16", max_model_len=4096, gpu_memory_utilization=0.85, enable_prefix_caching=True)
    tok = llm.get_tokenizer()
    letras_id = ids_letras(tok)
    sp = SamplingParams(max_tokens=1, temperature=0.0, logprobs=top_logprobs)
    t0, out = time.time(), {}
    for i in range(0, len(filas), trozo):
        if (time.time() - t0) / 60 > minutos:
            log("tope de %.0f min: %d de %d filas etiquetadas" % (minutos, len(out), len(filas)))
            break
        lote = filas[i:i + trozo]
        res = llm.generate([construir_prompt(tok, recortar(f), f["opciones"]) for f in lote], sp, use_tqdm=False)
        for f, r in zip(lote, res):
            lp = r.outputs[0].logprobs[0] if r.outputs and r.outputs[0].logprobs else {}
            out[f["id"]] = distribucion({k: v.logprob for k, v in lp.items()}, f["opciones"], letras_id)
        log("%d/%d filas, %.1f filas/s" % (len(out), len(filas), len(out) / max(time.time() - t0, 1e-9)))
    return out, time.time() - t0


def reescribir(manifiesto, raiz, blandas):
    """Añade `blanda` a las filas etiquetadas de cada fichero del manifiesto (gzip sin fecha: el sha256 solo depende de las filas)."""
    n = 0
    for c in manifiesto.conjuntos:
        p = Path(raiz) / c["fichero"]
        filas = list(iterar([str(p)]))
        for r in filas:
            if r["id"] in blandas and r["split"] == "train":
                r["blanda"] = blandas[r["id"]]
                n += 1
        tmp = p.with_suffix(".tmp")
        with open(tmp, "wb") as fb, gzip.GzipFile(fileobj=fb, mode="wb", mtime=0) as gz:
            for r in filas:
                gz.write((json.dumps(r, ensure_ascii=False) + "\n").encode("utf-8"))
        tmp.replace(p)
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--datos", required=True, help="raíz con los ficheros del manifiesto")
    ap.add_argument("--manifiesto")
    ap.add_argument("--modelo", default=MODELO)
    ap.add_argument("--max-filas", type=int, default=150000)
    ap.add_argument("--tope-tarea", type=int, default=1000)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--minutos", type=float, default=55)
    ap.add_argument("--resumen", required=True)
    a = ap.parse_args(argv)
    m = cargar(a.manifiesto) if a.manifiesto else cargar()
    filas = elegir(m, a.datos, a.max_filas, a.tope_tarea, a.semilla)
    print("a etiquetar: %d filas" % len(filas), flush=True)
    blandas, seg = etiquetar(filas, a.modelo, a.minutos, log=lambda s: print(s, flush=True))
    escritas = reescribir(m, a.datos, blandas)
    por_id = {f["id"]: f for f in filas}
    acuerdo = [max(b, key=b.get) == por_id[i]["etiqueta"] for i, b in blandas.items() if isinstance(por_id[i].get("etiqueta"), str)]
    res = {"modelo": a.modelo, "licencia_modelo": "apache-2.0", "elegidas": len(filas), "etiquetadas": len(blandas),
           "escritas": escritas, "segundos": round(seg, 1), "filas_por_s": round(len(blandas) / max(seg, 1e-9), 2),
           "acuerdo_top1": round(sum(acuerdo) / len(acuerdo), 4) if acuerdo else None,
           "por_tarea": dict(sorted(__import__("collections").Counter(por_id[i]["tarea"] for i in blandas).most_common(20)))}
    Path(a.resumen).write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False))
    return 0 if blandas else 1


if __name__ == "__main__":
    sys.exit(main())
