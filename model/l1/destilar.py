"""Destilación mínima estilo Model2Vec: e5-small -> embedding estático `.chispa-l1`.

    python -m model.l1.destilar --dims 256 --salida /tmp/l1propio [--vocab model/bench/vocab-podado-e5-small.json]

El paquete `model2vec` está instalado pero su `distill` no corre aquí (importa `skeletoken`, que falta y no hay
red), así que se implementa lo mismo con los mismos pasos:
  1. cada pieza del vocabulario podado pasa por e5-small como frase de un token (`<s> pieza </s>`) con el
     pooling medio de e5 (sin prefijo «query: »);
  2. PCA (centrado, sin blanqueo) a `--dims` dimensiones;
  3. ponderación Zipf/SIF: peso = sif / (sif + p(rango)), p ∝ 1/rango, con el rango de la pieza en el Unigram
     completo (orden de score) y sif = 1e-4.
Diferencias con `model2vec.distill`: (a) el vector va en float32 y se cuantiza a int8 por fila al exportar (no
fp16); (b) el tokenizador conserva el Unigram de e5 con el normalizador de potion (espaciado de puntuación), que
es lo que acepta `runtime/l1/exportar.py` sin cambiar el formato; (c) el rango Zipf sale del vocabulario
completo de 250 037 piezas aunque solo se destilen las podadas; (d) las piezas de relleno (`<s>`, `<pad>`, `</s>`,
`<unk>`, `<mask>`) tienen vector cero.
El exportador es `runtime/l1/exportar.py`, sin cambios; este módulo le pasa un directorio de modelo (tokenizer.json,
config.json y model.safetensors con una tabla `embeddings` de tamaño completo, con ceros fuera del vocabulario
podado) y `--vocab`.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from . import comun


def vectores_crudos(dir_e5, ids, cache=None, lote=512):
    """Salida media de e5-small para `<s> id </s>`, una fila por id (float32, 384 columnas)."""
    if cache and Path(cache).exists():
        v = np.load(cache)
        if v.shape[0] == len(ids):
            return v
    import torch
    from transformers import AutoModel
    torch.set_num_threads(4)
    m = AutoModel.from_pretrained(dir_e5).eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(ids), lote):
            b = torch.tensor([[0, int(t), 2] for t in ids[i:i + lote]])
            h = m(input_ids=b, attention_mask=torch.ones_like(b)).last_hidden_state
            out.append(h.mean(dim=1).numpy())
    v = np.concatenate(out).astype(np.float32)
    if cache:
        np.save(cache, v)
    return v


def pesos_sif(scores, sif=1e-4):
    """Peso por pieza del vocabulario completo: rango por score descendente (empates por id), p ∝ 1/rango."""
    n = len(scores)
    orden = np.lexsort((np.arange(n), -np.asarray(scores)))
    rango = np.empty(n)
    rango[orden] = np.arange(1, n + 1)
    p = (1 / rango) / (1 / rango).sum()
    return sif / (sif + p)


def pca(x, dims):
    """Proyección sobre las `dims` primeras componentes principales de x centrado (como sklearn, sin blanqueo)."""
    media = x.mean(axis=0)
    _, _, vt = np.linalg.svd(x - media, full_matrices=False)
    return (x - media) @ vt[:dims].T, vt[:dims], media


def destilar(dir_e5, ids_vocab, dims, salida, sif=1e-4, cache=None, exportar_a=None):
    from safetensors.numpy import save_file
    d = Path(salida)
    d.mkdir(parents=True, exist_ok=True)
    tok = json.loads((Path(dir_e5) / "tokenizer.json").read_text())
    scores = np.array([s for _, s in tok["model"]["vocab"]])
    n = len(scores)
    ids = np.array(sorted(set(int(i) for i in ids_vocab) - set(comun.ESPECIALES)))
    crudo = vectores_crudos(dir_e5, ids, cache)
    red, comp, media = pca(crudo.astype(np.float64), dims)
    red = red * pesos_sif(scores, sif)[ids][:, None]
    tabla = np.zeros((n, dims), dtype=np.float32)
    tabla[ids] = red.astype(np.float32)
    save_file({"embeddings": tabla}, str(d / "model.safetensors"))
    (d / "config.json").write_text(json.dumps({"model_type": "model2vec", "hidden_dim": dims, "normalize": True}))
    (d / "tokenizer.json").write_text(json.dumps(comun.tokenizador_estatico(tok), ensure_ascii=False))
    np.savez(d / "pca.npz", componentes=comp, media=media)
    vocab = d / "vocab.json"
    vocab.write_text(json.dumps({"ids_originales": [int(i) for i in ids]}))
    destino = exportar_a or str(d / ("propio-%d.chispa-l1" % dims))
    r = subprocess.run([sys.executable, str(comun.RAIZ / "runtime/l1/exportar.py"), str(d), destino, "--vocab", str(vocab)],
                       capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("exportar.py falló:\n" + r.stderr[-1500:])
    print(r.stdout.strip())
    return destino


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--modelo", default=comun.snapshot("intfloat/multilingual-e5-small"))
    ap.add_argument("--vocab", default=str(comun.RAIZ / "model/bench/vocab-podado-e5-small.json"))
    ap.add_argument("--dims", type=int, nargs="+", default=[256, 128])
    ap.add_argument("--sif", type=float, default=1e-4)
    ap.add_argument("--salida", default="/tmp/l1propio")
    a = ap.parse_args(argv)
    ids = json.loads(Path(a.vocab).read_text())["ids_originales"]
    for dims in a.dims:
        destilar(a.modelo, ids, dims, "%s/d%d" % (a.salida, dims), a.sif, cache="%s/crudo.npy" % a.salida)


if __name__ == "__main__":
    main()
