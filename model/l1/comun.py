"""Utilidades comunes de model/l1: rutas, tareas, tokenizador estático y embeddings con el runtime Go."""
import glob
import json
import os
import subprocess
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
TAREAS = ("massive", "hatecheck", "clinc150", "inyecciones", "herramientas")
DATOS = "/tmp/lb_datos"
PUNTUACION = list("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
ESPECIALES = (0, 1, 2, 3, 250001)        # <s> <pad> </s> <unk> <mask> de e5: sin vector
BIN_EMBEBER = Path("/tmp/embeber")


def snapshot(repo):
    """Directorio del modelo `org/nombre` en ~/hf."""
    return glob.glob(os.path.expanduser("~/hf/hub/models--%s/snapshots/*" % repo.replace("/", "--")))[0]


def tokenizador_estatico(tok):
    """tokenizer.json de e5 con el normalizador y el pre-tokenizador que exige `runtime/l1/exportar.py`
    (los mismos de potion: espaciado de puntuación ASCII, `\\s+`, strip, Metaspace nuevo). Solo añade
    normalización: las piezas y sus scores son los del Unigram de e5."""
    t = json.loads(json.dumps(tok))
    pre = t["normalizer"]
    assert pre["type"] == "Sequence" and pre["normalizers"][0]["type"] == "Precompiled", pre["type"]
    nuevo = [{"type": "Sequence", "normalizers": pre["normalizers"][:1] + [
        {"type": "Replace", "pattern": {"Regex": " {2,}"}, "content": " "}]}]
    nuevo += [{"type": "Replace", "pattern": {"String": p}, "content": " %s " % p} for p in PUNTUACION]
    nuevo += [{"type": "Replace", "pattern": {"Regex": "\\s+"}, "content": " "},
              {"type": "Strip", "strip_left": True, "strip_right": True}]
    t["normalizer"] = {"type": "Sequence", "normalizers": nuevo}
    t["pre_tokenizer"] = {"type": "Metaspace", "replacement": "▁", "prepend_scheme": "always", "split": False}
    t["truncation"] = None
    t["model"].setdefault("byte_fallback", False)
    return t


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def compilar_embeber():
    if not BIN_EMBEBER.exists():
        subprocess.run(["go", "build", "-o", str(BIN_EMBEBER), "./cmd/embeber"], cwd=AQUI / "go", check=True)
    return BIN_EMBEBER


def embeber(modelo, textos, dim):
    """Embeddings (n × dim, float32, unitarios o cero) de `runtime/l1` sobre un `.chispa-l1`."""
    exe = compilar_embeber()
    salida = "/tmp/embeber-%d.f32" % os.getpid()
    entrada = "".join(json.dumps(t, ensure_ascii=False) + "\n" for t in textos)
    subprocess.run([str(exe), str(modelo), salida], input=entrada.encode(), check=True)
    x = np.fromfile(salida, dtype="<f4").reshape(len(textos), dim)
    os.unlink(salida)
    return x
