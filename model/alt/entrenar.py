"""Entrena la alternativa (b): codificador abierto descongelado + cabeza cross-encoder (`model.alt.modelo`).

    python -m model.alt.entrenar --datos RAIZ --salida DIR [--codificador e5-small|mmbert-small] [--epocas 3] [--lote 16]
                                 [--max-tok 256] [--lr 3e-5] [--semilla 0] [--manifiesto RUTA] [--sellar]

Se niega a arrancar (código 2) si el manifiesto no valida: licencias SA/NC/ND/sin verificar, conjuntos excluidos, conjuntos sin sellar
(filas y sha256; `--sellar` los calcula de los ficheros bajo RAIZ) o ficheros que no coinciden con su sha256. Además comprueba cada fila de
train y dev (`uso_comercial` true, tarea de tsjev admitida). AdamW (la cabeza con lr×10), calentamiento lineal + caída lineal, checkpoint por
época en `DIR/epoca-N/` y el mejor en dev por exactitud en `DIR/mejor/`; el manifiesto se escribe junto a cada checkpoint.
CPU o GPU (`--dispositivo auto`). `--pasos N` corta tras N pasos (pruebas en seco); `--minutos M` corta al pasar M minutos (guarda la época en curso).
"""
import argparse
import json
import random
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import torch

from model.l2.datos import iterar

from .manifiesto import ManifiestoInvalido, cargar, verificar_filas
from .modelo import CrossEncoder


def fijar_semilla(s):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
    torch.cuda.manual_seed_all(s)


def cargar_filas(manifiesto, raiz):
    """(train, dev) de los ficheros del manifiesto bajo `raiz`, ya verificadas contra él."""
    train, dev = [], []
    for c in manifiesto.conjuntos:
        for r in iterar([str(Path(raiz) / c["fichero"])]):
            if r["split"] == "train":
                train.append(r)
            elif r["split"] == "dev":
                dev.append(r)
    verificar_filas(train + dev, manifiesto)
    return train, dev


def exactitud_dev(modelo, dev, lote):
    from .evaluar import predecir
    if not dev:
        return float("nan")
    pr = predecir(modelo, dev, lote)
    return float(np.mean([max(p["probs"], key=p["probs"].get) == r["etiqueta"] for p, r in zip(pr, dev)]))


def tope_por_tarea(filas, tope, semilla=0):
    """Como mucho `tope` filas por `tarea` (barajadas con semilla fija); tope 0 o None = todas."""
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


def entrenar(modelo, manifiesto, train, dev, salida, epocas=3, lote=16, lr=3e-5, pasos=None, peso_blanda=0.5, semilla=0, log=print,
             minutos=None, bf16=False):
    """Con `minutos`, corta (tras guardar la época en curso) al pasar ese tiempo. Devuelve la lista de {epoca, perdida, exactitud_dev}. Escribe epoca-N/ y mejor/ bajo `salida`."""
    dev_, salida = next(modelo.parameters()).device, Path(salida)
    enc = [p for n, p in modelo.named_parameters() if not n.startswith("cabeza")]
    opt = torch.optim.AdamW([{"params": enc, "lr": lr}, {"params": modelo.cabeza.parameters(), "lr": lr * 10}], weight_decay=0.01)
    por_epoca = max(1, -(-len(train) // lote))
    total = min(pasos, por_epoca * epocas) if pasos else por_epoca * epocas
    calent = max(1, total // 10)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min((s + 1) / calent, max(0.0, (total - s) / max(1, total - calent))))
    rng, paso, mejor, hist = random.Random(semilla), 0, -1.0, []
    limite = time.time() + minutos * 60 if minutos else None
    corte = lambda: bool((pasos and paso >= pasos) or (limite and time.time() > limite))  # noqa: E731
    for ep in range(1, epocas + 1):
        modelo.train()
        orden = list(range(len(train)))
        rng.shuffle(orden)
        suma, n, t0 = 0.0, 0, time.time()
        for i in range(0, len(orden), lote):
            if corte():
                break
            fs = [train[j] for j in orden[i:i + lote]]
            opt.zero_grad()
            with torch.autocast("cuda", dtype=torch.bfloat16, enabled=bf16 and dev_.type == "cuda"):
                p = modelo.perdida(fs, peso_blanda)
            p.backward()
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), 1.0)
            opt.step()
            sched.step()
            paso += 1
            suma, n = suma + float(p.detach()), n + 1
            if paso % 50 == 0:
                log("época %d paso %d/%d pérdida %.4f (%.0f s)" % (ep, paso, total, suma / n, time.time() - t0))
        acc = exactitud_dev(modelo, dev, lote)
        hist.append({"epoca": ep, "pasos": paso, "perdida": suma / max(n, 1), "exactitud_dev": acc})
        log("época %d: pérdida %.4f, exactitud dev %.4f" % (ep, hist[-1]["perdida"], acc))
        d = salida / ("epoca-%d" % ep)
        modelo.guardar(d, {"epoca": ep, "exactitud_dev": acc, "semilla": semilla})
        manifiesto.escribir_junto(d)
        if acc > mejor or (np.isnan(acc) and mejor < 0):
            mejor = acc
            shutil.rmtree(salida / "mejor", ignore_errors=True)
            shutil.copytree(d, salida / "mejor")
        if corte():
            break
    (salida / "historial.json").write_text(json.dumps(hist, indent=1), encoding="utf-8")
    return hist


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--datos", required=True, help="raíz con los ficheros del manifiesto")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--manifiesto")
    ap.add_argument("--sellar", action="store_true", help="calcula filas y sha256 de los ficheros bajo --datos antes de validar")
    ap.add_argument("--codificador", default="e5-small")
    ap.add_argument("--pooling", default="media", choices=("media", "cls"))
    ap.add_argument("--epocas", type=int, default=3)
    ap.add_argument("--lote", type=int, default=16)
    ap.add_argument("--max-tok", type=int, default=256)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--peso-blanda", type=float, default=0.5)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--pasos", type=int)
    ap.add_argument("--minutos", type=float, help="tope de tiempo de entrenamiento")
    ap.add_argument("--bf16", action="store_true")
    ap.add_argument("--tope-tarea", type=int, default=1000, help="filas de train por tarea (0 = todas)")
    ap.add_argument("--max-dev", type=int, default=2000)
    ap.add_argument("--dispositivo", default="auto")
    a = ap.parse_args(argv)
    try:
        m = cargar(a.manifiesto) if a.manifiesto else cargar()
        if a.sellar:
            m.sellar(a.datos)
        m.validar(a.datos, sellado=True)
        train, dev = cargar_filas(m, a.datos)
    except (ManifiestoInvalido, OSError) as e:
        print("manifiesto no válido, no se entrena: %s" % e, file=sys.stderr)
        return 2
    fijar_semilla(a.semilla)
    train = tope_por_tarea(train, a.tope_tarea, a.semilla)
    dev = random.Random(a.semilla).sample(dev, min(a.max_dev, len(dev)))
    dis = ("cuda" if torch.cuda.is_available() else "cpu") if a.dispositivo == "auto" else a.dispositivo
    modelo = CrossEncoder.desde_hf(a.codificador, pooling=a.pooling, max_tok=a.max_tok).to(dis)
    print("train %d filas, dev %d, dispositivo %s" % (len(train), len(dev), dis))
    entrenar(modelo, m, train, dev, a.salida, a.epocas, a.lote, a.lr, a.pasos, a.peso_blanda, a.semilla,
             minutos=a.minutos, bf16=a.bf16)
    return 0


if __name__ == "__main__":
    sys.exit(main())
