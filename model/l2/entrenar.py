"""Entrenamiento de L2 (ranuras + torre + cabezas sobre e5 congelado).

    python -m model.l2.entrenar --salida DIR --datos DIR_CONVERTIDOS [--herramientas] [--meta DIR] [--blandas DIR ...]
        [--max-filas 600000] [--epocas 1] [--minutos M] [--s3 s3://bucket/prefijo] [--dev-max 4000]
        [--descongelar N] [--renombrar P] [--maestro-extra DIR --peso-extra W] [--inicial CKPT]
        [--episodios [--k-min 4 --k-max 32 --vias 16 --frac-meta 0.5 --frac-zeroshot 0.25]]

AdamW (3e-4 ranuras y cabezas, 1e-4 torre), warmup 5 % y coseno, lotes de 64 mensajes con muestreo por tarea (n^0,5).
Checkpoint cada 10 min en `DIR/ultimo.pt` (atómico) y, con `--s3`, subido; `mejor.pt` por macro-F1 medio en dev.
Reanuda solo: si `DIR/ultimo.pt` existe (o está en `--s3`), sigue desde su paso. `--minutos` acota el tiempo de
entrenamiento: tras 30 pasos recalcula el total de pasos con la velocidad medida (una vez, queda en el checkpoint).

T2.2: `--descongelar N` entrena las últimas N capas de e5 (lr `--lr-enc`, 2e-5; recorte de gradiente 1,0 sobre todo). Las dos
torres comparten el codificador, así que los vectores de opción se recalculan con gradiente en cada paso y la caché se invalida
tras cada `opt.step()` (ver `Codificador`). `--renombrar P`: con probabilidad P por fila `choice`, los ids de las opciones pasan a
A, B, C… (se decide por (semilla, paso, id)). `--maestro-extra`: blandas `{id, blanda}` de un segundo maestro, promediadas con
las existentes con peso `--peso-extra`. `--inicial`: pesos de un checkpoint de T2.1 (sin optimizador) si no hay `ultimo.pt`.

T2.1b: `--episodios` entrena con prototipos de soporte (ver `datos.Episodios`): una tarea local por paso, k ejemplos por clase
(k al azar en [`--k-min`, `--k-max`]) como soporte y un lote de consultas disjunto; `--frac-zeroshot` de los pasos va sin soporte, con
meta (como mucho `--frac-meta` de los pasos) o con filas locales. Las épocas se cuentan sobre las filas locales. El dev se mide sin y
con soporte (k = `--k-max`, el de T1.7a) y `mejor.pt` se elige por el segundo.
"""
import argparse
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import torch

from . import datos as D
from .evaluar import macro_f1_medio, predecir
from .modelo import MAX_TOK, Codificador, ModeloL2, SoporteEval, prototipos

CKPT_CADA_S = 600


def copiar(origen, destino):
    """cp local o `aws s3 cp` si alguno es s3://. Con CHISPA_LOCAL=1 el «s3» es /tmp/chispa/s3/<prefijo> (como en arranque.sh).
    Devuelve True si salió bien (un origen ausente en S3 no es un error)."""
    origen, destino = str(origen), str(destino)
    if os.environ.get("CHISPA_LOCAL") == "1":
        origen, destino = [("/tmp/chispa/s3/" + x[5:]) if x.startswith("s3://") else x for x in (origen, destino)]
    elif origen.startswith("s3://") or destino.startswith("s3://"):
        try:
            return subprocess.run(["aws", "s3", "cp", "--only-show-errors", origen, destino]).returncode == 0
        except OSError as e:
            print("aviso: no se pudo ejecutar aws:", e, flush=True)
            return False
    try:
        Path(destino).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, destino)
        return True
    except OSError:
        return False


def guardar(ruta, estado):
    tmp = str(ruta) + ".tmp"
    torch.save(estado, tmp)
    os.replace(tmp, ruta)


def lr_en(paso, total, base, warm=0.05):
    w = max(int(total * warm), 1)
    if paso < w:
        return base * (paso + 1) / w
    return base * 0.5 * (1 + math.cos(math.pi * (paso - w) / max(total - w, 1)))


def _fuera(r):
    from model.meta.muestreo import es_fuera
    return es_fuera(r)


def _tareas_fuera(meta, semilla):
    """Tareas de tasksource del directorio de meta que se dejan fuera (para dejarlas en entrenamiento.json)."""
    from model.meta.muestreo import es_tasksource, lista_fuera
    return lista_fuera({r["tarea"] for f in D.ficheros(meta) for r in D._filas_meta(f, "train") if es_tasksource(r)})


def preparar_filas(a):
    """(filas, info, meta): con `--episodios`, `meta` va aparte (los episodios la usan solo sin soporte); si no, está en `filas`."""
    filas = []
    for d in a.datos:
        filas += D.leer(d, split="train", solo_comercial=True)
    if a.herramientas:
        h = Path(__file__).resolve().parents[1] / "herramientas" / "train.jsonl"
        filas += D.leer(str(h), split="train", solo_comercial=True)
    excl = set(a.excluir_tareas)
    sin_filas = sorted(excl - {D.conjunto(r) for r in filas})
    filas = D.sin_conjuntos(filas, excl)
    info = {"locales": len(filas)}
    if excl:
        info["excluir"] = {"conjuntos": sorted(excl), "sin_filas_locales": sin_filas}
    meta = []
    if a.meta:
        tope = max(a.max_filas - len(filas), 0)
        if getattr(a, "tope_tarea", 0):  # G.8: reparto por tarea con tope; las tareas «fuera» no entran ni gastan cupo
            meta, cuentas, cupo, quit = D.submuestrear_meta_tareas(
                a.meta, tope, a.tope_tarea, a.semilla, fuera=_fuera if getattr(a, "excluir_fuera", False) else None)
            meta = D.sin_conjuntos(meta, excl)
            info["meta"] = {"tareas": len(cuentas), "tope_tarea": a.tope_tarea, "alfa": getattr(a, "alfa", D.ALFA), "fuera": quit,
                            "cupo_total": sum(cupo.values()), "elegidas": len(meta),
                            "tareas_fuera": sorted(_tareas_fuera(a.meta, a.semilla))[:400] if getattr(a, "excluir_fuera", False) else []}
        else:
            meta, cuentas, cupo = D.submuestrear_meta(a.meta, tope, semilla=a.semilla)
            meta = D.sin_conjuntos(meta, excl)
            info["meta"] = {"cuentas": cuentas, "cupo": cupo, "elegidas": len(meta)}
        if not a.episodios:
            filas += meta
            meta = []
    if a.blandas:
        bl = D.cargar_blandas(a.blandas)
        info["blandas"] = D.aplicar_blandas(filas + meta, bl)
        del bl
    if a.maestro_extra:
        ex = D.cargar_simples(a.maestro_extra)
        info["extra"] = {"ids": len(ex), "mezcladas": D.mezclar_extra(filas + meta, ex, a.peso_extra)}
        del ex
    if len(filas) > a.max_filas:  # los datos locales no se recortan a ciegas: submuestreo estable por id
        filas = [r for r in filas if D._u(r["id"], a.semilla) < a.max_filas / len(filas)]
    info["filas"] = len(filas)
    if a.episodios:
        info["meta_filas"] = len(meta)
    return filas, info, meta


def preparar_dev(a):
    dev = []
    for d in a.datos + ([a.meta] if a.meta else []):
        dev += D.leer(d, split="dev", solo_comercial=True)
    dev = D.sin_conjuntos(dev, a.excluir_tareas)
    if getattr(a, "excluir_fuera", False):
        dev = [r for r in dev if not _fuera(r)]
    if len(dev) > a.dev_max:
        dev = [r for r in dev if D._u(r["id"], 1) < a.dev_max / len(dev)]
    return dev


def elegir_kappa(modelo, enc, dev, filas, a, k=2):
    """κ de la rejilla con mayor macro-F1 medio en el dev con `k` ejemplos por clase (el caso en que el soporte estropea).
    Devuelve {"k", "rejilla": {κ: F1}, "kappa"}; el empate lo gana el κ menor. Solo cuentan las tareas del dev con soporte local."""
    por_conjunto = {}
    for r in filas:
        por_conjunto.setdefault(D.conjunto(r), []).append(r)
    con_sop = [r for r in dev if D.conjunto(r) in por_conjunto]
    if not con_sop:
        return None
    res = {}
    for kap in sorted({0.0, *a.elegir_kappa}):
        sop = SoporteEval(por_conjunto, k, a.semilla, kap)
        res[kap], _ = macro_f1_medio(con_sop, predecir(modelo, enc, con_sop, soporte=sop))
        print("κ=%g: dev con soporte k=%d macro-F1 medio %.4f" % (kap, k, res[kap]), flush=True)
    mejor_k = max(sorted(res), key=lambda x: (res[x], -x))
    pos = [x for x in res if x > 0]
    mejor_pos = max(sorted(pos), key=lambda x: (res[x], -x)) if pos else None   # el mejor κ > 0: es el que se compara con κ = 0
    return {"k": k, "filas": len(con_sop), "rejilla": {str(x): v for x, v in res.items()}, "kappa": mejor_k, "kappa_pos": mejor_pos}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--datos", nargs="*", default=[], help="directorios/ficheros convertidos (model.datos.convertir)")
    ap.add_argument("--herramientas", action="store_true", help="añade model/herramientas/train.jsonl (T1.4)")
    ap.add_argument("--meta", help="directorio de metaentrenamiento (model.meta.convertir)")
    ap.add_argument("--blandas", nargs="*", default=[], help="directorios/ficheros con `blanda` (maestro)")
    ap.add_argument("--max-filas", type=int, default=600_000)
    ap.add_argument("--epocas", type=float, default=1.0)
    ap.add_argument("--pasos", type=int, default=0, help="fija el total de pasos (pruebas)")
    ap.add_argument("--lote", type=int, default=64)
    ap.add_argument("--minutos", type=float, default=0, help="tope de reloj de entrenamiento (0 = sin tope)")
    ap.add_argument("--eval-cada", type=int, default=0, help="pasos entre evaluaciones en dev (0 = cada ~1/4 del total)")
    ap.add_argument("--dev-max", type=int, default=4000)
    ap.add_argument("--s3", help="prefijo s3:// (o directorio local) donde subir/bajar los checkpoints")
    ap.add_argument("--ckpt-cada", type=int, default=CKPT_CADA_S, help="segundos entre checkpoints")
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--lr-torre", type=float, default=1e-4)
    ap.add_argument("--descongelar", type=int, default=0, help="entrena las últimas N capas de e5 (0 = congelado)")
    ap.add_argument("--lr-enc", type=float, default=2e-5, help="lr de las capas descongeladas")
    ap.add_argument("--renombrar", type=float, default=0.0, help="prob. por fila choice de renombrar las opciones a A/B/C…")
    ap.add_argument("--maestro-extra", nargs="*", default=[], help="blandas {id, blanda} de un segundo maestro (JSONL)")
    ap.add_argument("--peso-extra", type=float, default=0.5, help="peso del segundo maestro en el promedio de blandas")
    ap.add_argument("--inicial", help="checkpoint (T2.1) de donde tomar los pesos si no hay ultimo.pt")
    ap.add_argument("--episodios", action="store_true", help="entrena por episodios con prototipos de soporte (T2.1b)")
    ap.add_argument("--k-min", type=int, default=4, help="mínimo de ejemplos de soporte por clase en un episodio")
    ap.add_argument("--k-max", type=int, default=32, help="máximo (y k del dev con soporte)")
    ap.add_argument("--vias", type=int, default=16, help="clases por episodio en las tareas choice con más clases")
    ap.add_argument("--frac-meta", type=float, default=0.5, help="tope de la fracción de pasos con datos de meta")
    ap.add_argument("--frac-zeroshot", type=float, default=0.25, help="fracción de pasos sin soporte")
    ap.add_argument("--cache-mensajes", action="store_true", help="guarda los estados e5 de cada mensaje (pruebas en seco)")
    ap.add_argument("--excluir-tareas", type=lambda x: [t for t in x.split(",") if t], default=[],
                    help="conjuntos (datos.conjunto) cuyas filas se quitan de train, meta y dev, p. ej. massive,hatecheck,inyecciones")
    ap.add_argument("--excluir-fuera", action="store_true",
                    help="quita también las tareas de tasksource de la lista fija con semilla (model.meta.muestreo.es_fuera)")
    ap.add_argument("--tope-tarea", type=int, default=0,
                    help="filas máx. por tarea de meta (0 = reparto por fuente de siempre); activa el reparto por tarea (G.8)")
    ap.add_argument("--alfa", type=float, default=D.ALFA, help="p(tarea) ∝ n^alfa al muestrear (G.8: 0,3)")
    ap.add_argument("--max-tok", type=int, default=MAX_TOK, help="tokens de e5 por mensaje y por opción (G.8: 256)")
    ap.add_argument("--kappa", type=float, default=0.0, help="shrinkage del soporte del dev con soporte (0 = como siempre)")
    ap.add_argument("--elegir-kappa", type=float, nargs="*", default=[],
                    help="al final, mide el dev con soporte de k=2 para cada κ y deja el mejor en entrenamiento.json (`kappa_dev`)")
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    a = ap.parse_args(argv)
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(a.semilla)
    t_ini = time.time()

    filas, info, meta = preparar_filas(a)
    dev = preparar_dev(a)
    print("datos:", json.dumps(info, ensure_ascii=False)[:1500], "dev:", len(dev), flush=True)
    if not filas:
        print("error: sin filas de train", file=sys.stderr)
        return 2
    if a.episodios:
        mues = D.Episodios(filas, meta, a.lote, a.k_min, a.k_max, a.vias, a.frac_zeroshot, a.frac_meta, alfa=a.alfa, semilla=a.semilla)
        print("episodios: %d tareas con soporte, %d filas locales, %d de meta, p(sin soporte)=%.2f" % (
            len(mues.tareas), len(filas), len(meta), mues.frac_zeroshot), flush=True)
    else:
        mues = D.Muestreador(filas, a.lote, a.alfa, semilla=a.semilla)
    total = a.pasos or int(mues.pasos_por_epoca() * a.epocas)
    claves = sorted({"score%d" % len(r["opciones"]) for r in filas + meta if r["tipo"] == "score"})
    sop_dev = None
    if a.episodios:
        por_conjunto = {}
        for r in filas:
            por_conjunto.setdefault(D.conjunto(r), []).append(r)
        sop_dev = SoporteEval(por_conjunto, a.k_max, a.semilla, a.kappa)

    enc = Codificador(device=a.device, max_tok=a.max_tok, cache_mensajes=a.cache_mensajes, descongelar=a.descongelar)
    modelo = ModeloL2().to(a.device)
    for k in claves:
        modelo.asegurar_cabeza(k, a.device)

    def nuevo_opt():
        g = modelo.grupos_optimizador(a.lr, a.lr_torre)
        if a.descongelar:
            g.append({"params": enc.parametros_entrenables(), "lr": a.lr_enc, "weight_decay": 0.0})
        return torch.optim.AdamW(g)
    opt = nuevo_opt()
    bases = [g["lr"] for g in opt.param_groups]
    paso, mejor, calibrado = 0, {"f1": -1, "paso": -1}, bool(a.pasos or not a.minutos)

    ultimo = sal / "ultimo.pt"
    if not ultimo.exists() and a.s3:
        copiar(a.s3.rstrip("/") + "/ultimo.pt", ultimo)
    if not ultimo.exists() and a.inicial:
        ck = torch.load(a.inicial, map_location=a.device, weights_only=False)
        for k in ck.get("cabezas", []):
            modelo.asegurar_cabeza(k, a.device)
        modelo.load_state_dict(ck["modelo"])
        enc.cargar_enc(ck.get("enc"))
        opt = nuevo_opt()
        print("pesos iniciales de %s (paso %s de ese entrenamiento)" % (a.inicial, ck.get("paso")), flush=True)
    if ultimo.exists():
        ck = torch.load(ultimo, map_location=a.device, weights_only=False)
        for k in ck.get("cabezas", []):
            modelo.asegurar_cabeza(k, a.device)
        opt = nuevo_opt()
        modelo.load_state_dict(ck["modelo"])
        enc.cargar_enc(ck.get("enc"))
        opt.load_state_dict(ck["opt"])
        paso, total, mejor, calibrado = ck["paso"], ck["total"], ck["mejor"], ck["calibrado"]
        print("reanudado en el paso %d de %d" % (paso, total), flush=True)

    def estado():
        return {"modelo": modelo.state_dict(), "opt": opt.state_dict(), "paso": paso, "total": total, "mejor": mejor,
                "calibrado": calibrado, "cabezas": sorted(modelo.coral.keys()), "args": vars(a),
                "enc": enc.estado_enc(), "max_tok": enc.max_tok}

    def checkpoint(sube=True):
        guardar(ultimo, estado())
        if sube and a.s3:
            copiar(ultimo, a.s3.rstrip("/") + "/ultimo.pt")
            if (sal / "mejor.pt").exists():
                copiar(sal / "mejor.pt", a.s3.rstrip("/") + "/mejor.pt")

    parar = []
    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, lambda *_: parar.append(1))

    def evaluar_dev():
        if not dev:
            return
        f1, _ = macro_f1_medio(dev, predecir(modelo, enc, dev))
        if sop_dev:
            sop_dev.cache.limpiar()  # los pesos cambiaron
            f1_sin = f1
            f1, _ = macro_f1_medio(dev, predecir(modelo, enc, dev, soporte=sop_dev))
            print("dev paso %d: macro-F1 medio sin soporte %.4f, con soporte (k=%d) %.4f" % (paso, f1_sin, a.k_max, f1), flush=True)
        print("dev paso %d: macro-F1 medio %.4f (mejor %.4f)" % (paso, f1, mejor["f1"]), flush=True)
        if f1 > mejor["f1"]:
            mejor.update(f1=f1, paso=paso)
            guardar(sal / "mejor.pt", {"modelo": modelo.state_dict(), "cabezas": sorted(modelo.coral.keys()), "paso": paso, "f1": f1,
                                       "enc": enc.estado_enc(), "max_tok": enc.max_tok})
        modelo.train()

    eval_cada = a.eval_cada or max(total // 4, 1)
    modelo.train()
    t_ent, t_ck, p0, acc = time.time(), time.time(), paso, {}
    print("entrenando: %d filas, %d pasos (%.2f épocas), dispositivo %s" % (mues.n, total, total / mues.pasos_por_epoca(), a.device), flush=True)
    while paso < total and not parar:
        for g, b in zip(opt.param_groups, bases):
            g["lr"] = lr_en(paso, total, b)
        if a.episodios:
            ep = mues.paso(paso)
            lote_p, protos = ep["filas"], (None if ep["soporte"] is None else {ep["tarea"]: prototipos(modelo, enc, ep["soporte"])})
        else:
            lote_p, protos = mues.lote_paso(paso), None
        _, ps = modelo(D.renombrar_lote(lote_p, a.renombrar, a.semilla, paso), enc, protos=protos)
        opt.zero_grad(set_to_none=True)
        ps["total"].backward()
        torch.nn.utils.clip_grad_norm_([*modelo.parameters(), *enc.parametros_entrenables()], 1.0)
        opt.step()
        if a.descongelar:
            enc.invalidar()
        paso += 1
        for k, v in ps.items():
            acc[k] = acc.get(k, 0.0) + float(v.detach())
        if paso % 10 == 0 or paso == 1:
            n = 1 if paso == 1 else 10
            print("paso %d/%d " % (paso, total) + " ".join("%s=%.4f" % (k, v / n) for k, v in acc.items())
                  + " lr=%.2e %.2f s/paso cache=%d/%d" % (opt.param_groups[0]["lr"], (time.time() - t_ent) / (paso - p0),
                                                          enc.aciertos, enc.aciertos + enc.fallos), flush=True)
            acc = {}
        if not calibrado and paso - p0 == 30:
            por_paso = (time.time() - t_ent) / 30
            nuevo = paso + int(max(a.minutos * 60 - (time.time() - t_ini), 0) / por_paso * 0.95)
            if nuevo < total:
                print("calibrado: %.2f s/paso, el total pasa de %d a %d pasos" % (por_paso, total, nuevo), flush=True)
                total = nuevo
                eval_cada = a.eval_cada or max(total // 4, 1)
            calibrado = True
        if paso % eval_cada == 0 and paso < total:
            evaluar_dev()
        if time.time() - t_ck >= a.ckpt_cada:
            checkpoint()
            t_ck = time.time()
            print("checkpoint en el paso %d" % paso, flush=True)
    evaluar_dev()
    if not (sal / "mejor.pt").exists():
        guardar(sal / "mejor.pt", {"modelo": modelo.state_dict(), "cabezas": sorted(modelo.coral.keys()), "paso": paso, "f1": None,
                                   "enc": enc.estado_enc(), "max_tok": enc.max_tok})
    checkpoint()
    kappa_dev = elegir_kappa(modelo, enc, dev, filas, a) if a.elegir_kappa and a.episodios and not parar else None
    with open(sal / "entrenamiento.json", "w") as f:
        json.dump({"pasos": paso, "total": total, "mejor": mejor, "filas": mues.n, "info": info, "kappa_dev": kappa_dev,
                   "segundos": time.time() - t_ini, "interrumpido": bool(parar)}, f, indent=1, ensure_ascii=False)
    print("fin: paso %d de %d, mejor dev %.4f en el paso %d" % (paso, total, mejor["f1"], mejor["paso"]), flush=True)
    return 143 if parar else 0


if __name__ == "__main__":
    sys.exit(main())
