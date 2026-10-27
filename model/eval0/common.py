"""Arnés común de T0.4: carga el sondeo, mide un ejemplo a la vez (4 hilos, CPU) y guarda un JSON por (modelo, tarea).

Cada script de modelo define `crear(tarea, train)` -> objeto con `.predecir(fila) -> lista de probabilidades en el
orden de fila['opciones']`, y llama a `main(nombre, crear, licencia)`. Un proceso por (modelo, tarea): el RSS pico
(ru_maxrss) incluye carga + inferencia y no se contamina con otras tareas.
"""
import argparse, json, os, resource, sys, time, traceback
os.environ.setdefault("OMP_WAIT_POLICY", "passive")  # con espera activa, 4 hilos son ~10x más lentos que 1 en esta microVM
import numpy as np

SONDEO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sondeo")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
TAREAS = ["intencion", "toxicidad", "whatsapp_comercio", "herramientas"]


def cargar(tarea):
    leer = lambda f: [json.loads(l) for l in open(os.path.join(SONDEO, f), encoding="utf-8")]
    return leer(f"{tarea}.jsonl"), leer(f"train_{tarea}.jsonl")


def macro_f1(y, p, clases):
    fs = []
    for c in clases:
        tp = sum(1 for a, b in zip(y, p) if a == c and b == c)
        fp = sum(1 for a, b in zip(y, p) if a != c and b == c)
        fn = sum(1 for a, b in zip(y, p) if a == c and b != c)
        fs.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(fs))


def ece(conf, ok, bins=15):
    conf, ok = np.asarray(conf), np.asarray(ok, float)
    edges = np.linspace(0, 1, bins + 1)
    tot = 0.0
    for i in range(bins):
        m = (conf > edges[i]) & (conf <= edges[i + 1]) if i else (conf >= 0) & (conf <= edges[1])
        if m.any():
            tot += m.mean() * abs(ok[m].mean() - conf[m].mean())
    return float(tot)


def rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def main(nombre, crear, licencia, extra_args=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tarea", required=True, choices=TAREAS)
    ap.add_argument("--hilos", type=int, default=1)
    ap.add_argument("--n", type=int, default=0, help="usa un subconjunto aleatorio fijo (semilla 0) del test")
    ap.add_argument("--calentar", type=int, default=3)
    for a, kw in (extra_args or []):
        ap.add_argument(a, **kw)
    args = ap.parse_args()
    import torch
    torch.set_num_threads(args.hilos)
    os.makedirs(OUT, exist_ok=True)
    res = dict(modelo=nombre, tarea=args.tarea, licencia=licencia, hilos=args.hilos)
    try:
        test, train = cargar(args.tarea)
        if args.n:
            import random
            test = [test[i] for i in sorted(random.Random(0).sample(range(len(test)), min(args.n, len(test))))]  # subconjunto fijo y aleatorio, igual para todos los modelos
        t0 = time.perf_counter()
        m = crear(args.tarea, train, args)
        res["carga_s"] = round(time.perf_counter() - t0, 2)
        for f in test[: args.calentar]:
            m.predecir(f)
        lat, pred, conf = [], [], []
        for f in test:
            t = time.perf_counter()
            p = m.predecir(f)
            lat.append((time.perf_counter() - t) * 1000)
            p = np.asarray(p, float)
            i = int(p.argmax())
            pred.append(f["opciones"][i]); conf.append(float(p[i]))
        y = [f["etiqueta"] for f in test]
        ok = [a == b for a, b in zip(y, pred)]
        clases = test[0]["opciones"]
        res.update(n=len(test), macro_f1=macro_f1(y, pred, clases), exactitud=float(np.mean(ok)), ece=ece(conf, ok),
                   p50_ms=float(np.percentile(lat, 50)), p99_ms=float(np.percentile(lat, 99)),
                   rss_pico_mb=round(rss_mb(), 1), estado="medido")
    except Exception as e:  # modelo que no carga o no cabe: «no medido» con el error
        res.update(estado="no medido", error="".join(traceback.format_exception_only(type(e), e)).strip()[:600],
                   rss_pico_mb=round(rss_mb(), 1))
        traceback.print_exc()
    suf = f"__h{args.hilos}" + (f"__n{args.n}" if args.n else "")
    json.dump(res, open(os.path.join(OUT, f"{nombre}__{args.tarea}{suf}.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False))
