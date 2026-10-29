"""P2b: mide las variantes del perfil móvil (consulta y torre) frente a PyTorch y escribe informe.md.

    python -m model.bench.torre.movil medir RES (--ckpt CKPT | --ckpt-aleatorio) --ampliar DIR --comprobacion DIR --calib JSONL
        [--variantes dinamico ffn-estatico fp16 fp32] [--n-calib 500] [--filas 300] [--vocab-podado JSON]
    python -m model.bench.torre.movil informe RES

`medir` exporta cada variante con el vocabulario completo y con la poda ampliada (`--vocab-ampliar DIR`, ver corpus_poda.py) y escribe
RES/movil.json (se reescribe tras cada variante). `informe` lo vuelve tabla en RES/informe.md.
"""
import argparse
import gc
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import torch

from model.l2 import calibrar as C
from model.l2 import datos as D
from model.l2 import exportar as E
from model.l2.modelo import Codificador, maxsim, texto_opcion

# variante → (--cuant de la consulta, --cuant-torre)
VARIANTES = {"dinamico": ("codificador", "dinamico"), "ffn-estatico": ("ffn-estatico", "ffn-estatico"), "fp16": ("fp16", "fp16"),
             "fp32": ("ninguna", "ninguna")}
MIN_TOP1, MAX_MB = 0.93, 60.0


def percentiles(ts):
    ts = sorted(ts)
    return {"n": len(ts), "p50_ms": ts[len(ts) // 2], "p99_ms": ts[min(int(len(ts) * 0.99), len(ts) - 1)]}


def latencia_consulta(sess, ids, calentar=3):
    """ms por mensaje (lote 1, 1 hilo)."""
    def una(t):
        x = np.array([t], dtype=np.int64)
        t0 = time.perf_counter()
        E.correr(sess, x, np.ones_like(x))
        return (time.perf_counter() - t0) * 1000
    for t in ids[:calentar]:
        una(t)
    return percentiles([una(t) for t in ids])


@torch.no_grad()
def referencia(modelo, enc, filas, textos_h):
    """h de PyTorch para `textos_h`, y por fila choice: S de PyTorch (K,d) y la opción que elige con las torres de PyTorch."""
    h_ref = E.h_torch(modelo, enc, textos_h)
    ops = list(dict.fromkeys(texto_opcion(r, o) for r in filas for o in r["opciones"]))
    h_op = dict(zip(ops, torch.from_numpy(E.h_torch(modelo, enc, ops))))
    S, elegida = [], []
    for r in filas:
        H, m = enc.tokens([r["texto"]])
        s = modelo.ranuras(H, m)
        S.append(s[0].numpy())
        elegida.append(int(maxsim(s, torch.stack([h_op[texto_opcion(r, o)] for o in r["opciones"]]))[0].argmax()))
    return h_ref, S, elegida


@torch.no_grad()
def top1_y_coseno_s(enc, sess_q, sess_t, filas, S_ref, elegida):
    """Acuerdo top-1 de ONNX (consulta y torre) con PyTorch (consulta y torre) y coseno medio de S (por ranura)."""
    ops = list(dict.fromkeys(texto_opcion(r, o) for r in filas for o in r["opciones"]))
    h_op = dict(zip(ops, torch.from_numpy(E.correr_torre(sess_t, E.ids_torre(enc, ops)).astype(np.float32))))
    ok, cos = [], []
    for r, sr, el in zip(filas, S_ref, elegida):
        b = enc.tok(["query: " + r["texto"]], truncation=True, max_length=enc.max_tok)
        S = E.correr(sess_q, np.array(b["input_ids"]), np.array(b["attention_mask"]))
        ok.append(int(maxsim(torch.from_numpy(S), torch.stack([h_op[texto_opcion(r, o)] for o in r["opciones"]]))[0].argmax()) == el)
        cos.append(float(E.cosenos(S[0], sr).mean()))
    return float(np.mean(ok)), float(np.mean(cos)), len(ok)


def medir_variante(nombre, vocab, modelo, enc, encoder, trabajo, ref, cal, textos_h, filas, ids_lat, ids_lat_q, n_calib):
    cq, ct = VARIANTES[nombre]
    t = Path(trabajo)
    ids_t, ids_q = (cal["torre"], cal["consulta"]) if "estatico" in nombre else (None, None)
    res = {"variante": nombre, "vocab": "poda ampliada" if vocab else "completo"}
    t0 = time.time()
    # torre
    pt = t / "torre.onnx"
    inf = E.exportar_torre(encoder, modelo.torre, pt, t / "tw", vocab, cuant=ct, max_len=enc.max_tok, ids_calib=ids_t)
    res["torre_mb"] = inf["mb"]
    sess_t = E.sesion(pt)
    h = E.correr_torre(sess_t, E.ids_torre(enc, textos_h))
    c = E.cosenos(h, ref[0])
    res.update(coseno_h=float(c.mean()), coseno_h_min=float(c.min()), torre=E.latencia_torre(sess_t, ids_lat))
    # consulta
    qenc, remap = E.podar(encoder, vocab) if vocab else (encoder, None)
    q32, pq = t / "q-fp32.onnx", t / "q.onnx"
    E.exportar_onnx(E.Envoltura(qenc, modelo.ranuras, remap), q32, len(remap) if vocab else encoder.get_input_embeddings().weight.shape[0])
    E.cuantizar(q32, pq, cq, True, ids_calib=ids_q)
    res["consulta_mb"] = pq.stat().st_size / 1e6
    sess_q = E.sesion(pq)
    res["top1"], res["coseno_s"], res["n_top1"] = top1_y_coseno_s(enc, sess_q, sess_t, filas, ref[1], ref[2])
    res["consulta"] = latencia_consulta(sess_q, ids_lat_q)
    res["cumple"] = bool(res["top1"] >= MIN_TOP1 and res["torre_mb"] <= MAX_MB and res["consulta_mb"] <= MAX_MB)
    res["segundos"] = round(time.time() - t0, 1)
    for f in t.iterdir():
        f.unlink() if f.is_file() else __import__("shutil").rmtree(f)
    gc.collect()
    return res


def cargar(a):
    from transformers import AutoModel
    modelo, ck = (E.modelo_aleatorio(), None) if a.ckpt_aleatorio else C.cargar_modelo(a.ckpt, "cpu")
    enc = Codificador(device="cpu", max_tok=int((ck or {}).get("max_tok") or a.max_tok))
    ruta = os.environ.get("CHISPA_E5") or "intfloat/multilingual-e5-small"
    encoder = AutoModel.from_pretrained(ruta, attn_implementation="eager", local_files_only=os.path.exists(os.path.expanduser("~/hf/hub"))).eval()
    encoder.load_state_dict(enc.enc.state_dict())
    return modelo.eval(), enc, encoder


def medir(a):
    res_dir = Path(a.res)
    res_dir.mkdir(parents=True, exist_ok=True)
    modelo, enc, encoder = cargar(a)
    base = json.loads(Path(a.vocab_podado).read_text())
    vocab, ampl = E.ampliar_vocab(enc, base, [a.ampliar])
    comp = E.textos_de(a.comprobacion)
    ampl.update(unk_comprobacion_antes=E.fraccion_unk_textos(enc, comp, base), unk_comprobacion_despues=E.fraccion_unk_textos(enc, comp, vocab),
                textos_comprobacion=len(comp))
    print("poda ampliada:", ampl, file=sys.stderr)
    filas = [r for r in E.filas_massive(a.filas) if r["tipo"] == "choice"]
    textos_h = E.textos_golden(a.filas)
    ref = referencia(modelo, enc, filas, textos_h)
    filas_c = D.leer([a.calib])
    filas_c = [r for r in filas_c if r.get("split") == "train"] or filas_c
    corpus = [json.loads(l) for f in sorted(Path(a.ampliar).rglob("*.jsonl")) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    cal = {"torre": E.ids_torre(enc, E.textos_calib(filas_c, a.n_calib)), "consulta": E.ids_calib_consulta(enc, corpus or filas_c, a.n_calib)}
    ids_lat = E.ids_torre(enc, textos_h[::3])
    ids_lat_q = [enc.tok(["query: " + r["texto"]], truncation=True, max_length=enc.max_tok)["input_ids"][0] for r in filas[:100]]
    out = {"poda": ampl, "top1_minimo": MIN_TOP1, "mb_maximo": MAX_MB, "max_tok": enc.max_tok, "aleatorio": bool(a.ckpt_aleatorio), "filas": []}
    for nombre in a.variantes:
        for v in [x for k, x in (("completo", None), ("ampliado", vocab)) if k in a.vocabularios]:
            with tempfile.TemporaryDirectory() as t:
                try:
                    r = medir_variante(nombre, v, modelo, enc, encoder, t, ref, cal, textos_h, filas, ids_lat, ids_lat_q, a.n_calib)
                except Exception as e:   # una variante rota no tira las demás
                    import traceback
                    traceback.print_exc()
                    r = {"variante": nombre, "vocab": "poda ampliada" if v else "completo", "error": "%s: %s" % (type(e).__name__, e)}
            r["unk_comprobacion"] = ampl["unk_comprobacion_despues"] if v else 0.0
            out["filas"].append(r)
            (res_dir / "movil.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
            print(json.dumps(r), file=sys.stderr)
    informe(res_dir)
    return 0


def f(x, d=3):
    return ("%.*f" % (d, x)).replace(".", ",")


def informe(res_dir):
    res_dir = Path(res_dir)
    d = json.loads((res_dir / "movil.json").read_text(encoding="utf-8"))
    p = d["poda"]
    L = ["# P2b: perfil móvil, variantes de consulta y torre", "",
         "Frente a PyTorch fp32 (%s, max_tok %d). Cumple = top-1 ≥ %s y consulta y torre ≤ %d MB." % (
             "pesos aleatorios: solo vale como prueba en seco" if d["aleatorio"] else "checkpoint real", d["max_tok"], f(d["top1_minimo"], 2), d["mb_maximo"]),
         "", "Poda ampliada: %s ids → %s con %s textos del corpus. `<unk>` en la comprobación (%s textos que no están en el corpus): %s %% antes, %s %% después." % (
             p["ids_antes"], p["ids_despues"], p["textos"], p["textos_comprobacion"], f(100 * p["unk_comprobacion_antes"], 2), f(100 * p["unk_comprobacion_despues"], 2)),
         "", "| variante | vocabulario | consulta MB | torre MB | coseno h (media / mín) | coseno S | top-1 | torre p50 / p99 ms | consulta p50 / p99 ms | `<unk>` % | cumple |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in d["filas"]:
        if "error" in r:
            L.append("| %s | %s | FALLO: %s |||||||||" % (r["variante"], r["vocab"], r["error"]))
            continue
        L.append("| %s | %s | %s | %s | %s / %s | %s | %s | %s / %s | %s / %s | %s | %s |" % (
            r["variante"], r["vocab"], f(r["consulta_mb"], 1), f(r["torre_mb"], 1), f(r["coseno_h"]), f(r["coseno_h_min"]), f(r["coseno_s"]), f(r["top1"], 2),
            f(r["torre"]["p50_ms"], 1), f(r["torre"]["p99_ms"], 1), f(r["consulta"]["p50_ms"], 1), f(r["consulta"]["p99_ms"], 1),
            f(100 * r["unk_comprobacion"], 2), "**SÍ**" if r["cumple"] else "no"))
    ok = [r for r in d["filas"] if r.get("cumple")]
    L += ["", "Cumplen: %s." % (", ".join("%s (%s)" % (r["variante"], r["vocab"]) for r in ok) if ok else "ninguna")]
    (res_dir / "informe.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("medir")
    m.add_argument("res")
    m.add_argument("--ckpt")
    m.add_argument("--ckpt-aleatorio", action="store_true")
    m.add_argument("--ampliar", required=True)
    m.add_argument("--comprobacion", required=True)
    m.add_argument("--calib", required=True)
    m.add_argument("--variantes", nargs="+", choices=sorted(VARIANTES), default=list(VARIANTES))
    m.add_argument("--vocabularios", nargs="+", choices=("completo", "ampliado"), default=["completo", "ampliado"],
                   help="el vocabulario completo (fp32: 470 MB por modelo) no cabe en 4 GB: la prueba en seco usa solo «ampliado»")
    m.add_argument("--n-calib", type=int, default=500)
    m.add_argument("--filas", type=int, default=300)
    m.add_argument("--max-tok", type=int, default=E.MAX_TOK)
    m.add_argument("--vocab-podado", default=str(E.VOCAB_PODADO))
    i = sub.add_parser("informe")
    i.add_argument("res")
    a = ap.parse_args(argv)
    if a.cmd == "informe":
        informe(a.res)
        return 0
    if bool(a.ckpt) == bool(a.ckpt_aleatorio):
        ap.error("pide --ckpt o --ckpt-aleatorio")
    return medir(a)


if __name__ == "__main__":
    sys.exit(main())
