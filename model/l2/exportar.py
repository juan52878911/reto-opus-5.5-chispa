"""Exportación de L2 a ONNX int8 y empaquetado en `.chispa` v3 (T2.6).

    python -m model.l2.exportar --ckpt DIR --calib calib.json --esquemas A.jsonl [B.jsonl…] --salida l2.chispa
        [--paridad dev.jsonl [--n-paridad 500] [--min-top1 0.95]] [--cuant …] [--sin-poda] [--trabajo DIR]

1. ONNX fp32 del codificador + ranuras: (input_ids, attention_mask) → S ∈ R^{B×K×d}, opset 17. Con vocabulario podado, la
   tabla de embeddings se recorta y el grafo lleva dentro la tabla id original → id podado (los ids son los del tokenizador
   de e5; los que no están pasan a <unk>).
2. int8 dinámico con `onnxruntime.quantization.quantize_dynamic` (`--cuant todo|codificador|ninguna`, `--per-channel`): por
   defecto solo el codificador, por canal y con las ranuras en fp32.
3. Torres de opción en int8 con una escala por vector. Claves de ESQUEMAS (`HashEsquema(pregunta, opciones)`): en `choice`,
   una entrada por opción con `opciones=[opción]`; en `noul` y `score`, una por pregunta con la lista completa de opciones
   (el vector de consulta, `texto_consulta`).
4. `.chispa` v3 con `empaquetar_go` (META, L2, ESQUEMAS, CALIB).
Junto al `.chispa` deja `<salida>.informe.json` con tamaño, paridad y latencia.
"""
import argparse
import base64
import copy
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from . import calibrar as C
from . import datos as D
from .modelo import K_RANURAS, clave_cabeza, maxsim, texto_consulta, texto_opcion

RAIZ = Path(__file__).resolve().parents[2]
VOCAB_PODADO = RAIZ / "model" / "bench" / "vocab-podado-e5-small.json"
GO_DIR = Path(__file__).resolve().parent / "empaquetar_go"
OPSET = 17
MAX_L2_MB = 60
MIN_TOP1 = 0.95


# ---------------------------------------------------------------- grafo
class RanurasExportable(nn.Module):
    """Mismo cálculo que `Ranuras.forward` sin `nn.MultiheadAttention`, cuyo trazado fija el lote y la longitud en el grafo.
    Comparte los pesos; `comprobar` lo contrasta con la original."""

    def __init__(self, r):
        super().__init__()
        self.r, self.h = r, r.atencion.num_heads

    def forward(self, H, mascara):
        r, h = self.r, self.h
        W, b = r.atencion.in_proj_weight, r.atencion.in_proj_bias
        E = W.shape[1]
        Wq, Wk, Wv = W.chunk(3)
        bq, bk, bv = b.chunk(3)
        B = H.shape[0]
        q = F.linear(r.q, Wq, bq).reshape(1, -1, h, E // h).transpose(1, 2)  # (1,h,K,hd)
        k = F.linear(H, Wk, bk).reshape(B, -1, h, E // h).transpose(1, 2)  # (B,h,T,hd)
        v = F.linear(H, Wv, bv).reshape(B, -1, h, E // h).transpose(1, 2)
        sc = q @ k.transpose(-1, -2) / (E // h) ** 0.5  # (B,h,K,T)
        sc = sc + (~mascara).to(sc.dtype)[:, None, None, :] * -1e9
        a = (torch.softmax(sc, -1) @ v).transpose(1, 2).reshape(B, -1, E)
        a = r.atencion.out_proj(a)
        return F.normalize(r.proy(r.norma(r.q.unsqueeze(0) + a)), dim=-1)

    @torch.no_grad()
    def comprobar(self, tol=1e-4):
        H = torch.randn(3, 9, self.r.q.shape[1])
        m = torch.ones(3, 9, dtype=torch.bool)
        m[1, 5:] = False
        d = float((self.eval()(H, m) - self.r.eval()(H, m)).abs().max())
        if d > tol:
            raise RuntimeError("RanurasExportable ya no coincide con Ranuras (%.2g): hay que actualizarla" % d)


class Envoltura(nn.Module):
    """(ids, máscara) → S. Con `remap` (tabla id original → id podado) el grafo acepta los ids del tokenizador original."""

    def __init__(self, encoder, ranuras, remap=None):
        super().__init__()
        self.encoder, self.ranuras = encoder, RanurasExportable(ranuras)
        self.ranuras.comprobar()
        self.register_buffer("remap", remap if remap is not None else torch.zeros(0, dtype=torch.long), persistent=False)

    def forward(self, input_ids, attention_mask):
        if self.remap.numel():
            input_ids = self.remap[input_ids]
        H = self.encoder(input_ids=input_ids, attention_mask=attention_mask, return_dict=False)[0]
        return self.ranuras(H, attention_mask.bool())


def podar(encoder, vocab):
    """(encoder podado, remap). `vocab` = JSON de model/bench: `ids_originales` ordenados, `original`, `unk` (id original)."""
    ids = vocab["ids_originales"]
    emb = encoder.get_input_embeddings()
    if emb.weight.shape[0] != vocab["original"]:
        raise ValueError("el vocabulario podado es de %d ids y el codificador tiene %d" % (vocab["original"], emb.weight.shape[0]))
    if vocab["unk"] not in ids:
        raise ValueError("el id <unk> no está entre los conservados")
    remap = torch.full((vocab["original"],), ids.index(vocab["unk"]), dtype=torch.long)
    remap[torch.tensor(ids)] = torch.arange(len(ids))
    pad = encoder.config.pad_token_id
    if pad is not None and remap[pad] != pad:
        raise ValueError("el relleno cambiaría de id al podar (%d → %d)" % (pad, remap[pad]))
    enc = copy.deepcopy(encoder)
    nuevo = nn.Embedding(len(ids), emb.weight.shape[1], padding_idx=emb.padding_idx)
    nuevo.weight.data = emb.weight.data[torch.tensor(ids)].clone()
    enc.set_input_embeddings(nuevo)
    enc.config.vocab_size = len(ids)
    return enc, remap


def exportar_onnx(env, ruta, vocab_n):
    env.eval()
    ids = torch.randint(5, vocab_n, (2, 16))
    mask = torch.ones_like(ids)
    mask[1, 10:] = 0
    with torch.no_grad():
        torch.onnx.export(env, (ids, mask), str(ruta), input_names=["input_ids", "attention_mask"], output_names=["S"],
                          opset_version=OPSET, dynamo=False,
                          dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}, "S": {0: "b"}})


CUANT = ("todo", "codificador", "ninguna")
PREFIJO_RANURAS = "/ranuras/"


def cuantizar(fp32, int8, modo="codificador", per_channel=True):
    """`todo`: todo el grafo; `codificador`: solo MatMul y Gather (tabla de embeddings) del codificador, con las ranuras
    (atención y proyecciones) en fp32; `ninguna`: copia el fp32."""
    if modo not in CUANT:
        raise ValueError("cuantización %r desconocida (%s)" % (modo, ", ".join(CUANT)))
    if modo == "ninguna":
        shutil.copyfile(fp32, int8)
        return
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic
    kw = {}
    if modo == "codificador":
        nodos = [n for n in onnx.load(str(fp32), load_external_data=False).graph.node if n.name.startswith(PREFIJO_RANURAS)]
        # el preprocesado de ORT parte cada Gemm en «<nombre>_MatMul» + Add antes de excluir: hay que excluir también ese nombre
        nombres = [n.name for n in nodos] + [n.name + "_MatMul" for n in nodos if n.op_type == "Gemm"]
        if not nombres:
            raise RuntimeError("el grafo no tiene nodos %s*: no se pueden dejar las ranuras en fp32" % PREFIJO_RANURAS)
        kw = {"nodes_to_exclude": nombres, "op_types_to_quantize": ["MatMul", "Gather"]}
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8, per_channel=per_channel, **kw)


def sesion(ruta, hilos=1):
    import onnxruntime as ort
    o = ort.SessionOptions()
    o.intra_op_num_threads, o.inter_op_num_threads = hilos, 1
    return ort.InferenceSession(str(ruta), o, providers=["CPUExecutionProvider"])


def correr(sess, ids, mask):
    return sess.run(["S"], {"input_ids": ids.astype(np.int64), "attention_mask": mask.astype(np.int64)})[0]


# ---------------------------------------------------------------- torres
def cuantizar_vec(h):
    """h (d,) → (int8 (d,), escala): escala = máx|h|/127; h ≈ q·escala."""
    m = float(np.abs(h).max())
    esc = m / 127.0 if m > 0 else 1.0
    return np.clip(np.rint(h / esc), -127, 127).astype(np.int8), esc


def entradas_torres(modelo, enc, filas, lote=256):
    """[(pregunta, opciones, vec int8, escala)] únicas; error si una misma clave tiene dos textos de torre distintos."""
    texto_de, claves = {}, []
    for r in filas:
        if r["tipo"] == "choice":
            pares = [((r["pregunta"], (o,)), texto_opcion(r, o)) for o in r["opciones"]]
        else:
            pares = [((r["pregunta"], tuple(r["opciones"])), texto_consulta(r))]
        for k, t in pares:
            if texto_de.setdefault(k, t) != t:
                raise ValueError("la clave %r tiene dos textos de torre distintos (¿descripciones que cambian?)" % (k,))
            if k not in claves:
                claves.append(k)
    out = []
    with torch.no_grad():
        for i in range(0, len(claves), lote):
            ks = claves[i:i + lote]
            h = modelo.torre(enc.pasaje([texto_de[k] for k in ks]).to(modelo.ranuras.q.device)).cpu().numpy()
            for k, v in zip(ks, h):
                q, esc = cuantizar_vec(v)
                out.append((k[0], list(k[1]), q, esc))
    return out


def esquemas_json(torres, dim):
    return {"dim": dim, "entradas": [{"pregunta": p, "opciones": o, "escala": float(np.float32(e)),
                                      "vec": base64.b64encode(q.tobytes()).decode()} for p, o, q, e in torres]}


# ---------------------------------------------------------------- paridad y latencia
def probs_onnx(modelo, enc, sess, filas, torres):
    """Probabilidades de la cabeza del modelo con S del ONNX int8 y torres dequantizadas de ESQUEMAS (lo que hará el runtime)."""
    vec = {(p, tuple(o)): torch.from_numpy(q.astype(np.float32) * np.float32(e)) for p, o, q, e in torres}
    out = []
    for r in filas:
        b = enc.tok(["query: " + r["texto"]], padding=True, truncation=True, max_length=enc.max_tok, return_tensors="pt")
        S = torch.from_numpy(correr(sess, b["input_ids"].numpy(), b["attention_mask"].numpy()))
        if r["tipo"] == "choice":
            h = torch.stack([vec[(r["pregunta"], (o,))] for o in r["opciones"]])
            s = maxsim(S, h)[0]
        else:
            s = maxsim(S, vec[(r["pregunta"], tuple(r["opciones"]))][None])[0]
        clave = clave_cabeza(r)
        out.append(C.probs_de(clave, s, C.cabeza_inicial(modelo, clave)))
    return out


@torch.no_grad()
def paridad(modelo, enc, sess, filas, torres):
    """Python fp32 (`ModeloL2.forward`) frente a ONNX int8 + torres int8: diferencia media y máxima por probabilidad y acuerdo top-1."""
    for r in filas:
        modelo.asegurar_cabeza(clave_cabeza(r))
    ref = []
    for i in range(0, len(filas), 64):
        ref += modelo(filas[i:i + 64], enc, entrenar=False)[0]
    got = probs_onnx(modelo, enc, sess, filas, torres)
    d = np.concatenate([np.abs(a.double().numpy() - b.double().numpy()) for a, b in zip(ref, got)])
    top = np.mean([int(a.argmax()) == int(b.argmax()) for a, b in zip(ref, got)])
    return {"n": len(filas), "dif_media": float(d.mean()), "dif_max": float(d.max()), "acuerdo_top1": float(top)}


def fraccion_unk(enc, filas, vocab):
    """Parte de los tokens de las filas que la poda manda a <unk>: si es alta, la paridad mide la poda y no la cuantización."""
    keep, tot, fuera = set(vocab["ids_originales"]), 0, 0
    for r in filas:
        ids = enc.tok(["query: " + r["texto"]], truncation=True, max_length=enc.max_tok)["input_ids"][0]
        tot += len(ids)
        fuera += sum(int(i) not in keep for i in ids)
    return fuera / max(tot, 1)


def latencia(sess, vocab_n, tokens=(16, 64, 256), reps=50, calentar=5):
    """ms por consulta (lote 1, 1 hilo): media, p50 y p99. Cota en la microVM, no la cifra de c6a."""
    rng = np.random.default_rng(0)
    res = {}
    for n in tokens:
        ids = rng.integers(5, vocab_n, (1, n))
        mask = np.ones((1, n), dtype=np.int64)
        for _ in range(calentar):
            correr(sess, ids, mask)
        ts = []
        for _ in range(reps):
            t = time.perf_counter()
            correr(sess, ids, mask)
            ts.append((time.perf_counter() - t) * 1000)
        ts.sort()
        res[str(n)] = {"media_ms": statistics.fmean(ts), "p50_ms": ts[len(ts) // 2], "p99_ms": ts[min(int(len(ts) * 0.99), len(ts) - 1)]}
    return res


# ---------------------------------------------------------------- empaquetado
def go_bin():
    return shutil.which("go") or os.path.expanduser("~/go-sdk/bin/go")


def empaquetar(meta, onnx, esquemas, calib, salida):
    """Llama a `empaquetar_go` (importa format/chispa3 con `replace`)."""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        for n, c in (("meta.json", meta), ("esquemas.json", esquemas), ("calib.json", calib)):
            (t / n).write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        # GOPROXY=off solo por defecto: en AWS el script fija un proxy (go.mod de format/chispa3 trae kindling).
        env = {"GOFLAGS": "-mod=mod", "GOPROXY": "off", **{k: v for k, v in os.environ.items() if k in ("GOFLAGS", "GOPROXY")}}
        env = {**os.environ, **env}
        p = subprocess.run([go_bin(), "run", ".", "--meta", str(t / "meta.json"), "--l2", str(onnx), "--esquemas", str(t / "esquemas.json"),
                            "--calib", str(t / "calib.json"), "--salida", str(Path(salida).resolve())],
                           cwd=GO_DIR, env=env, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError("empaquetar_go falló:\n" + p.stdout + p.stderr)


def meta_de(filas, dorado=""):
    lic = {}
    for r in filas:
        lic.setdefault(r.get("fuente", "?"), r.get("licencia", "?"))
    return {"version": 1, "tareas": sorted({r["tarea"] for r in filas}), "licencias": lic, "dorado": dorado}


def construir(modelo, enc, encoder, ckpt_info, calib, filas_esq, salida, trabajo, vocab=None, filas_paridad=(), latencias=(16, 64, 256),
              cuant="codificador", per_channel=True):
    """Todo el camino hasta el `.chispa`. `encoder`: módulo HF (atención eager) del que sale el grafo; `vocab`: dict o None."""
    trabajo = Path(trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    remap = None
    if vocab:
        encoder, remap = podar(encoder, vocab)
    n_vocab = encoder.get_input_embeddings().weight.shape[0] if remap is None else len(remap)
    env = Envoltura(encoder, modelo.ranuras, remap)
    fp32, int8 = trabajo / "l2-fp32.onnx", trabajo / "l2-int8.onnx"
    exportar_onnx(env, fp32, n_vocab)
    cuantizar(fp32, int8, cuant, per_channel)
    torres = entradas_torres(modelo, enc, filas_esq)
    dim = int(torres[0][2].shape[0])
    empaquetar(meta_de(filas_esq), int8, esquemas_json(torres, dim), calib["chispa"], salida)
    inf = {"l2_mb": int8.stat().st_size / 1e6, "fp32_mb": fp32.stat().st_size / 1e6, "chispa_mb": Path(salida).stat().st_size / 1e6,
           "torres": len(torres), "vocab_podado": bool(vocab), "cuant": cuant, "per_channel": per_channel, "opset": OPSET, "k_ranuras": K_RANURAS}
    sess = sesion(int8)
    if len(filas_paridad):
        inf["paridad"] = paridad(modelo, enc, sess, list(filas_paridad), torres)
        if vocab:
            inf["paridad"]["tokens_unk"] = fraccion_unk(enc, filas_paridad, vocab)
    if latencias:
        inf["latencia_1_hilo"] = latencia(sess, n_vocab if remap is None else len(remap), latencias)
    inf["torres_entradas"] = torres
    return inf


def comprobar_paridad(inf, minimo):
    """Error si el acuerdo top-1 del informe es menor que `minimo` (sin paridad medida no hay nada que comprobar)."""
    p = inf.get("paridad")
    if p and p["acuerdo_top1"] < minimo:
        raise RuntimeError("paridad: acuerdo top-1 %.3f < %.3f con --cuant %s (dif. media %.2g, máx %.2g)"
                           % (p["acuerdo_top1"], minimo, inf.get("cuant"), p["dif_media"], p["dif_max"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--calib", required=True)
    ap.add_argument("--esquemas", nargs="+", required=True, help="jsonl cuyas preguntas y opciones llevan torre precalculada")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--paridad", nargs="*", default=[], help="jsonl de dev para la paridad")
    ap.add_argument("--n-paridad", type=int, default=500)
    ap.add_argument("--vocab-podado", default=str(VOCAB_PODADO))
    ap.add_argument("--sin-poda", action="store_true", help="no aplicar el vocabulario podado")
    ap.add_argument("--cuant", choices=CUANT, default="codificador",
                    help="todo: todo el grafo en int8; codificador: solo MatMul y embeddings del codificador (ranuras en fp32); ninguna: fp32")
    ap.add_argument("--per-channel", action=argparse.BooleanOptionalAction, default=True, help="pesos int8 con una escala por canal de salida")
    ap.add_argument("--min-top1", type=float, default=MIN_TOP1, help="falla si el acuerdo top-1 con PyTorch queda por debajo")
    ap.add_argument("--trabajo", help="directorio de los ONNX (por defecto, temporal)")
    a = ap.parse_args(argv)
    from transformers import AutoModel
    from .modelo import Codificador
    modelo, ck = C.cargar_modelo(a.ckpt, "cpu")
    enc = Codificador(device="cpu")
    ruta = os.environ.get("CHISPA_E5") or "intfloat/multilingual-e5-small"
    encoder = AutoModel.from_pretrained(ruta, attn_implementation="eager", local_files_only=os.path.exists(os.path.expanduser("~/hf/hub"))).eval()
    encoder.load_state_dict(enc.enc.state_dict())
    calib = json.loads(Path(a.calib).read_text(encoding="utf-8"))
    vocab = None if a.sin_poda else json.loads(Path(a.vocab_podado).read_text())
    filas = D.leer(a.esquemas)
    par = D.leer(a.paridad)[:a.n_paridad] if a.paridad else []
    with tempfile.TemporaryDirectory() as t:
        inf = construir(modelo, enc, encoder, ck, calib, filas, a.salida, a.trabajo or t, vocab, par, cuant=a.cuant, per_channel=a.per_channel)
    inf.pop("torres_entradas")
    Path(a.salida + ".informe.json").write_text(json.dumps(inf, indent=1) + "\n")
    print(json.dumps(inf, indent=1))
    if inf["l2_mb"] > MAX_L2_MB:
        print("AVISO: L2 pesa %.1f MB (> %d MB)" % (inf["l2_mb"], MAX_L2_MB), file=sys.stderr)
    comprobar_paridad(inf, a.min_top1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
