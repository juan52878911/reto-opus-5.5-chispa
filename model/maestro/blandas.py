"""Etiquetas blandas del maestro (Qwen): añade `blanda: {opcion: prob}` a las filas del esquema.

    python -m model.maestro.blandas --entrada a.jsonl b.jsonl --salida <dir> --modelo <id HF o ruta>
                                    [--lote 16] [--max-filas N]

Cada opción se puntúa por el logprob (sobre todo el vocabulario) del primer token de su letra (A, B, C…) tras
un prompt que lista las opciones con sus descripciones. Hasta 26 opciones: un solo prompt y softmax sobre las
letras. Más de 26 (CLINC, herramientas): dos pasadas con candidatos (ver README).

Salida, por cada `<entrada>.jsonl`: `<salida>/<nombre>.jsonl` (filas con `uso_comercial` true) y
`<salida>/<nombre>.solo-medir.jsonl` (filas con `uso_comercial` false: solo sirven para medir). Reanuda desde lo
ya escrito. Al final escribe `<salida>/resumen.json`.
"""
import argparse
import collections
import json
import math
import sys
import time
from pathlib import Path

MAX_BLOQUE = 26
LETRAS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
EPS_RESTO = 0.02  # masa que la segunda pasada reserva a las opciones que no llegaron a candidatas
MODELO_DEFECTO = "Qwen/Qwen3.5-4B-Instruct"
MODELOS_RESPALDO = ("Qwen/Qwen3.5-4B", "Qwen/Qwen3-4B-Instruct-2507")
MAX_TOKENS_LOTE = 16384
SISTEMA = ("Eres un clasificador. Lee el mensaje y responde únicamente con la letra de la opción correcta, "
           "sin explicación.")


# --- modelo ------------------------------------------------------------------------------------------------
def resolver_modelo(modelo):
    """(id usado, motivo). Una ruta local se usa tal cual; un id de HF se comprueba y, si no existe, cae a los
    respaldos."""
    if Path(modelo).is_dir():
        return modelo, "ruta local"
    from huggingface_hub import model_info
    candidatos = [MODELO_DEFECTO, *MODELOS_RESPALDO] if modelo == MODELO_DEFECTO else [modelo]
    errores = []
    for c in candidatos:
        try:
            model_info(c)
            return c, "pedido" if c == modelo else "respaldo de %s (%s)" % (modelo, "; ".join(errores))
        except Exception as e:  # no existe, sin red…
            errores.append("%s: %s" % (c, type(e).__name__))
    raise RuntimeError("ningún modelo existe: " + "; ".join(errores))


def cargar(modelo, dispositivo=None):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(modelo)
    tok.padding_side = "left"
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token or tok.unk_token
    dispositivo = dispositivo or ("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.bfloat16 if dispositivo == "cuda" else torch.float32
    m = AutoModelForCausalLM.from_pretrained(modelo, dtype=dtype).to(dispositivo).eval()
    return m, tok, dispositivo


def ids_letras(tok):
    """Id del token de cada letra, tal como sale como primer token de la respuesta."""
    ids = []
    for l in LETRAS:
        t = tok.encode(l, add_special_tokens=False)
        if not t:
            raise ValueError("la letra %s no tiene token" % l)
        ids.append(t[-1])
    if len(set(ids)) != len(ids):
        raise ValueError("letras con token repetido")
    return ids


# --- prompts -----------------------------------------------------------------------------------------------
def texto_prompt(fila, opciones):
    desc = fila.get("descripciones") or {}
    lineas = []
    for i, o in enumerate(opciones):
        d = desc.get(o)
        lineas.append("%s. %s%s" % (LETRAS[i], o, (": " + d) if d else ""))
    return "%s\n\nMensaje: %s\n\nOpciones:\n%s\n\nResponde solo con la letra." % (
        fila["pregunta"], fila["texto"], "\n".join(lineas))


def construir_prompt(tok, fila, opciones):
    usuario = texto_prompt(fila, opciones)
    if getattr(tok, "chat_template", None):
        msgs = [{"role": "system", "content": SISTEMA}, {"role": "user", "content": usuario}]
        try:
            return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            return tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    return SISTEMA + "\n\n" + usuario + "\nRespuesta: "


# --- puntuación --------------------------------------------------------------------------------------------
def logprobs_letras(modelo, tok, dispositivo, trabajos, lote, letras_id):
    """trabajos: lista de (prompt, n_opciones). Devuelve, en el mismo orden, la lista de n logprobs de las
    letras (sobre todo el vocabulario). Agrupa por longitud para no rellenar de más."""
    import torch
    enc = [tok(p, add_special_tokens=False)["input_ids"] for p, _ in trabajos]
    orden = sorted(range(len(trabajos)), key=lambda i: len(enc[i]))
    salida = [None] * len(trabajos)
    pos = 0
    while pos < len(orden):
        fin = pos + 1
        while fin < len(orden) and fin - pos < lote and len(enc[orden[fin]]) * (fin - pos + 1) <= MAX_TOKENS_LOTE:
            fin += 1
        idx = orden[pos:fin]
        pos = fin
        largo = max(len(enc[i]) for i in idx)
        pad = tok.pad_token_id
        ids = torch.tensor([[pad] * (largo - len(enc[i])) + enc[i] for i in idx], device=dispositivo)
        mask = torch.tensor([[0] * (largo - len(enc[i])) + [1] * len(enc[i]) for i in idx], device=dispositivo)
        with torch.no_grad():
            try:
                lg = modelo(input_ids=ids, attention_mask=mask, logits_to_keep=1).logits[:, -1]
            except TypeError:
                lg = modelo(input_ids=ids, attention_mask=mask).logits[:, -1]
            lp = torch.log_softmax(lg.float(), dim=-1)[:, letras_id].cpu().tolist()
        for k, i in enumerate(idx):
            salida[i] = lp[k][:trabajos[i][1]]
    return salida


def softmax(xs):
    m = max(xs)
    e = [math.exp(x - m) for x in xs]
    s = sum(e)
    return [v / s for v in e]


def bloques(n):
    """Partes consecutivas y equilibradas de range(n), cada una de ≤ 26."""
    nb = -(-n // MAX_BLOQUE)
    tam = -(-n // nb)
    return [list(range(i, min(i + tam, n))) for i in range(0, n, tam)]


def normalizar(d):
    s = sum(d.values())
    return {k: v / s for k, v in d.items()}


def puntuar_filas(modelo, tok, dispositivo, filas, lote, letras_id):
    """Devuelve una lista de dicts {opcion: prob} (suman 1) en el orden de `filas`."""
    # Pasada 1: un trabajo por (fila, bloque). Con ≤ 26 opciones es la única pasada.
    trabajos, claves = [], []
    for fi, f in enumerate(filas):
        for bi, b in enumerate(bloques(len(f["opciones"]))):
            trabajos.append((construir_prompt(tok, f, [f["opciones"][j] for j in b]), len(b)))
            claves.append((fi, bi))
    lp1 = logprobs_letras(modelo, tok, dispositivo, trabajos, lote, letras_id)
    por_fila = collections.defaultdict(dict)
    for (fi, bi), lp in zip(claves, lp1):
        por_fila[fi][bi] = softmax(lp)  # distribución dentro del bloque
    res = [None] * len(filas)
    seg = []  # filas que necesitan segunda pasada: (fi, candidatos)
    for fi, f in enumerate(filas):
        ops = f["opciones"]
        bl = bloques(len(ops))
        if len(bl) == 1:
            res[fi] = dict(zip(ops, por_fila[fi][0]))
            continue
        m = max(1, MAX_BLOQUE // len(bl))
        cand = []
        for bi, b in enumerate(bl):
            top = sorted(range(len(b)), key=lambda k: -por_fila[fi][bi][k])[:m]
            cand += [(por_fila[fi][bi][k], b[k]) for k in top]
        cand = sorted(sorted(cand, reverse=True)[:MAX_BLOQUE], key=lambda c: c[1])
        seg.append((fi, [j for _, j in cand]))
    if seg:
        t2 = [(construir_prompt(tok, filas[fi], [filas[fi]["opciones"][j] for j in cj]), len(cj)) for fi, cj in seg]
        lp2 = logprobs_letras(modelo, tok, dispositivo, t2, lote, letras_id)
        for (fi, cj), lp in zip(seg, lp2):
            ops = filas[fi]["opciones"]
            q = softmax(lp)
            p = {ops[j]: (1 - EPS_RESTO) * qq for j, qq in zip(cj, q)}
            resto = {}
            for bi, b in enumerate(bloques(len(ops))):
                for k, j in enumerate(b):
                    if j not in cj:
                        resto[ops[j]] = por_fila[fi][bi][k] + 1e-9
            s = sum(resto.values())
            p.update({o: EPS_RESTO * v / s for o, v in resto.items()})
            res[fi] = {o: p[o] for o in ops}
    return [normalizar(r) for r in res]


# --- E/S, reanudación y resumen ----------------------------------------------------------------------------
def leer_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def leer_jsonl_tolerante(path):
    """Como leer_jsonl pero ignora una última línea cortada (muerte a mitad de escritura)."""
    out = []
    if not Path(path).exists():
        return out
    with open(path, encoding="utf-8") as fh:
        for l in fh:
            try:
                out.append(json.loads(l))
            except ValueError:
                pass
    return out


def repartir_tope(conteos, max_filas):
    """Cuántas filas toma cada entrada para sumar ≤ max_filas, proporcional a su tamaño."""
    total = sum(conteos)
    if not max_filas or total <= max_filas:
        return list(conteos)
    return [min(n, max(1, round(max_filas * n / total))) for n in conteos]


def muestreo(filas, tope):
    """tope filas repartidas con paso regular (cubre todos los splits); determinista."""
    if tope >= len(filas):
        return list(filas)
    return [filas[int(i * len(filas) / tope)] for i in range(tope)]


def salidas(dir_salida, entrada):
    n = Path(entrada).stem
    return Path(dir_salida) / (n + ".jsonl"), Path(dir_salida) / (n + ".solo-medir.jsonl")


def resumir(dir_salida, entradas, info):
    from model.evaluacion.metricas import ece
    por = collections.defaultdict(lambda: {"n": 0, "ok": 0})
    conf, aciertos = [], []
    for e in entradas:
        for p in salidas(dir_salida, e):
            for f in leer_jsonl_tolerante(p):
                b = f.get("blanda")
                if not b:
                    continue
                top = max(b, key=b.get)
                ok = top == f["etiqueta"]
                k = por[(f["tarea"], f["split"], f["fuente"], "solo-medir" if not f.get("uso_comercial", True) else "")]
                k["n"] += 1
                k["ok"] += ok
                conf.append(b[top])
                aciertos.append(ok)
    acuerdo = ["%s|%s|%s%s" % (t, s, fu, ("|" + sm) if sm else "") for (t, s, fu, sm) in sorted(por)]
    return {"acuerdo_top1": {a: {"n": v["n"], "acuerdo": v["ok"] / v["n"]}
                             for a, v in zip(acuerdo, (por[k] for k in sorted(por)))},
            "acuerdo_global": (sum(aciertos) / len(aciertos)) if aciertos else None,
            "filas_total": len(aciertos),
            "ece_maestro": ece(conf, aciertos) if aciertos else None, **info}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--entrada", nargs="+", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--modelo", default=MODELO_DEFECTO)
    ap.add_argument("--lote", type=int, default=16)
    ap.add_argument("--max-filas", type=int, default=0, help="tope total (0 = todas), repartido entre entradas")
    a = ap.parse_args(argv)

    import torch
    t0 = time.time()
    Path(a.salida).mkdir(parents=True, exist_ok=True)
    usado, motivo = resolver_modelo(a.modelo)
    print("modelo:", usado, "(%s)" % motivo, flush=True)
    modelo, tok, disp = cargar(usado)
    letras_id = ids_letras(tok)
    filas_in = [leer_jsonl(e) for e in a.entrada]
    topes = repartir_tope([len(f) for f in filas_in], a.max_filas)
    nuevas, t_gpu = 0, 0.0
    for e, filas, tope in zip(a.entrada, filas_in, topes):
        filas = muestreo(filas, tope)
        ruta_c, ruta_m = salidas(a.salida, e)
        hechas = {f["id"] for r in (ruta_c, ruta_m) for f in leer_jsonl_tolerante(r) if f.get("blanda")}
        pend = [f for f in filas if f["id"] not in hechas]
        print("%s: %d filas elegidas, %d ya hechas, %d pendientes" % (e, len(filas), len(hechas & {f["id"] for f in filas}),
                                                                       len(pend)), flush=True)
        for i in range(0, len(pend), 256):
            trozo = pend[i:i + 256]
            t1 = time.time()
            probs = puntuar_filas(modelo, tok, disp, trozo, a.lote, letras_id)
            if disp == "cuda":
                torch.cuda.synchronize()
            t_gpu += time.time() - t1
            nuevas += len(trozo)
            for f, p in zip(trozo, probs):
                ruta = ruta_c if f.get("uso_comercial", True) else ruta_m
                with open(ruta, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(dict(f, blanda=p), ensure_ascii=False, sort_keys=True) + "\n")
            print("  %d/%d  %.1f filas/s" % (min(i + 256, len(pend)), len(pend), len(trozo) / (time.time() - t1)), flush=True)
    info = {"modelo": usado, "modelo_pedido": a.modelo, "motivo_modelo": motivo, "dispositivo": disp,
            "filas_nuevas": nuevas, "segundos_puntuando": round(t_gpu, 2),
            "filas_por_s": round(nuevas / t_gpu, 3) if t_gpu else None,
            "horas_gpu": round(t_gpu / 3600, 4) if disp == "cuda" else 0.0,
            "horas_reloj": round((time.time() - t0) / 3600, 4), "lote": a.lote, "max_filas": a.max_filas}
    res = resumir(a.salida, a.entrada, info)
    with open(Path(a.salida) / "resumen.json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print("resumen: %d filas, acuerdo global %s, ECE %s, %s filas/s" % (
        res["filas_total"], res["acuerdo_global"], res["ece_maestro"], info["filas_por_s"]), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
