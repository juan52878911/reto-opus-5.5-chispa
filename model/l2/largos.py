"""M2, textos largos: qué hacer con el estado que no cabe en `max_tok` (sin reentrenar, con el checkpoint).

    python -m model.l2.largos --ckpt mejor.pt --jevbench RUTA --salida DIR [--max-tok N] [--device cpu] [--max-casos N]

Cinco estrategias sobre los ids de «query: » + texto (el contrato exacto, para el runtime, en `contrato-largos.md`):
  cabeza       los primeros `b` tokens (lo que hace hoy `Codificador`: truncation=True);
  cola         los últimos `b`;
  cabeza_cola  la primera mitad y la última mitad de `b` (la cabeza se queda con el token impar);
  trozos_max   trozos de `b` tokens con solape 32, un pase por trozo; s por opción = máximo entre trozos;
  trozos_media lo mismo, s = media entre trozos.
`b` = max_tok − 2 (<s> y </s>) − tokens del prefijo «query: ». El prefijo se repite en cada ventana. Si el cuerpo cabe en `b`, las
cinco estrategias dan la misma ventana. La agregación va sobre s (MaxSim, antes de la cabeza), y la cabeza (T de choice, a y b de
noul, CORAL de score) se aplica al s agregado, como en `ModeloL2.forward` sin soporte (k = 0).

Salida: `DIR/largos.json` y `DIR/largos.md`: exactitud global, por tipo y en los casos largos (los que la cabeza trunca), con IC95 por
bootstrap sobre casos (percentil, 2000 remuestreos, semilla 0), y el coste (tokens por caso largo). Recomienda una estrategia solo si
gana a `cabeza` con IC que no se solapa en los largos, o si empata (IC solapados) y cuesta menos; si no, deja la cabeza.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from model.evaluacion import metricas as M

from .modelo import MAX_TOK, maxsim, normalizar_mayusculas, texto_consulta, texto_opcion

SOLAPE = 32
ESTRATEGIAS = ("cabeza", "cola", "cabeza_cola", "trozos_max", "trozos_media")
PREFIJO = "query: "
REMUESTREOS = 2000


# ---------------------------------------------------------------- tokenización y ventanas
def tokenizar(tok, texto):
    """(prefijo, cuerpo): ids de «query: » + texto sin especiales; el prefijo son los tokens de «query: »."""
    ids = tok(PREFIJO + normalizar_mayusculas(texto), add_special_tokens=False)["input_ids"]
    n = len(tok(PREFIJO, add_special_tokens=False)["input_ids"])
    return ids[:n], ids[n:]


def presupuesto(prefijo, max_tok):
    """Tokens de cuerpo por ventana: max_tok − <s> − </s> − prefijo."""
    b = max_tok - 2 - len(prefijo)
    if b < 1:
        raise ValueError("max_tok %d no deja sitio para el cuerpo (prefijo de %d tokens)" % (max_tok, len(prefijo)))
    return b


def ventanas(prefijo, cuerpo, max_tok, estrategia, solape=SOLAPE):
    """Lista de ventanas (prefijo + trozo del cuerpo, SIN <s> ni </s>); cada una tiene como mucho max_tok − 2 ids."""
    b = presupuesto(prefijo, max_tok)
    n = len(cuerpo)
    if n <= b:
        return [prefijo + cuerpo]
    if estrategia == "cabeza":
        return [prefijo + cuerpo[:b]]
    if estrategia == "cola":
        return [prefijo + cuerpo[-b:]]
    if estrategia == "cabeza_cola":
        t = b // 2
        return [prefijo + cuerpo[:b - t] + (cuerpo[-t:] if t else [])]
    if estrategia in ("trozos_max", "trozos_media"):
        paso = max(1, b - solape)
        out, ini = [], 0
        while True:
            out.append(prefijo + cuerpo[ini:ini + b])
            if ini + b >= n:
                return out
            ini += paso
    raise ValueError("estrategia desconocida: %r" % (estrategia,))


def con_especiales(tok, ids):
    return [tok.cls_token_id] + list(ids) + [tok.sep_token_id]


def es_largo(prefijo, cuerpo, max_tok):
    """True si la cabeza (el truncado actual) pierde tokens."""
    return len(cuerpo) > presupuesto(prefijo, max_tok)


# ---------------------------------------------------------------- puntuación
@torch.no_grad()
def pase_ids(enc, listas, lote=32):
    """Estados de la última capa (B,T,384) y máscara (B,T) de ventanas ya tokenizadas (con especiales)."""
    Hs, ms = [], []
    for i in range(0, len(listas), lote):
        ls = listas[i:i + lote]
        T = max(len(x) for x in ls)
        ids = torch.full((len(ls), T), enc.tok.pad_token_id, dtype=torch.long)
        m = torch.zeros(len(ls), T, dtype=torch.long)
        for j, x in enumerate(ls):
            ids[j, :len(x)] = torch.tensor(x)
            m[j, :len(x)] = 1
        ids, m = ids.to(enc.device), m.to(enc.device)
        with torch.autocast(enc.device.split(":")[0], dtype=torch.bfloat16, enabled=enc.device != "cpu"):
            h = enc.enc(input_ids=ids, attention_mask=m).last_hidden_state.float()
        Hs.append(h)
        ms.append(m.bool())
    T = max(h.shape[1] for h in Hs)
    H = torch.cat([F.pad(h, (0, 0, 0, T - h.shape[1])) for h in Hs])
    mk = torch.cat([F.pad(m, (0, T - m.shape[1])) for m in ms])
    return H, mk


@torch.no_grad()
def sim_ventanas(modelo, enc, listas, h):
    """s (n_ventanas, U): MaxSim de cada ventana (ids con especiales) contra los vectores de torre h (U,d)."""
    dev = modelo.ranuras.q.device
    H, m = pase_ids(enc, listas)
    return maxsim(modelo.ranuras(H.to(dev), m.to(dev)), h)


def agregar(s, estrategia):
    """s (n_ventanas, U) → (U,)."""
    if estrategia == "trozos_max":
        return s.max(0).values
    if estrategia == "trozos_media":
        return s.mean(0)
    return s[0]


def probs_de_s(modelo, fila, s):
    """Distribución sobre `opciones` a partir de s (U,): la cabeza del modelo, sin soporte (igual que `ModeloL2.forward`)."""
    tipo = fila["tipo"]
    if tipo == "choice":
        T = modelo.log_t["choice"].exp().clamp(min=5e-3)
        return F.softmax(s / T, -1)
    if tipo == "noul":
        a, b = modelo.ab["noul"]
        pt = torch.sigmoid(a * s[0] + b)
        return torch.stack([1 - pt, pt])
    return modelo.coral["score%d" % len(fila["opciones"])](s[:1])[0]


def textos_torre(fila):
    return [texto_opcion(fila, o) for o in fila["opciones"]] if fila["tipo"] == "choice" else [texto_consulta(fila)]


@torch.no_grad()
def predecir_estrategias(modelo, enc, fila, estrategias=ESTRATEGIAS, max_tok=None):
    """{estrategia: {probs: {opción: p}, tokens, ventanas}} para una fila, más `largo`. Las ventanas repetidas se calculan una vez."""
    max_tok = max_tok or enc.max_tok
    dev = modelo.ranuras.q.device
    modelo.asegurar_cabeza("score%d" % len(fila["opciones"]) if fila["tipo"] == "score" else fila["tipo"], dev)
    pref, cuerpo = tokenizar(enc.tok, fila["texto"])
    h = modelo.torre(enc.pasaje(textos_torre(fila)).to(dev))
    vent = {e: [tuple(con_especiales(enc.tok, w)) for w in ventanas(pref, cuerpo, max_tok, e)] for e in estrategias}
    unicas = list(dict.fromkeys(w for ws in vent.values() for w in ws))
    s_por = dict(zip(unicas, sim_ventanas(modelo, enc, [list(w) for w in unicas], h)))
    out = {}
    for e, ws in vent.items():
        s = agregar(torch.stack([s_por[w] for w in ws]), e)
        p = probs_de_s(modelo, fila, s).double().cpu()
        out[e] = {"probs": dict(zip(fila["opciones"], (p / p.sum()).tolist())), "tokens": sum(len(w) for w in ws), "ventanas": len(ws)}
    return {"largo": es_largo(pref, cuerpo, max_tok), "tokens_texto": len(pref) + len(cuerpo), "por": out}


# ---------------------------------------------------------------- estadística
def ic95(ok, remuestreos=REMUESTREOS, semilla=0):
    """(media, bajo, alto): bootstrap percentil sobre casos (ok: 0/1)."""
    ok = np.asarray(ok, dtype=float)
    if len(ok) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.RandomState(semilla)
    medias = ok[rng.randint(0, len(ok), (remuestreos, len(ok)))].mean(1)
    return float(ok.mean()), float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5))


def ic95_diferencia(a, b, remuestreos=REMUESTREOS, semilla=0):
    """IC95 de media(a) − media(b) emparejado por caso."""
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    return ic95(d, remuestreos, semilla)


def recomendar(res, base="cabeza"):
    """(estrategia, motivo). `res[e]` lleva `largos` = {acc, ic: [bajo, alto]} y `coste` = tokens por caso largo.
    Gana si su IC queda por encima del de `base`; empata si los IC se solapan, y entonces solo vale si cuesta menos."""
    b = res[base]
    if b["largos"]["n"] == 0:
        return base, "sin casos largos: no hay nada que comparar"
    ganan, baratas = [], []
    for e, r in res.items():
        if e == base:
            continue
        if r["largos"]["ic"][0] > b["largos"]["ic"][1]:
            ganan.append(e)
        elif r["largos"]["ic"][1] >= b["largos"]["ic"][0] and r["largos"]["ic"][0] <= b["largos"]["ic"][1] and r["coste"] < b["coste"]:
            baratas.append(e)
    if ganan:
        e = max(ganan, key=lambda x: (res[x]["largos"]["acc"], -res[x]["coste"]))
        return e, "gana a %s en los largos con IC95 que no se solapa" % base
    if baratas:
        e = min(baratas, key=lambda x: res[x]["coste"])
        return e, "empata con %s (IC solapados) y cuesta menos" % base
    return base, "ninguna gana con IC que no se solape ni empata siendo más barata"


def resumir(filas, preds, estrategias=ESTRATEGIAS):
    """Tabla por estrategia a partir de `preds[id] = predecir_estrategias(...)`."""
    res = {}
    largos = [r["id"] for r in filas if preds[r["id"]]["largo"]]
    for e in estrategias:
        ok = {r["id"]: float(M.top1(preds[r["id"]]["por"][e]["probs"], r["tipo"], r["opciones"])[0] == r["etiqueta"]) for r in filas}
        por_tipo = defaultdict(list)
        for r in filas:
            por_tipo[r["tipo"]].append(ok[r["id"]])
        okl = [ok[i] for i in largos]
        m, lo, hi = ic95(list(ok.values()))
        ml, lol, hil = ic95(okl)
        lt = defaultdict(list)
        for r in filas:
            if r["id"] in set(largos):
                lt[r["tipo"]].append(ok[r["id"]])
        res[e] = {
            "global": {"n": len(ok), "acc": m, "ic": [lo, hi]},
            "por_tipo": {t: {"n": len(v), "acc": float(np.mean(v))} for t, v in sorted(por_tipo.items())},
            "largos": {"n": len(okl), "acc": ml, "ic": [lol, hil], "por_tipo": {t: {"n": len(v), "acc": float(np.mean(v))} for t, v in sorted(lt.items())}},
            "coste": float(np.mean([preds[i]["por"][e]["tokens"] for i in largos])) if largos else 0.0,
            "ventanas": float(np.mean([preds[i]["por"][e]["ventanas"] for i in largos])) if largos else 0.0,
            "_ok": ok,
        }
    if largos:
        ref = [res["cabeza"]["_ok"][i] for i in largos]
        for e in estrategias:
            m, lo, hi = ic95_diferencia([res[e]["_ok"][i] for i in largos], ref)
            res[e]["largos"]["dif_vs_cabeza"] = {"media": m, "ic": [lo, hi]}
    for e in estrategias:
        del res[e]["_ok"]
    return res


def informe_md(res, rec, n, n_largos, max_tok):
    f = lambda x: "%.3f" % x
    tipos = sorted({t for r in res.values() for t in r["por_tipo"]})
    lin = ["# M2 textos largos (max_tok %d)" % max_tok, "",
           "%d casos, %d largos (la cabeza los trunca). IC95 por bootstrap sobre casos." % (n, n_largos), "",
           "| estrategia | global | IC95 | %s | largos | IC95 largos | Δ vs cabeza (IC95) | tokens/caso largo | pases |" % " | ".join(tipos),
           "|" + "---|" * (8 + len(tipos))]
    for e, r in res.items():
        d = r["largos"].get("dif_vs_cabeza")
        lin.append("| %s | %s | %s–%s | %s | %s | %s–%s | %s | %.0f | %.1f |" % (
            e, f(r["global"]["acc"]), f(r["global"]["ic"][0]), f(r["global"]["ic"][1]),
            " | ".join(f(r["por_tipo"][t]["acc"]) if t in r["por_tipo"] else "-" for t in tipos),
            f(r["largos"]["acc"]) if n_largos else "-", f(r["largos"]["ic"][0]) if n_largos else "-", f(r["largos"]["ic"][1]) if n_largos else "-",
            "%+.3f [%+.3f, %+.3f]" % (d["media"], d["ic"][0], d["ic"][1]) if d else "-", r["coste"], r["ventanas"]))
    lin += ["", "Recomendación: **%s** (%s)." % rec]
    return "\n".join(lin) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--jevbench", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--max-tok", type=int, default=0, help="0 = el del checkpoint (sin él, %d)" % MAX_TOK)
    ap.add_argument("--max-casos", type=int, default=0)
    a = ap.parse_args(argv)
    from model.evaluacion.jevbench import cargar_jevbench
    from .evaluar import cargar_modelo
    from .modelo import Codificador
    filas = cargar_jevbench(a.jevbench)
    if a.max_casos:
        filas = filas[:a.max_casos]
    modelo, ck = cargar_modelo(a.ckpt, a.device)
    max_tok = a.max_tok or ck.get("max_tok", MAX_TOK)
    enc = Codificador(device=a.device, max_tok=max_tok)
    enc.cargar_enc(ck.get("enc"))
    preds = {}
    for i, r in enumerate(filas):
        preds[r["id"]] = predecir_estrategias(modelo, enc, r, max_tok=max_tok)
        if (i + 1) % 25 == 0:
            print("  %d/%d casos" % (i + 1, len(filas)), flush=True)
    res = resumir(filas, preds)
    n_largos = sum(p["largo"] for p in preds.values())
    rec = recomendar(res)
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    (sal / "largos.json").write_text(json.dumps({"max_tok": max_tok, "n": len(filas), "n_largos": n_largos, "estrategias": res,
                                                  "recomendacion": {"estrategia": rec[0], "motivo": rec[1]}}, indent=1, ensure_ascii=False))
    md = informe_md(res, rec, len(filas), n_largos, max_tok)
    (sal / "largos.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
