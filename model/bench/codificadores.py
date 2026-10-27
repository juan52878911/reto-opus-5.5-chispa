#!/usr/bin/env python
"""T0.3: latencia de codificadores en CPU x86 (e5-small, mmBERT-small, potion).

Uso (desde cualquier sitio, con `source ~/.profile`):
  python codificadores.py preparar     # exporta ONNX, poda vocabulario, cuantiza int8, comprueba coseno
  python codificadores.py medir        # mide todas las variantes (un subproceso por variante e hilos)
  python codificadores.py informe      # escribe resultados-x86.md
Todo es determinista: semilla fija (SEMILLA) para pesos aleatorios, ids de entrada y orden.
"""
import gzip, json, os, subprocess, sys, time, unicodedata, resource, shutil, platform
from pathlib import Path
import numpy as np

SEMILLA = 20261027
AQUI = Path(__file__).resolve().parent
WORK = AQUI / "work"
HF = Path(os.environ.get("HF_HOME", Path.home() / "hf")) / "hub"
CALENTAMIENTO, REPS = 20, 200
TOKENS, HILOS = (16, 64, 256), (1, 4)
OBJETIVO_PODA = 55_000

MODELOS = {
    "e5-small": dict(dir="models--intfloat--multilingual-e5-small", prefijo="query: ", pesos=True),
    "mmBERT-small": dict(dir="models--jhu-clsp--mmBERT-small", prefijo="", pesos=False),
}


def snap(d):
    return next((HF / d / "snapshots").iterdir())


def textos_massive(split, lang):
    ruta = next((HF / "datasets--mteb--amazon_massive_intent" / "snapshots").iterdir()) / split / f"{lang}.json.gz"
    with gzip.open(ruta, "rt", encoding="utf8") as f:
        return [json.loads(l)["text"] for l in f]


def textos_vocab():
    """Corpus de poda: es train+val, en y pt test (MASSIVE) + hatecheck-es. El test es queda fuera."""
    t = []
    t += textos_massive("train", "es") + textos_massive("validation", "es")
    t += textos_massive("test", "en") + textos_massive("test", "pt")  # solo hay en/pt en test; el test es queda fuera
    import csv
    ruta = next((HF / "datasets--Paul--hatecheck-spanish" / "snapshots").iterdir()) / "test.csv"
    with open(ruta, encoding="utf8") as f:
        t += [r["test_case"] for r in csv.DictReader(f)]
    return t


def frases_prueba():
    """200 frases en español del test de MASSIVE (no usadas para podar), fijas por semilla."""
    t = textos_massive("test", "es")
    idx = np.random.RandomState(SEMILLA).choice(len(t), 200, replace=False)
    return [t[i] for i in sorted(idx)]


def es_latino(pieza):
    p = pieza.replace("▁", "").replace("Ġ", "")
    for c in p:
        if ord(c) < 128:
            continue
        try:
            if not unicodedata.name(c).startswith(("LATIN", "COMBINING")):
                return False
        except ValueError:
            return False
    return True


# ---------------------------------------------------------------- preparar
def cargar_torch(nombre):
    import torch
    from transformers import AutoConfig, AutoModel
    m = MODELOS[nombre]
    d = snap(m["dir"])
    torch.manual_seed(SEMILLA)
    if m["pesos"]:
        mod = AutoModel.from_pretrained(d, attn_implementation="eager")
    else:  # el caché no trae pesos de mmBERT-small: arquitectura real, pesos aleatorios (latencia sí, calidad no)
        cfg = AutoConfig.from_pretrained(d)
        cfg._attn_implementation = "eager"
        mod = AutoModel.from_config(cfg, attn_implementation="eager")
    return mod.eval(), d


def exportar(mod, ruta, vocab_n):
    import torch
    ids = torch.randint(5, vocab_n, (1, 16))
    mask = torch.ones_like(ids)

    class W(torch.nn.Module):
        def __init__(s, m):
            super().__init__(); s.m = m
        def forward(s, input_ids, attention_mask):
            return s.m(input_ids=input_ids, attention_mask=attention_mask, return_dict=False)[0]
    torch.onnx.export(W(mod), (ids, mask), str(ruta), input_names=["input_ids", "attention_mask"],
                      output_names=["last_hidden_state"], opset_version=17, dynamo=False,
                      dynamic_axes={"input_ids": {0: "b", 1: "s"}, "attention_mask": {0: "b", 1: "s"},
                                    "last_hidden_state": {0: "b", 1: "s"}})


def cuantizar(fp32, int8):
    from onnxruntime.quantization import quantize_dynamic, QuantType
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)


def elegir_vocab(tok, n_vocab, especiales, corpus):
    usados = set(especiales)
    for e in tok.encode_batch(corpus, add_special_tokens=False):
        usados.update(e.ids)
    n_usados = len(usados)
    cola = [i for i in range(n_vocab) if i not in usados and es_latino(tok.id_to_token(i) or "\u0000x")]
    for i in cola:
        if len(usados) >= OBJETIVO_PODA:
            break
        usados.add(i)
    return sorted(usados), n_usados


def podar(mod, conservar):
    import torch
    emb = mod.get_input_embeddings()
    nuevo = torch.nn.Embedding(len(conservar), emb.weight.shape[1])
    nuevo.weight.data = emb.weight.data[torch.tensor(conservar)].clone()
    mod.set_input_embeddings(nuevo)
    mod.config.vocab_size = len(conservar)
    return mod


def mapa(conservar, n_vocab, unk):
    m = np.full(n_vocab, conservar.index(unk) if unk in conservar else 0, dtype=np.int64)
    for nuevo, viejo in enumerate(conservar):
        m[viejo] = nuevo
    return m


def coseno():
    """Repite solo la comprobación de coseno sobre los ONNX ya exportados."""
    from tokenizers import Tokenizer
    prueba, res = frases_prueba(), {}
    for nombre, m in MODELOS.items():
        d = snap(m["dir"])
        v = json.loads((AQUI / f"vocab-podado-{nombre}.json").read_text())
        tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        res[nombre] = comprobar_coseno(nombre, tok, prueba, mapa(v["ids_originales"], v["original"], v["unk"]), m["prefijo"], d)
        print(nombre, res[nombre], flush=True)
    (AQUI / "coseno-poda.json").write_text(json.dumps(res, indent=1))


def preparar():
    import torch
    from tokenizers import Tokenizer
    torch.set_num_threads(4)
    WORK.mkdir(exist_ok=True)
    corpus, prueba = textos_vocab(), frases_prueba()
    cos_res = {}
    for nombre, m in MODELOS.items():
        if len(sys.argv) > 2 and nombre != sys.argv[2]:
            continue
        mod, d = cargar_torch(nombre)
        tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        n_vocab = mod.get_input_embeddings().weight.shape[0]
        cfg = json.loads((d / "config.json").read_text())
        especiales = [i for i in {cfg.get("pad_token_id"), cfg.get("bos_token_id"), cfg.get("eos_token_id"),
                                  cfg.get("cls_token_id"), cfg.get("sep_token_id"), cfg.get("mask_token_id"),
                                  tok.token_to_id("<unk>"), 0, 1, 2, 3} if i is not None]
        unk = tok.token_to_id("<unk>")
        unk = 3 if unk is None else unk
        conservar, n_corpus = elegir_vocab(tok, n_vocab, especiales, corpus)
        (AQUI / f"vocab-podado-{nombre}.json").write_text(json.dumps(
            dict(modelo=nombre, original=n_vocab, conservados=len(conservar), de_corpus=n_corpus,
                 unk=unk, ids_originales=conservar)))
        print(nombre, "vocab", n_vocab, "->", len(conservar), "(del corpus:", n_corpus, ")", flush=True)
        import gc
        if not (WORK / f"{nombre}-fp32.onnx").exists():
            exportar(mod, WORK / f"{nombre}-fp32.onnx", n_vocab)
        del mod; gc.collect()
        # la poda parte de los mismos pesos (misma semilla): recarga para no mutar el original
        if not (WORK / f"{nombre}-fp32-podado.onnx").exists():
            mod2, _ = cargar_torch(nombre)
            exportar(podar(mod2, conservar), WORK / f"{nombre}-fp32-podado.onnx", len(conservar))
            del mod2; gc.collect()
        for v in ("", "-podado"):  # cuantizar con 4 GB de RAM: un modelo a la vez, sin torch en memoria
            if not (WORK / f"{nombre}-int8{v}.onnx").exists():
                cuantizar(WORK / f"{nombre}-fp32{v}.onnx", WORK / f"{nombre}-int8{v}.onnx"); gc.collect()
        # coseno podado vs original (artefactos ONNX), y int8 vs fp32 como dato extra
        cos_res[nombre] = comprobar_coseno(nombre, tok, prueba, mapa(conservar, n_vocab, unk), m["prefijo"], d)
        print(nombre, cos_res[nombre], flush=True)
    if len(sys.argv) <= 2:
        (AQUI / "coseno-poda.json").write_text(json.dumps(cos_res, indent=1))


def sesion(ruta, hilos):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads, so.inter_op_num_threads = hilos, 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    return ort.InferenceSession(str(ruta), so, providers=["CPUExecutionProvider"])


def emb_onnx(s, ids):
    mask = np.ones_like(ids)
    h = s.run(None, {"input_ids": ids, "attention_mask": mask})[0]
    v = h.mean(1)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def comprobar_coseno(nombre, tok, prueba, mp, prefijo, d):
    s = {k: sesion(WORK / f"{nombre}-{k}.onnx", 4) for k in ("fp32", "fp32-podado", "int8", "int8-podado")}
    cos = {k: [] for k in ("podado_vs_original_fp32", "podado_vs_original_int8", "int8_vs_fp32")}
    fuera = 0
    for f in prueba:
        ids = np.array([tok.encode(prefijo + f).ids], dtype=np.int64)
        idp = mp[ids]
        fuera += int((~np.isin(ids, np.nonzero(mp != mp[0])[0])).sum()) if False else 0
        a, b = emb_onnx(s["fp32"], ids), emb_onnx(s["fp32-podado"], idp)
        c, e = emb_onnx(s["int8"], ids), emb_onnx(s["int8-podado"], idp)
        cos["podado_vs_original_fp32"].append(float((a * b).sum()))
        cos["podado_vs_original_int8"].append(float((c * e).sum()))
        cos["int8_vs_fp32"].append(float((a * c).sum()))
    out = {k: dict(min=min(v), media=float(np.mean(v)), n=len(v), n_ge_0999=int(sum(x >= 0.999 for x in v)))
           for k, v in cos.items()}
    out["pesos"] = "preentrenados" if MODELOS[nombre]["pesos"] else "ALEATORIOS (sin pesos en el caché)"
    return out


# ---------------------------------------------------------------- medir
def rss_pico_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def trabajador(variante, hilos):
    """Un proceso por (variante, hilos): arranque en frío, luego 16/64/256 tokens."""
    rs = np.random.RandomState(SEMILLA)
    res = dict(variante=variante, hilos=hilos, celdas={})
    if variante == "potion":
        os.environ.update(OMP_NUM_THREADS=str(hilos), OPENBLAS_NUM_THREADS=str(hilos), MKL_NUM_THREADS=str(hilos))
        t0 = time.perf_counter()
        from model2vec import StaticModel
        sm = StaticModel.from_pretrained(str(snap("models--minishlab--potion-multilingual-128M")))
        W = np.asarray(sm.embedding)
        n = W.shape[0]
        def f(ids):
            v = W[ids].mean(0); return v / np.linalg.norm(v)
        f(rs.randint(5, n, 16))
        res["frio_ms"] = (time.perf_counter() - t0) * 1e3
        vocab_n = n
        res["disco_mb"] = (snap("models--minishlab--potion-multilingual-128M") / "model.safetensors").stat().st_size / 1e6
    else:
        t0 = time.perf_counter()
        ruta = WORK / f"{variante}.onnx"
        s = sesion(ruta, hilos)
        nombre = "e5-small" if variante.startswith("e5") else "mmBERT-small"
        v = json.loads((AQUI / f"vocab-podado-{nombre}.json").read_text())
        vocab_n = v["conservados" if "podado" in variante else "original"]
        ids0 = rs.randint(5, vocab_n, (1, 16)).astype(np.int64)
        emb_onnx(s, ids0)
        res["frio_ms"] = (time.perf_counter() - t0) * 1e3
        res["disco_mb"] = ruta.stat().st_size / 1e6
        f = lambda ids: emb_onnx(s, ids[None, :])
    for n in TOKENS:
        entradas = [rs.randint(5, vocab_n, n).astype(np.int64) for _ in range(CALENTAMIENTO + REPS)]
        for x in entradas[:CALENTAMIENTO]:
            f(x)
        t = []
        for x in entradas[CALENTAMIENTO:]:
            a = time.perf_counter(); f(x); t.append((time.perf_counter() - a) * 1e3)
        res["celdas"][str(n)] = dict(p50=float(np.percentile(t, 50)), p99=float(np.percentile(t, 99)), reps=len(t))
    res["rss_mb"] = rss_pico_mb()
    print(json.dumps(res))


VARIANTES = [f"{m}-{p}{v}" for m in MODELOS for p in ("fp32", "int8") for v in ("", "-podado")] + ["potion"]


# Orden de prioridad (la poda no cambia el cómputo del cuerpo, solo la tabla de embeddings): si se
# agota el reloj, lo que no empezó se marca «no medida» en vez de recortar repeticiones.
ORDEN = [("potion", 4), ("potion", 1)] + [
    (f"{m}-{p}-podado", h) for m in ("e5-small",) for h in (4, 1) for p in ("int8", "fp32")] + [
    (f"mmBERT-small-{p}-podado", h) for h in (4, 1) for p in ("int8", "fp32")] + [
    (f"{m}-{p}", h) for m in ("e5-small", "mmBERT-small") for h in (4, 1) for p in ("int8", "fp32")]
LIMITE_INICIO = float(os.environ.get("LIMITE_INICIO", "inf"))  # epoch: no arrancar variantes nuevas pasada esta hora


def medir():
    WORK.mkdir(exist_ok=True)
    out = WORK / "medidas.jsonl"
    hecho = {(json.loads(l)["variante"], json.loads(l)["hilos"]) for l in out.open()} if out.exists() else set()
    for v, h in ORDEN:
        if (v, h) in hecho:
            continue
        if time.time() > LIMITE_INICIO:
            with out.open("a") as f:
                f.write(json.dumps(dict(variante=v, hilos=h, error="tope de tiempo del trabajo (no llegó a empezar)")) + "\n")
            continue
        for intento in (1, 2):
            p = subprocess.run([sys.executable, str(Path(__file__).resolve()), "_trabajador", v, str(h)],
                               capture_output=True, text=True)
            if p.returncode == 0 and p.stdout.strip():
                with out.open("a") as f:
                    f.write(p.stdout.strip().splitlines()[-1] + "\n")
                print("ok", v, h, time.strftime("%H:%M:%S"), flush=True)
                break
            print("fallo", intento, v, h, p.stderr[-300:], flush=True)
        else:
            with out.open("a") as f:
                f.write(json.dumps(dict(variante=v, hilos=h, error=p.stderr.strip().splitlines()[-1][:300] if p.stderr.strip() else "?")) + "\n")


# ---------------------------------------------------------------- informe
def informe():
    filas = [json.loads(l) for l in (WORK / "medidas.jsonl").open()]
    cos = json.loads((AQUI / "coseno-poda.json").read_text())
    cpu = subprocess.run("lscpu", capture_output=True, text=True).stdout
    g = lambda k: next((l.split(":", 1)[1].strip() for l in cpu.splitlines() if l.startswith(k)), "?")
    carga = open("/proc/loadavg").read().split()[:3]
    o = ["# T0.3 Resultados x86 (microVM kindling)", "",
         f"- CPU: {g('Model name')}, {g('CPU(s):')} vCPU, modelo {g('Model:')} paso {g('Stepping')}; "
         "flags relevantes: " + ", ".join(x for x in ("avx", "avx2", "avx512f", "avx_vnni", "avx512_vnni", "fma") if f" {x} " in cpu + " ") + " (sin avx2/VNNI)",
         f"- Carga del host al informar (loadavg 1/5/15 min): {' / '.join(carga)}. Máquina virtual compartida: cifras = cota pesimista; el i7-8700T se mide aparte.",
         f"- Python {platform.python_version()}; onnxruntime/torch/transformers de ~/venv; {CALENTAMIENTO} calentamientos + {REPS} repeticiones por celda; batch 1; semilla {SEMILLA}.",
         "- Latencia = `session.run` + pooling medio + normalización sobre ids ya tokenizados (no incluye tokenizar). RSS pico = `ru_maxrss` del proceso de (variante, hilos), incluye la carga y todas las longitudes. Disco = fichero ONNX (potion: safetensors). Arranque en frío = crear sesión/cargar + primera inferencia, en proceso nuevo.",
         "- Exportación: `torch.onnx.export` (opset 17) y no optimum: optimum 1.17.1 no importa con transformers 5.21 (`is_tf_available`). Int8 = `onnxruntime.quantization.quantize_dynamic` (QInt8, pesos de MatMul y de la tabla de embeddings vía Gather).",
         "- **mmBERT-small: el caché `~/hf` solo trae config y tokenizador, sin pesos.** Se instancia la arquitectura real con pesos aleatorios (semilla fija): la latencia, RSS y tamaño son válidos; calidad/coseno no se pueden juzgar (el coseno de poda sí es válido como prueba de la mecánica, no del contenido).",
         "- La poda conserva ids vistos en MASSIVE (es train+val, en y pt test) y hatecheck-es, más especiales, y rellena hasta ~55 k con piezas de alfabeto latino por orden de id; ids fuera se mapean a `<unk>`. Vocabularios en `vocab-podado-*.json`.",
         "", "## Coseno de la poda (200 frases en español de MASSIVE test, no usadas para podar)", "",
         "| modelo | pesos | vocab original→podado | podado vs original fp32 (mín / media; frases ≥0,999) | podado vs original int8 (mín / media; frases ≥0,999) | int8 vs fp32 (mín / media) |", "|---|---|---|---|---|---|"]
    for n, c in cos.items():
        v = json.loads((AQUI / f"vocab-podado-{n}.json").read_text())
        a, b, i = c["podado_vs_original_fp32"], c["podado_vs_original_int8"], c["int8_vs_fp32"]
        o.append(f"| {n} | {c['pesos']} | {v['original']}→{v['conservados']} | {a['min']:.6f} / {a['media']:.6f}; {a['n_ge_0999']}/{a['n']} | {b['min']:.6f} / {b['media']:.6f}; {b['n_ge_0999']}/{b['n']} | {i['min']:.4f} / {i['media']:.4f} |")
    o += ["", "## Latencias (ms)", "",
          "| modelo | precisión | poda | tokens | hilos | p50 | p99 | RSS pico (MB) | disco (MB) | frío (ms) |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in filas:
        v = r["variante"]
        if v == "potion":
            mod, prec, poda = "potion-multilingual-128M (static)", "fp32", "no"
        else:
            mod, prec, *rest = v.split("-")[0:2] + v.split("-")[2:]
            mod = {"e5": "e5-small", "mmBERT": "mmBERT-small"}[v.split("-")[0]]
            prec = "int8" if "int8" in v else "fp32"; poda = "sí" if "podado" in v else "no"
        if "error" in r:
            o.append(f"| {mod} | {prec} | {poda} | - | {r['hilos']} | no medida: {r['error']} | | | | |"); continue
        for n in TOKENS:
            c = r["celdas"][str(n)]
            o.append(f"| {mod} | {prec} | {poda} | {n} | {r['hilos']} | {c['p50']:.2f} | {c['p99']:.2f} | {r['rss_mb']:.0f} | {r['disco_mb']:.0f} | {r['frio_ms']:.0f} |")
    o += ["", "## Lectura (escrita a mano tras la medición; ver cifras arriba)", "",
          "- Hipótesis refutada en esta VM: e5-small int8 podado a 64 tokens da p99 ≈ 200 ms con 1 hilo y ≈ 744 ms con 4 (no < 15 ms). La CPU no tiene AVX2 ni VNNI (Ivy Bridge), así que int8 dinámico no acelera: es igual o más lento que fp32 (p50 64 tok, 1 hilo: 113 vs 95 ms) y solo gana en RSS y disco.",
          "- 4 hilos es más lento que 1 en los modelos transformer (vCPU compartidas/hiperhilos, hay robo de CPU): usar 1 hilo en esta VM. El i7-8700T (AVX2) debe medirse aparte; no extrapolar de aquí.",
          "- mmBERT-small frente a e5-small (p50 64 tok, 1 hilo, fp32 podado): 183 vs 95 ms (≈1,9×), dentro del 1,5-2× previsto, pero con pesos aleatorios y sin saber su calidad.",
          "- La poda no cambia el cómputo (p50 igual dentro del ruido) pero reduce RSS pico (e5 fp32: 877→305 MB) y disco (470→171 MB; int8 118→43 MB).",
          "- Potion (static) es 100-1000× más rápido (p50 ≈ 0,1 ms), pero su RSS pico es ≈ 1,9 GB y arranca en 12-18 s (carga de model2vec + 512 MB fp32); habría que podar/cuantizar su tabla para móvil.",
          "- Coseno de la poda de e5: media 0,99959 (cumple ≥ 0,999) pero 2/200 frases bajan a ≥ 0,958 porque una pieza léxica (`▁medioambiental`, `▁faculta`) cayó fuera del vocabulario y se mapea a `<unk>`; la regla «cada frase ≥ 0,999» no se cumple del todo. Arreglo: más corpus en es/pt/en en el recorte, o reconvertir las piezas ausentes en subpiezas conservadas."]
    (AQUI / "resultados-x86.md").write_text("\n".join(o) + "\n")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "preparar": preparar()
    elif c == "coseno": coseno()
    elif c == "medir": medir()
    elif c == "informe": informe()
    elif c == "_trabajador": trabajador(sys.argv[2], int(sys.argv[3]))
