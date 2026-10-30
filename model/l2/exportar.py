"""Exportación de L2 a ONNX int8 y empaquetado en `.chispa` v3 (T2.6).

    python -m model.l2.exportar --ckpt DIR --calib calib.json --esquemas A.jsonl [B.jsonl…] --salida l2.chispa
        [--paridad dev.jsonl [--n-paridad 500] [--min-top1 0.95]] [--cuant …] [--sin-poda] [--trabajo DIR]

1. ONNX fp32 del codificador + ranuras: (input_ids, attention_mask) → S ∈ R^{B×K×d}, opset 17. Con vocabulario podado, la
   tabla de embeddings se recorta y el grafo lleva dentro la tabla id original → id podado (los ids son los del tokenizador
   de e5; los que no están pasan a <unk>).
2. int8 dinámico con `onnxruntime.quantization.quantize_dynamic` (`--cuant todo|codificador|ninguna`, `--per-channel`): por
   defecto solo el codificador, por canal y con las ranuras en fp32.
3. Torres de opción en int8 con una escala por vector. ESQUEMAS v2 con `HashEsquema2` (`clave_torre`, `hash_clave`): en `choice`
   y `multi`, una entrada por opción (kind `choice` / `multi`); en `noul` (false y true) y `score` (todos los niveles), una por pregunta
   (el vector de consulta, `texto_torre_consulta`: la opción `true` / el nivel máximo, no `opciones[-1]`).
4. `.chispa` v3 con `empaquetar_go` (META, L2, ESQUEMAS, CALIB).
Junto al `.chispa` deja `<salida>.informe.json` con tamaño, paridad y latencia.
"""
import argparse
import base64
import copy
import json
import os
import re
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
from .modelo import K_RANURAS, MAX_TOK, clave_cabeza, maxsim, normalizar_mayusculas, texto_opcion

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


class EnvolturaTorre(nn.Module):
    """(ids, máscara) → h (B,256): e5, media ponderada por la máscara, L2, `Torre` (GELU erf) y L2. Contrato: contrato-torre.md.
    El MLP cuelga de `torre` para que sus nodos se llamen «/torre/…» y queden en fp32 al cuantizar."""

    def __init__(self, encoder, torre, remap=None):
        super().__init__()
        self.encoder, self.torre = encoder, torre
        self.register_buffer("remap", remap if remap is not None else torch.zeros(0, dtype=torch.long), persistent=False)

    def forward(self, input_ids, attention_mask):
        if self.remap.numel():
            input_ids = self.remap[input_ids]
        H = self.encoder(input_ids=input_ids, attention_mask=attention_mask, return_dict=False)[0]
        m = attention_mask.unsqueeze(-1).to(H.dtype)
        v = F.normalize((H * m).sum(1) / m.sum(1).clamp(min=1), dim=-1)
        return self.torre(v)


def exportar_onnx(env, ruta, vocab_n, salida="S"):
    env.eval()
    ids = torch.randint(5, vocab_n, (2, 16))
    mask = torch.ones_like(ids)
    mask[1, 10:] = 0
    with torch.no_grad():
        torch.onnx.export(env, (ids, mask), str(ruta), input_names=["input_ids", "attention_mask"], output_names=[salida],
                          opset_version=OPSET, dynamo=False,
                          dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"}, salida: {0: "b"}})


CUANT = ("todo", "codificador", "ninguna", "ffn-estatico", "fp16")
PREFIJO_RANURAS = "/ranuras/"
# FFN de cada capa de e5: MatMul de `intermediate.dense` y de `output.dense`. El `attention.output.dense` no entra (el patrón exige
# «/layer.N/output/…»), ni q/k/v ni los MatMul de la atención, ni LayerNorm, ni las ranuras o la `Torre`.
RE_FFN = re.compile(r"/layer\.\d+/(intermediate|output)/dense/MatMul$")
RE_EMBEDDINGS = re.compile(r"/embeddings/word_embeddings/Gather$")


def nodos_ffn(fp32, embeddings=True):
    """Nombres de los nodos que cuantiza `ffn-estatico`: los MatMul de las FFN (`RE_FFN`) y, con `embeddings`, el Gather de la tabla de
    palabras (lo que más pesa con el vocabulario podado; sin él el modelo móvil no baja de ~90 MB). Todo lo demás queda en fp32."""
    import onnx
    nodos = onnx.load(str(fp32), load_external_data=False).graph.node
    nombres = [n.name for n in nodos if (n.op_type == "MatMul" and RE_FFN.search(n.name))
               or (embeddings and n.op_type == "Gather" and RE_EMBEDDINGS.search(n.name))]
    if not any(RE_FFN.search(n) for n in nombres):
        raise RuntimeError("el grafo no tiene MatMul de FFN (…/layer.N/intermediate|output/dense/MatMul)")
    return nombres


def a_fp16(fp32, salida):
    """Todo el grafo en fp16 (pesos y cálculo) con `onnxruntime.transformers.float16` (en este venv no está `onnxconverter_common`);
    `keep_io_types`: entradas y salidas siguen como estaban (la salida, fp32)."""
    import onnx
    from onnxruntime.transformers.float16 import convert_float_to_float16
    onnx.save(convert_float_to_float16(onnx.load(str(fp32)), keep_io_types=True), str(salida))


def cuantizar(fp32, int8, modo="codificador", per_channel=True, prefijo=PREFIJO_RANURAS, ids_calib=None, metodo_calib="minmax"):
    """`todo`: todo el grafo; `codificador`: solo MatMul y Gather (tabla de embeddings) del codificador, con los nodos
    `prefijo` (las ranuras, o la `Torre`) en fp32; `ninguna`: copia el fp32; `ffn-estatico`: QDQ estático por canal solo en las FFN
    (`nodos_ffn`), calibrado con `ids_calib`; `fp16`: todo en fp16."""
    if modo not in CUANT:
        raise ValueError("cuantización %r desconocida (%s)" % (modo, ", ".join(CUANT)))
    if modo == "ninguna":
        shutil.copyfile(fp32, int8)
        return
    if modo == "fp16":
        return a_fp16(fp32, int8)
    if modo == "ffn-estatico":
        return cuantizar_estatico(fp32, int8, ids_calib, per_channel, metodo_calib, nodos=nodos_ffn(fp32))
    import onnx
    from onnxruntime.quantization import QuantType, quantize_dynamic
    kw = {}
    if modo == "codificador":
        nodos = [n for n in onnx.load(str(fp32), load_external_data=False).graph.node if n.name.startswith(prefijo)]
        # el preprocesado de ORT parte cada Gemm en «<nombre>_MatMul» + Add antes de excluir: hay que excluir también ese nombre
        nombres = [n.name for n in nodos] + [n.name + "_MatMul" for n in nodos if n.op_type == "Gemm"]
        if not nombres:
            raise RuntimeError("el grafo no tiene nodos %s*: no se pueden dejar en fp32" % prefijo)
        kw = {"nodes_to_exclude": nombres, "op_types_to_quantize": ["MatMul", "Gather"]}
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8, per_channel=per_channel, **kw)


def sesion(ruta, hilos=1):
    import onnxruntime as ort
    o = ort.SessionOptions()
    o.intra_op_num_threads, o.inter_op_num_threads = hilos, 1
    return ort.InferenceSession(str(ruta), o, providers=["CPUExecutionProvider"])


def correr(sess, ids, mask, salida="S"):
    return sess.run([salida], {"input_ids": ids.astype(np.int64), "attention_mask": mask.astype(np.int64)})[0]


# ---------------------------------------------------------------- torres
def cuantizar_vec(h):
    """h (d,) → (int8 (d,), escala): escala = máx|h|/127; h ≈ q·escala."""
    m = float(np.abs(h).max())
    esc = m / 127.0 if m > 0 else 1.0
    return np.clip(np.rint(h / esc), -127, 127).astype(np.int8), esc


def hash_clave(pregunta, kind, opciones):
    """`HashEsquema2` (hex de 16 bytes) con el escritor del SDK; `opciones`: pares (id, descripción) en cualquier orden."""
    sdk = str(Path(__file__).resolve().parents[2] / "sdk" / "python")
    if sdk not in sys.path:
        sys.path.insert(0, sdk)
    from chispa import formato
    return formato.hash_esquema2(pregunta, kind, opciones).hex()


POR_OPCION = ("choice", "multi")  # una torre (y una entrada de ESQUEMAS) por opción, como busca server/decide/l2.go


def opcion_consulta(fila):
    """Opción cuya torre es la de consulta: noul, `true` (el runtime la lee así, sea cual sea el orden); score, el nivel máximo."""
    if fila["tipo"] == "noul":
        if "true" not in fila["opciones"]:
            raise ValueError("pregunta noul sin opción «true»: %r" % (fila["pregunta"],))
        return "true"
    try:
        return max(fila["opciones"], key=int)
    except ValueError:
        raise ValueError("pregunta score con niveles no numéricos: %r" % (fila["opciones"],))


def texto_torre_consulta(fila):
    """Texto de la torre de noul y score (ver `opcion_consulta`); `modelo.texto_consulta` usa `opciones[-1]`, igual si el orden es [false, true] / 1..K."""
    return texto_opcion(fila, opcion_consulta(fila))


def clave_torre(fila, opcion=None):
    """(pregunta, kind, ((id, descripción), …)) de ESQUEMAS v2: choice y multi, la de una `opcion`; noul (false y true,
    como `opcionesUnica` del servidor) y score (todos los niveles), la de toda la pregunta."""
    desc = fila.get("descripciones", {})
    if fila["tipo"] in POR_OPCION:
        ops = [opcion]
    elif fila["tipo"] == "noul":
        ops = ["false", "true"]
    else:
        ops = list(fila["opciones"])
    return fila["pregunta"], fila["tipo"], tuple(sorted((o, desc.get(o, "")) for o in ops))


def entradas_torres(modelo, enc, filas, lote=256):
    """[(pregunta, kind, opciones, vec int8, escala)] únicas; error si una misma clave tiene dos textos de torre distintos."""
    texto_de, claves = {}, []
    for r in filas:
        if r["tipo"] in POR_OPCION:
            pares = [(clave_torre(r, o), texto_opcion(r, o)) for o in r["opciones"]]
        else:
            pares = [(clave_torre(r), texto_torre_consulta(r))]
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
                out.append((*k, q, esc))
    return out


def esquemas_json(torres, dim):
    return {"dim": dim, "entradas": [{"pregunta": p, "kind": k, "opciones": [{"id": i, "description": d} for i, d in o],
                                      "escala": float(np.float32(e)), "vec": base64.b64encode(q.tobytes()).decode()}
                                     for p, k, o, q, e in torres]}


# ---------------------------------------------------------------- paridad y latencia
def probs_onnx(modelo, enc, sess, filas, torres):
    """Probabilidades de la cabeza del modelo con S del ONNX int8 y torres dequantizadas de ESQUEMAS (lo que hará el runtime)."""
    vec = {(p, k, tuple(o)): torch.from_numpy(q.astype(np.float32) * np.float32(e)) for p, k, o, q, e in torres}
    out = []
    for r in filas:
        b = enc.tok(["query: " + normalizar_mayusculas(r["texto"])], padding=True, truncation=True, max_length=enc.max_tok, return_tensors="pt")
        S = torch.from_numpy(correr(sess, b["input_ids"].numpy(), b["attention_mask"].numpy()))
        if r["tipo"] == "choice":
            h = torch.stack([vec[clave_torre(r, o)] for o in r["opciones"]])
            s = maxsim(S, h)[0]
        else:
            s = maxsim(S, vec[clave_torre(r)][None])[0]
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
        ids = enc.tok(["query: " + normalizar_mayusculas(r["texto"])], truncation=True, max_length=enc.max_tok)["input_ids"][0]
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


# ---------------------------------------------------------------- torre ONNX (contrato-torre.md)
PREFIJO_TORRE = "/torre/"
SEMILLA_TORRE = 20261029
PREFIJO_PASAJE = "passage: "


CUANT_TORRE = ("ninguna", "dinamico", "estatico", "ffn-estatico", "fp16")
METODOS_CALIB = ("minmax", "percentil")
ESTATICAS = ("estatico", "ffn-estatico")   # las que piden --calib-torre


def poner_meta(ruta, props):
    """Escribe `props` ({clave: valor}) en las `metadata_props` del ONNX, sustituyendo las que ya estén."""
    import onnx
    m = onnx.load(str(ruta))
    for k, v in props.items():
        for p in [p for p in m.metadata_props if p.key == k]:
            m.metadata_props.remove(p)
        m.metadata_props.add(key=k, value=str(v))
    onnx.save(m, str(ruta))


def meta_torre(ruta, dim, max_len=MAX_TOK):
    """Escribe en `metadata_props` lo que lee `chispa train --torre`: dimensión de h, truncado y prefijo del texto."""
    poner_meta(ruta, {"chispa.torre.dim": dim, "chispa.torre.max_len": max_len, "chispa.torre.prefijo": PREFIJO_PASAJE})


def meta_consulta(ruta, max_len=MAX_TOK):
    """`chispa.consulta.max_len`: el truncado (tokens) con que se entrenó el checkpoint; sin él el runtime usa 128."""
    poner_meta(ruta, {"chispa.consulta.max_len": max_len})


def textos_calib(filas, n=500, semilla=0):
    """Hasta `n` textos de torre distintos de las filas, repartidos al azar (semilla fija) y no los primeros: una tarea no los copa."""
    import random
    todos = textos_torre(filas, 10 ** 9)
    return todos if len(todos) <= n else sorted(random.Random(semilla).sample(todos, n), key=todos.index)


def cuantizar_estatico(fp32, int8, ids_calib, per_channel=True, metodo="minmax", prefijo=PREFIJO_TORRE, nodos=None):
    """int8 estático QDQ: MatMul y Gather del codificador con pesos por canal y escalas de activación por tensor ajustadas con
    `ids_calib` (listas de ids sin relleno, de una en una); los nodos `prefijo` (la `Torre`) quedan en fp32. Con `nodos` (nombres)
    solo se cuantizan esos (`nodes_to_quantize`) y `prefijo` no cuenta."""
    import onnx
    from onnxruntime.quantization import CalibrationDataReader, CalibrationMethod, QuantFormat, QuantType, quantize_static
    if not ids_calib:
        raise ValueError("la cuantización estática pide textos de calibración (--calib-torre)")
    if metodo not in METODOS_CALIB:
        raise ValueError("método de calibración %r desconocido (%s)" % (metodo, ", ".join(METODOS_CALIB)))
    if nodos is None:
        fijos = [n for n in onnx.load(str(fp32), load_external_data=False).graph.node if n.name.startswith(prefijo)]
        nombres = [n.name for n in fijos] + [n.name + "_MatMul" for n in fijos if n.op_type == "Gemm"]
        if not nombres:
            raise RuntimeError("el grafo no tiene nodos %s*: no se pueden dejar en fp32" % prefijo)
        sel = {"nodes_to_exclude": nombres}
    else:
        sel = {"nodes_to_quantize": list(nodos)}

    class Lector(CalibrationDataReader):
        def __init__(self):
            self.it = iter(ids_calib)

        def get_next(self):
            t = next(self.it, None)
            return None if t is None else {"input_ids": np.array([t], dtype=np.int64), "attention_mask": np.ones((1, len(t)), dtype=np.int64)}

    metodo_ort = CalibrationMethod.MinMax if metodo == "minmax" else CalibrationMethod.Percentile
    quantize_static(str(fp32), str(int8), Lector(), quant_format=QuantFormat.QDQ, per_channel=per_channel,
                    activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8,
                    op_types_to_quantize=["MatMul", "Gather"], calibrate_method=metodo_ort, **sel)


def ids_calib_consulta(enc, filas, n=500, semilla=0):
    """Ids de hasta `n` textos de mensaje distintos de las filas (con «query: », como los ve la consulta), repartidos al azar; si las
    filas no traen `texto` (las de calibración de torre), los textos de torre."""
    import random
    todos = list(dict.fromkeys(r["texto"] for r in filas if r.get("texto")))
    if not todos:
        return ids_torre(enc, textos_calib(filas, n, semilla))
    todos = todos if len(todos) <= n else sorted(random.Random(semilla).sample(todos, n), key=todos.index)
    return ids_torre(enc, ["query: " + normalizar_mayusculas(t) for t in todos])


def exportar_torre(encoder, torre, ruta_int8, trabajo, vocab=None, cuant="dinamico", per_channel=True, max_len=MAX_TOK, ids_calib=None,
                   metodo_calib="minmax"):
    """ONNX de la torre: (input_ids, attention_mask) → h. `cuant`: ninguna (fp32), dinamico (int8 dinámico por canal; también
    «codificador»/«todo» de `--cuant`) estatico (QDQ calibrado con `ids_calib`), ffn-estatico (QDQ solo en las FFN y la tabla de embeddings) o fp16. Devuelve {mb, fp32_mb, vocab_n}. Con `vocab`
    comparte la tabla podada de la consulta (los ids de entrada siguen siendo los del tokenizador original)."""
    trabajo = Path(trabajo)
    trabajo.mkdir(parents=True, exist_ok=True)
    remap = None
    if vocab:
        encoder, remap = podar(encoder, vocab)
    n_vocab = encoder.get_input_embeddings().weight.shape[0] if remap is None else len(remap)
    fp32 = trabajo / "torre-fp32.onnx"
    exportar_onnx(EnvolturaTorre(encoder, torre, remap), fp32, n_vocab, "h")
    if cuant == "estatico":
        cuantizar_estatico(fp32, ruta_int8, ids_calib, per_channel, metodo_calib)
    else:
        cuantizar(fp32, ruta_int8, "codificador" if cuant == "dinamico" else cuant, per_channel, PREFIJO_TORRE, ids_calib, metodo_calib)
    meta_torre(ruta_int8, int(torre.mlp[-1].out_features), max_len)
    return {"mb": Path(ruta_int8).stat().st_size / 1e6, "fp32_mb": fp32.stat().st_size / 1e6, "vocab_n": n_vocab}


def textos_torre(filas, n):
    """Hasta `n` textos de torre distintos (choice: uno por opción; el resto, el de consulta), en el orden de las filas."""
    vistos = {}
    for r in filas:
        for t in ([texto_opcion(r, o) for o in r["opciones"]] if r["tipo"] in POR_OPCION else [texto_torre_consulta(r)]):
            vistos.setdefault(t, None)
    return list(vistos)[:n]


def ids_torre(enc, textos, max_tok=None):
    """Listas de ids sin relleno (tokenizador original de e5; los textos ya llevan «passage: »), truncadas a `max_tok` (por defecto el del codificador)."""
    return enc.tok(list(textos), truncation=True, max_length=max_tok or getattr(enc, "max_tok", MAX_TOK))["input_ids"]


def correr_torre(sess, ids, lote=32):
    """h ONNX (n,256) para listas de ids de longitud variable, con relleno y máscara por lote."""
    out = []
    for i in range(0, len(ids), lote):
        b = ids[i:i + lote]
        T = max(map(len, b))
        x = np.ones((len(b), T), dtype=np.int64)  # 1 = <pad> de XLM-R
        m = np.zeros((len(b), T), dtype=np.int64)
        for j, t in enumerate(b):
            x[j, :len(t)], m[j, :len(t)] = t, 1
        out.append(correr(sess, x, m, "h"))
    return np.concatenate(out)


@torch.no_grad()
def h_torch(modelo, enc, textos):
    """h de PyTorch fp32 (lo que hoy se precalcula en ESQUEMAS, sin cuantizar)."""
    return modelo.torre(enc.pasaje(list(textos))).numpy()


def cosenos(a, b):
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    return (a * b).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))


@torch.no_grad()
def top1_torres(modelo, enc, sess_q, sess_t, filas, lote=64):
    """Acuerdo top-1 de las filas choice con S del ONNX de consulta y torres ONNX frente a torres PyTorch fp32.
    El margen es el hueco entre la mejor opción y la segunda con las torres PyTorch: con pesos aleatorios es minúsculo y el
    top-1 mide ruido, así que se da también el acuerdo en la mitad de filas con más margen."""
    filas = [r for r in filas if r["tipo"] == "choice"]
    textos = list(dict.fromkeys(texto_opcion(r, o) for r in filas for o in r["opciones"]))
    ref = dict(zip(textos, torch.from_numpy(h_torch(modelo, enc, textos))))
    got = dict(zip(textos, torch.from_numpy(correr_torre(sess_t, ids_torre(enc, textos)).astype(np.float32))))
    ok, margenes = [], []
    for r in filas:
        b = enc.tok(["query: " + normalizar_mayusculas(r["texto"])], truncation=True, max_length=enc.max_tok)
        S = torch.from_numpy(correr(sess_q, np.array(b["input_ids"]), np.array(b["attention_mask"])))
        sa = maxsim(S, torch.stack([ref[texto_opcion(r, o)] for o in r["opciones"]]))[0]
        sb = maxsim(S, torch.stack([got[texto_opcion(r, o)] for o in r["opciones"]]))[0]
        ok.append(int(sa.argmax() == sb.argmax()))
        margenes.append(float(sa.topk(2).values.diff().abs()))
    ok, margenes = np.array(ok), np.array(margenes)
    alto = margenes >= np.median(margenes)
    return {"acuerdo": float(ok.mean()), "n": len(ok), "margen_medio": float(margenes.mean()), "opciones": len(filas[0]["opciones"]),
            "acuerdo_mitad_margen_alto": float(ok[alto].mean()), "margen_mitad_alta": float(margenes[alto].mean())}


# movil: fp16 con la poda ampliada (≈ 89 MB por modelo; top-1 1,00 en esquemas ampliados con --vocab-ampliar y ≈ 0,90 en los que no, por
# `<unk>`). movil-int8: int8 dinámico, para quien prioriza tamaño (top-1 ≈ 0,87). Ver model/bench/torre/resultados-20261029-d1e/movil.md
PERFILES = {"servidor": dict(cuant="ninguna", cuant_torre="ninguna", sin_poda=True),
            "movil": dict(cuant="fp16", cuant_torre="fp16", sin_poda=False),
            "movil-int8": dict(cuant="codificador", cuant_torre="dinamico", sin_poda=False)}


def textos_de(ruta):
    """Textos de un `.txt` (uno por línea) o `.jsonl` (cadenas de `texto`, `text`, `pregunta`, `opciones` y `descripciones`)."""
    ruta = Path(ruta)
    if ruta.is_dir():
        return [t for f in sorted(ruta.rglob("*")) if f.is_file() and f.suffix in (".jsonl", ".txt") for t in textos_de(f)]
    if ruta.suffix != ".jsonl":
        return [l.strip() for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = []
    for l in ruta.read_text(encoding="utf-8").splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        for k in ("texto", "text", "pregunta"):
            if isinstance(r.get(k), str):
                out.append(r[k])
        out += [o for o in r.get("opciones") or [] if isinstance(o, str)]
        out += [d for d in (r.get("descripciones") or {}).values() if isinstance(d, str)]
    return out


def ampliar_vocab(enc, vocab, rutas, lote=512):
    """Une al vocabulario podado los ids de los tokens de los textos de `rutas` (con los prefijos `query: ` y `passage: `)."""
    ids = set(vocab["ids_originales"])
    nuevos = set()
    textos = [t for r in rutas for t in textos_de(r)]
    for pre in ("query: ", "passage: "):
        for i in range(0, len(textos), lote):
            for x in enc.tok([pre + t for t in textos[i:i + lote]], truncation=True, max_length=512)["input_ids"]:
                nuevos.update(int(j) for j in x)
    uni = sorted(ids | nuevos)
    return {**vocab, "ids_originales": uni, "conservados": len(uni)}, {"textos": len(textos), "ids_antes": len(ids), "ids_despues": len(uni)}


def fraccion_unk_textos(enc, textos, vocab):
    """Parte de los tokens de `textos` que la poda manda a <unk>."""
    if not textos:
        return 0.0
    keep = set(vocab["ids_originales"])
    ids = [i for t in ids_torre(enc, textos) for i in t]
    return sum(int(i) not in keep for i in ids) / max(len(ids), 1)


def paridad_torre(modelo, enc, sess_t, textos):
    """Coseno de h ONNX int8 frente a h PyTorch fp32: media, mínimo y p1."""
    c = cosenos(correr_torre(sess_t, ids_torre(enc, textos)), h_torch(modelo, enc, textos))
    return {"n": len(textos), "coseno_medio": float(c.mean()), "coseno_min": float(c.min()), "coseno_p1": float(np.percentile(c, 1))}


def fixture_torre(modelo, enc, sess_t, textos, ruta, decimales=6):
    """JSON para probar el runtime de Go sin PyTorch: textos, ids de entrada (sin relleno) y h esperada (fp32 y ONNX int8)."""
    ids = ids_torre(enc, textos)
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    redondea = lambda a: [[round(float(x), decimales) for x in f] for f in a]
    ruta.write_text(json.dumps({
        "contrato": "model/l2/contrato-torre.md", "max_tok": enc.max_tok, "pad_id": 1, "dim": int(modelo.torre.mlp[-1].out_features),
        "nota": "input_ids sin relleno (attention_mask = unos). h_onnx sale del ONNX int8 exportado con el mismo comando; h_fp32 de PyTorch.",
        "textos": list(textos), "input_ids": ids, "h_fp32": redondea(h_torch(modelo, enc, textos)),
        "h_onnx": redondea(correr_torre(sess_t, ids))}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def modelo_aleatorio(semilla=SEMILLA_TORRE):
    """ModeloL2 con pesos aleatorios y semilla fija (la fidelidad de la cuantización no depende de que esté entrenado)."""
    from .modelo import ModeloL2
    torch.manual_seed(semilla)
    return ModeloL2().eval()


def filas_massive(n, semilla=0, opciones=8):
    """Filas choice inventadas sobre los mensajes de massive-es (validación): la verdadera más `opciones-1` intenciones al azar."""
    import gzip
    import random
    ruta = next(Path(os.path.expanduser("~/hf/hub")).glob("datasets--mteb--amazon_massive_intent/snapshots/*/validation/es.json.gz"))
    with gzip.open(ruta, "rt", encoding="utf-8") as f:
        datos = [json.loads(l) for l in f]
    rng = random.Random(semilla)
    clases = sorted({d["label_text"] for d in datos})
    rng.shuffle(datos)
    from model.datos.massive import DESCRIPCIONES as desc, PREGUNTA
    filas = []
    for i, d in enumerate(datos[:n]):
        ops = [d["label_text"]] + rng.sample([c for c in clases if c != d["label_text"]], opciones - 1)
        rng.shuffle(ops)
        filas.append({"id": "massive:dev:%d" % i, "tarea": "massive", "tipo": "choice", "pregunta": PREGUNTA,
                      "texto": d["text"], "opciones": ops, "descripciones": {o: desc[o] for o in ops}, "etiqueta": d["label_text"]})
    return filas


PREGUNTAS_GOLDEN = ("¿Qué quiere hacer la persona con su asistente?",
                    "Clasifica la petición del usuario según la acción que pide.", "¿A qué dominio pertenece la orden?",
                    "Elige la intención que mejor describe lo que se le pide al asistente de la casa.",
                    "Decide qué intención expresa el texto.")


def textos_golden(n=300):
    """`n` textos de torre distintos de la tarea massive: cada intención con varias redacciones de la pregunta."""
    from model.datos.massive import DESCRIPCIONES, PREGUNTA
    textos = []
    for q in (PREGUNTA,) + PREGUNTAS_GOLDEN:
        for c in sorted(DESCRIPCIONES):
            textos.append(texto_opcion({"pregunta": q, "descripciones": DESCRIPCIONES}, c))
    if len(textos) < n:
        raise ValueError("hay %d textos y se piden %d" % (len(textos), n))
    return textos[:n]


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
        # GOWORK=off: con el go.work del paquete del SDK en la raíz, `-mod=mod` falla ("-mod may only be set to readonly or vendor").
        env = {**os.environ, **env, "GOWORK": "off"}
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


def calib_con_multi(modelo, enc, chispa, filas):
    """CALIB con `multi_l2@<hex>[#<id>]` de los esquemas multi de `filas` (con `etiqueta`) que `chispa` aún no trae (los del dev ya
    vienen de `calibrar`); sin etiquetas variadas en un esquema, L2 no opina en él."""
    hechos = {k.split("#")[0] for k in chispa["tipos"] if k.startswith("multi_l2@")}
    nuevas = [r for r in filas if r["tipo"] == "multi" and "etiqueta" in r and "multi_l2" + C.sufijo_multi(r) not in hechos]
    tipos = C.calibrar_multi_l2(modelo, enc, nuevas)
    return {**chispa, "tipos": {**chispa["tipos"], **tipos}} if tipos else chispa


CABEZAS_L2 = ("choice", "noul", "score2", "score3", "score4", "score5")


def calib_completa(modelo, chispa):
    """CALIB de L2 con todas las cabezas (`CABEZAS_L2` y sus `scoreK#j`): las que `chispa` no trae salen del checkpoint (`cabeza_inicial`,
    θ = 0,5), igual que en `jevbench_l2`; las que trae (de `calibrar` sobre el dev) no se tocan. Así un esquema nuevo de cualquier tipo
    usa en el servidor los parámetros del checkpoint y no los valores por defecto."""
    faltan = {}
    for clave in CABEZAS_L2:
        if clave not in chispa["tipos"]:
            modelo.asegurar_cabeza(clave)
            p = C.cabeza_inicial(modelo, clave)
            faltan[clave] = {**p, "T": p.get("T", 1.0), "theta": 0.5}
    if not faltan:
        return chispa
    nuevas = C.a_calib_chispa({"tipos": faltan, "tau_escalate": chispa.get("tau_escalate", 0.0)})["tipos"]
    return {**chispa, "tipos": {**nuevas, **chispa["tipos"]}}


def construir(modelo, enc, encoder, ckpt_info, calib, filas_esq, salida, trabajo, vocab=None, filas_paridad=(), latencias=(16, 64, 256),
              cuant="codificador", per_channel=True, ids_calib=None):
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
    cuantizar(fp32, int8, cuant, per_channel, ids_calib=ids_calib)
    meta_consulta(int8, enc.max_tok)
    torres = entradas_torres(modelo, enc, filas_esq)
    dim = int(torres[0][3].shape[0])
    empaquetar(meta_de(filas_esq), int8, esquemas_json(torres, dim), calib_con_multi(modelo, enc, calib_completa(modelo, calib["chispa"]), filas_esq), salida)
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


def latencia_torre(sess, ids, calentar=3):
    """ms por texto (lote 1, 1 hilo, una pasada por texto tras calentar): p50 y p99 sobre todos los textos."""
    for t in ids[:calentar]:
        correr_torre(sess, [t])
    ts = []
    for t in ids:
        t0 = time.perf_counter()
        correr_torre(sess, [t])
        ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    return {"n": len(ts), "p50_ms": ts[len(ts) // 2], "p99_ms": ts[min(int(len(ts) * 0.99), len(ts) - 1)]}


def main_torre(a, modelo, enc, encoder, vocab, ampl=None):
    """`--torre-onnx`: exporta, y si se piden, mide la paridad y escribe el fixture."""
    sal = Path(a.torre_onnx)
    sal.parent.mkdir(parents=True, exist_ok=True)
    ids_calib = ids_calib_q = None
    if a.cuant_torre in ESTATICAS or a.cuant in ESTATICAS:
        if not a.calib_torre:
            raise SystemExit("la cuantización estática pide --calib-torre")
        filas_c = D.leer(a.calib_torre)
        filas_c = [r for r in filas_c if r.get("split") == "train"] or filas_c
        tx_c = textos_calib(filas_c, a.n_calib)
        ids_calib = ids_torre(enc, tx_c)
        ids_calib_q = ids_calib_consulta(enc, filas_c, a.n_calib)
        print("calibración estática: %d textos de torre y %d de consulta de %d filas" % (len(ids_calib), len(ids_calib_q), len(filas_c)), file=sys.stderr)
    kw = dict(cuant=a.cuant_torre, per_channel=a.per_channel, max_len=enc.max_tok, ids_calib=ids_calib, metodo_calib=a.metodo_calib)
    with tempfile.TemporaryDirectory() as t:
        import gc
        inf = {"max_len": enc.max_tok, "n_calib": len(ids_calib or []), "perfil": a.perfil, "vocab_ampliado": ampl}
        tg = textos_golden(300) if a.medir_torre else []
        if a.medir_torre and vocab:  # primero y liberado: separa el efecto de la poda del de la cuantización (la VM tiene 4 GB)
            inf["tokens_unk"] = fraccion_unk_textos(enc, tg, vocab)
            sin = Path(t) / "torre-sin-poda-int8.onnx"
            # poda ampliada con los ids de los textos (sin <unk>): exportar el vocabulario completo no cabe en los 4 GB de la VM
            amplio = {**vocab, "ids_originales": sorted(set(vocab["ids_originales"]) | {i for x in ids_torre(enc, tg) for i in x})}
            inf["mb_sin_poda"] = exportar_torre(encoder, modelo.torre, sin, Path(t) / "sp", amplio, **kw)["mb"]
            s_sin = sesion(sin)
            inf["h_sin_poda"] = paridad_torre(modelo, enc, s_sin, tg)
            shutil.rmtree(Path(t) / "sp")
        inf.update(exportar_torre(encoder, modelo.torre, sal, t, vocab, **kw))
        inf.update(vocab_podado=bool(vocab), cuant_torre=a.cuant_torre, cuant=a.cuant, per_channel=a.per_channel, opset=OPSET)
        sess = sesion(sal)
        if a.medir_torre:
            inf["h"] = paridad_torre(modelo, enc, sess, tg)
            inf["latencia_torre"] = latencia_torre(sess, ids_torre(enc, tg[::3]))
            gc.collect()
            q_fp32, q_int8 = Path(t) / "l2-fp32.onnx", Path(t) / "l2-int8.onnx"
            qenc, qremap = podar(encoder, vocab) if vocab else (encoder, None)
            exportar_onnx(Envoltura(qenc, modelo.ranuras, qremap), q_fp32, len(qremap) if vocab else encoder.get_input_embeddings().weight.shape[0])
            cuantizar(q_fp32, q_int8, a.cuant, a.per_channel, ids_calib=ids_calib_q, metodo_calib=a.metodo_calib)
            meta_consulta(q_int8, enc.max_tok)
            q_fp32.unlink()
            s_q, filas_t = sesion(q_int8), filas_massive(300)
            inf["top1_choice"] = top1_torres(modelo, enc, s_q, sess, filas_t)
            if vocab:
                inf["top1_choice_sin_unk"] = top1_torres(modelo, enc, s_q, s_sin, filas_t)
            inf["consulta_mb"] = q_int8.stat().st_size / 1e6
            escribir_leeme(inf, a.medir_torre)
        if a.fixture_torre:
            tx = textos_golden(300)
            largo = " ".join(["Elige la intención que mejor describe el mensaje del usuario, con todos sus matices."] * 12)
            fx = tx[::18][:17] + [texto_opcion({"pregunta": "¿Qué acción pide la persona?", "descripciones": {}}, "alarma_poner"),
                                   texto_opcion({"pregunta": largo, "descripciones": {"x": "Año nuevo: ¿qué pasó? ñandú, café, 日本"}}, "x"),
                                   texto_opcion({"pregunta": "¿Es spam?", "descripciones": {"true": "Mensaje no deseado."}}, "true")]
            fixture_torre(modelo, enc, sess, fx, Path(a.fixture_torre) / "torre.json")
    print(json.dumps(inf, indent=1))
    return 0


def sin_poda(inf):
    if "h_sin_poda" not in inf:
        return ""
    p = inf["h_sin_poda"]
    return ("\nPoda frente a cuantización: con el vocabulario podado %.1f %% de los tokens de estos textos caen en `<unk>` y el coseno\n"
            "baja por eso. Con el mismo vocabulario ampliado con los ids de estos textos (sin `<unk>`; solo cuantización, %.1f MB) el\n"
            "coseno medio es %.6f y el mínimo %.6f.\n"
            % (100 * inf["tokens_unk"], inf["mb_sin_poda"], p["coseno_medio"], p["coseno_min"]))


def escribir_leeme(inf, dir_):
    dir_ = Path(dir_)
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / "paridad.json").write_text(json.dumps(inf, indent=1) + "\n")
    h, t, u, sp = inf["h"], inf["top1_choice"], inf.get("top1_choice_sin_unk"), inf.get("h_sin_poda")
    ok = lambda c: "sí" if c else "NO"
    f = lambda x: ("%.4f" % x).replace(".", ",")
    filas = ["| coseno medio de `h`, ONNX tal como se exporta (poda) vs PyTorch fp32, %d textos | ≥ 0,999 | %s | %s |"
             % (h["n"], f(h["coseno_medio"]), ok(h["coseno_medio"] >= 0.999)),
             "| coseno mínimo / p1 (ídem) | — | %s / %s | — |" % (f(h["coseno_min"]), f(h["coseno_p1"]))]
    if sp:
        filas += ["| coseno medio, solo cuantización (vocabulario ampliado, sin `<unk>`) | ≥ 0,999 | %s | %s |"
                  % (f(sp["coseno_medio"]), ok(sp["coseno_medio"] >= 0.999)),
                  "| coseno mínimo (ídem) | — | %s | — |" % f(sp["coseno_min"])]
    filas.append("| top-1 de choice, torres ONNX (poda) vs torres PyTorch, %d filas × %d opciones | ≥ 0,98 | %s | %s |"
                 % (t["n"], t["opciones"], f(t["acuerdo"]), ok(t["acuerdo"] >= 0.98)))
    if u:
        filas.append("| top-1 de choice, solo cuantización (sin `<unk>`) | ≥ 0,98 | %s | %s |" % (f(u["acuerdo"]), ok(u["acuerdo"] >= 0.98)))
        filas.append("| ídem, mitad de filas con más margen (margen medio %s) | — | %s | — |" % (f(u["margen_mitad_alta"]), f(u["acuerdo_mitad_margen_alto"])))
    filas.append("| tamaño del ONNX de la torre (vocabulario podado: %s) | ≤ 50 MB | %.1f MB (fp32: %.1f) | %s |"
                 % ("sí" if inf["vocab_podado"] else "no", inf["mb"], inf["fp32_mb"], ok(inf["mb"] <= 50)))
    (dir_ / "LEEME.md").write_text("""# Torre de esquemas en ONNX int8: paridad

Generado con `python -m model.l2.exportar --torre-onnx SALIDA --ckpt-aleatorio --medir-torre DIR --fixture-torre DIR`
(semilla %d). e5 de `~/hf`, **pesos de L2 aleatorios con semilla fija** (aquí no está el checkpoint real): la fidelidad de la
cuantización de e5 y de la torre no depende de que estén entrenados.

| medida | objetivo | resultado | cumple |
|---|---|---|---|
%s

Cuantización de la torre: %s, por canal=%s, opset %d, `Torre` en fp32. El ONNX de consulta pesa %.1f MB.

Textos de coseno: tarea massive-es del repo (pregunta real y 6 redacciones × cada intención, con descripciones), en el formato
del contrato (`passage: pregunta · opción · descripción`). Top-1: 300 mensajes de validación de massive-es, 8 opciones cada
uno, con las S del ONNX de consulta en los dos lados: solo cambian las torres.

%s
Top-1 con pesos aleatorios: el margen medio entre la mejor opción y la segunda es %s (softplus·maxsim), así que el acuerdo
mide en buena parte ruido sobre empates casi exactos y no es extrapolable a un checkpoint entrenado. Hay que repetir la
medida con el real.
""" % (SEMILLA_TORRE, "\n".join(filas), inf.get("cuant_torre", inf["cuant"]), inf["per_channel"], inf["opset"], inf["consulta_mb"], sin_poda(inf),
       f(t["margen_medio"])), encoding="utf-8")


def escribir_tabla_perfiles(dir_):
    """DIR/LEEME.md con la tabla de los dos perfiles, a partir de DIR/{servidor,movil}/paridad.json (de `--medir-torre`)."""
    dir_ = Path(dir_)
    inf = {n: json.loads((dir_ / n / "paridad.json").read_text()) for n in sorted(PERFILES)}
    f = lambda x: ("%.4f" % x).replace(".", ",")
    pc = lambda x: ("%.2f %%" % (100 * x)).replace(".", ",")
    filas = []
    for n, i in inf.items():
        am = i.get("vocab_ampliado") or {}
        unk_m = "0 (sin poda)" if not i["vocab_podado"] else ("%s → %s" % (pc(am["unk_antes"]), pc(am["unk_despues"])) if am else pc(i["tokens_unk"]))
        unk_q = "0 (sin poda)" if not i["vocab_podado"] else ("%s → %s" % (pc(am["unk_mensajes_antes"]), pc(am["unk_mensajes_despues"])) if am else "—")
        filas.append("| %s | %.1f | %.1f | %.1f | %s | %s | %s | %s | %s | %s |" % (
            n, i["consulta_mb"], i["mb"], i["consulta_mb"] + i["mb"], f(i["h"]["coseno_medio"]), f(i["h"]["coseno_min"]),
            f(i["top1_choice"]["acuerdo"]), f(i["top1_choice"]["acuerdo_mitad_margen_alto"]), unk_m, unk_q))
    (dir_ / "LEEME.md").write_text(PLANTILLA_PERFILES.replace("@FILAS@", "\n".join(filas)), encoding="utf-8")


PLANTILLA_PERFILES = """# Perfiles del exportador: servidor y móvil

Generado con `python -m model.l2.exportar --torre-onnx SALIDA --ckpt-aleatorio --perfil P [--vocab-ampliar …] --medir-torre DIR/P` y
después `--tabla-perfiles DIR`. e5 de `~/hf` y **pesos de L2 aleatorios con semilla fija**: la fidelidad del codificador y el
% de `<unk>` no dependen del entrenamiento; el top-1 con pesos aleatorios mide en parte empates (margen ~0,001), así que no
extrapola a un checkpoint entrenado.

| perfil | consulta MB | torre MB | total MB | coseno medio de `h` | coseno mín. | top-1 choice (300 filas) | top-1, mitad con más margen | `<unk>` textos de torre massive-es (antes → después) | `<unk>` mensajes massive-es dev |
|---|---|---|---|---|---|---|---|---|---|
@FILAS@

- `servidor`: `--cuant ninguna --cuant-torre ninguna --sin-poda` (fp32, vocabulario completo).
- `movil`: int8 dinámico por canal en consulta (ranuras en fp32) y torre, con el vocabulario podado + `--vocab-ampliar`.
- Coseno y top-1: ONNX tal como se exporta frente a PyTorch fp32 (torres y consulta idénticas en los dos lados del top-1).
- `<unk>` de torre: parte de los tokens de 300 textos de torre de massive-es (pregunta · intención · descripción, con `passage: `) que cae
  en `<unk>`; «antes» = vocabulario podado actual, «después» = ampliado. `<unk>` de mensajes: ídem con 300 mensajes de validación (`query: `).
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt")
    ap.add_argument("--calib")
    ap.add_argument("--esquemas", nargs="+", help="jsonl cuyas preguntas y opciones llevan torre precalculada")
    ap.add_argument("--salida")
    ap.add_argument("--torre-onnx", metavar="SALIDA", help="exporta solo el ONNX int8 de la torre (contrato-torre.md) y sale; no pide --calib, --esquemas ni --salida")
    ap.add_argument("--ckpt-aleatorio", type=int, nargs="?", const=SEMILLA_TORRE, metavar="SEMILLA", help="con --torre-onnx: pesos aleatorios con semilla fija en vez de --ckpt")
    ap.add_argument("--medir-torre", metavar="DIR", help="con --torre-onnx: mide la paridad (300 textos, top-1 de choice) y escribe DIR/LEEME.md y DIR/paridad.json")
    ap.add_argument("--fixture-torre", metavar="DIR", help="con --torre-onnx: escribe DIR/torre.json, el fixture de paridad para Go")
    ap.add_argument("--cuant-torre", choices=CUANT_TORRE,
                    help="con --torre-onnx: ninguna (fp32), dinamico (defecto; int8 dinámico por canal), estatico (QDQ calibrado con --calib-torre), "
                         "ffn-estatico (QDQ por canal solo en las FFN y la tabla de embeddings) o fp16")
    ap.add_argument("--calib-torre", nargs="+", metavar="JSONL", help="con --cuant-torre estatico: filas (split train) cuyos textos de torre calibran las activaciones")
    ap.add_argument("--n-calib", type=int, default=500, help="textos de torre distintos para la calibración estática")
    ap.add_argument("--metodo-calib", choices=METODOS_CALIB, default="minmax", help="rango de las activaciones en la calibración estática")
    ap.add_argument("--max-tok", type=int, default=MAX_TOK, help="tokens de truncado si el checkpoint no guarda el suyo (G.8: 256)")
    ap.add_argument("--paridad", nargs="*", default=[], help="jsonl de dev para la paridad")
    ap.add_argument("--n-paridad", type=int, default=500)
    ap.add_argument("--vocab-podado", default=str(VOCAB_PODADO))
    ap.add_argument("--sin-poda", action="store_true", help="no aplicar el vocabulario podado")
    ap.add_argument("--perfil", choices=sorted(PERFILES), help="servidor = --cuant ninguna --cuant-torre ninguna --sin-poda; "
                    "movil = fp16 en consulta y torre con la poda ampliada con --vocab-ampliar; movil-int8 = lo mismo con int8 dinámico por canal "
                    "(más pequeño, top-1 ≈ 0,87)")
    ap.add_argument("--vocab-ampliar", nargs="+", action="extend", default=[], metavar="JSONL|TXT|DIR",
                    help="une al vocabulario podado los tokens de estos textos (repetible; un directorio = todos sus jsonl y txt; jsonl con texto/pregunta/opciones/descripciones, o txt)")
    ap.add_argument("--tabla-perfiles", metavar="DIR", help="escribe DIR/LEEME.md con DIR/servidor/paridad.json y DIR/movil/paridad.json (de --medir-torre) y sale")
    ap.add_argument("--cuant", choices=CUANT,
                    help="todo: todo el grafo en int8; codificador (defecto): solo MatMul y embeddings del codificador (ranuras en fp32); ninguna: fp32; "
                         "ffn-estatico: QDQ por canal solo en las FFN y la tabla de embeddings, calibrado con --calib-torre; fp16: todo en fp16")
    ap.add_argument("--per-channel", action=argparse.BooleanOptionalAction, default=True, help="pesos int8 con una escala por canal de salida")
    ap.add_argument("--min-top1", type=float, default=MIN_TOP1, help="falla si el acuerdo top-1 con PyTorch queda por debajo")
    ap.add_argument("--trabajo", help="directorio de los ONNX (por defecto, temporal)")
    a = ap.parse_args(argv)
    if a.tabla_perfiles:
        escribir_tabla_perfiles(a.tabla_perfiles)
        return 0
    for k, v in (PERFILES[a.perfil] if a.perfil else {}).items():
        if getattr(a, k) not in (None, False) and getattr(a, k) != v:
            ap.error("--perfil %s fija --%s %s" % (a.perfil, k.replace("_", "-"), v))
        setattr(a, k, v)
    a.cuant, a.cuant_torre = a.cuant or "codificador", a.cuant_torre or "dinamico"
    if a.vocab_ampliar and a.sin_poda:
        ap.error("--vocab-ampliar no tiene sentido con --sin-poda")
    if a.torre_onnx:
        if not (a.ckpt or a.ckpt_aleatorio is not None):
            ap.error("--torre-onnx pide --ckpt o --ckpt-aleatorio")
        if (a.cuant_torre in ESTATICAS or a.cuant == "ffn-estatico") and not a.calib_torre:
            ap.error("la cuantización estática pide --calib-torre")
    else:
        faltan = [f for f in ("ckpt", "calib", "esquemas", "salida") if not getattr(a, f)]
        if faltan:
            ap.error("faltan: " + ", ".join("--" + f for f in faltan))
    from transformers import AutoModel
    from .modelo import Codificador
    modelo, ck = (modelo_aleatorio(a.ckpt_aleatorio), None) if a.ckpt is None and a.torre_onnx else C.cargar_modelo(a.ckpt, "cpu")
    enc = Codificador(device="cpu", max_tok=int((ck or {}).get("max_tok") or a.max_tok))
    ruta = os.environ.get("CHISPA_E5") or "intfloat/multilingual-e5-small"
    encoder = AutoModel.from_pretrained(ruta, attn_implementation="eager", local_files_only=os.path.exists(os.path.expanduser("~/hf/hub"))).eval()
    encoder.load_state_dict(enc.enc.state_dict())
    vocab = None if a.sin_poda else json.loads(Path(a.vocab_podado).read_text())
    ampl = None
    if vocab and a.vocab_ampliar:
        base = vocab
        vocab, ampl = ampliar_vocab(enc, base, a.vocab_ampliar)
        tx, tg = [r["texto"] for r in filas_massive(300)], textos_golden(300)
        ampl.update(unk_antes=fraccion_unk_textos(enc, tg, base), unk_despues=fraccion_unk_textos(enc, tg, vocab),
                    unk_mensajes_antes=fraccion_unk_textos(enc, tx, base), unk_mensajes_despues=fraccion_unk_textos(enc, tx, vocab))
        print("vocabulario ampliado: %s" % ampl, file=sys.stderr)
    if a.torre_onnx:
        return main_torre(a, modelo, enc, encoder, vocab, ampl)
    calib = json.loads(Path(a.calib).read_text(encoding="utf-8"))
    filas = D.leer(a.esquemas)
    par = D.leer(a.paridad)[:a.n_paridad] if a.paridad else []
    ids_q = None
    if a.cuant == "ffn-estatico":
        if not a.calib_torre:
            ap.error("--cuant ffn-estatico pide --calib-torre")
        fc = D.leer(a.calib_torre)
        ids_q = ids_calib_consulta(enc, [r for r in fc if r.get("split") == "train"] or fc, a.n_calib)
    with tempfile.TemporaryDirectory() as t:
        inf = construir(modelo, enc, encoder, ck, calib, filas, a.salida, a.trabajo or t, vocab, par, cuant=a.cuant, per_channel=a.per_channel,
                        ids_calib=ids_q)
    inf.pop("torres_entradas")
    if ampl:
        inf["vocab_ampliado"] = ampl
    Path(a.salida + ".informe.json").write_text(json.dumps(inf, indent=1) + "\n")
    print(json.dumps(inf, indent=1))
    if inf["l2_mb"] > MAX_L2_MB:
        print("AVISO: L2 pesa %.1f MB (> %d MB)" % (inf["l2_mb"], MAX_L2_MB), file=sys.stderr)
    comprobar_paridad(inf, a.min_top1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
