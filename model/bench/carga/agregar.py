"""Agrega crudo/t*-*-*-c*.txt en tablas markdown (mediana y rango entre tandas). Uso: agregar.py CRUDO"""
import collections
import glob
import os
import re
import statistics
import sys

crudo = sys.argv[1]


def dur(s):  # 1.5ms / 350µs / 2.1s → ms
    m = re.fullmatch(r"([\d.]+)(ns|µs|us|ms|s)", s)
    return float(m[1]) * {"ns": 1e-6, "µs": 1e-3, "us": 1e-3, "ms": 1, "s": 1000}[m[2]]


datos = collections.defaultdict(list)
for f in sorted(glob.glob(os.path.join(crudo, "t*-*-c*.txt"))):
    m = re.fullmatch(r"t(\d+)-(.+)-(carga|cargamsg)-c(\d+)\.txt", os.path.basename(f))
    t = open(f).read()
    r = re.search(r"decisiones/s=(\d+) peticiones/s=\d+ p50=(\S+) p99=(\S+)", t)
    e = re.search(r"errores=(\d+)", t)
    if not r:
        continue
    datos[(m[2], m[3], int(m[4]))].append((int(r[1]), dur(r[2]), dur(r[3]), int(e[1])))

OBJ = {"l0l1": "≥ 5000 y p99 < 20 ms", "l1-forzado": "≥ 5000 y p99 < 20 ms", "l2-forzado": "≥ 300"}
for gen, tit in (("carga", "`server/cmd/carga` sin cambiar (mensaje fijo)"), ("cargamsg", "`cargamsg` (mensajes reales de MASSIVE, uno distinto por petición)")):
    print(f"\n### {tit}\n")
    print("| modo | conc | tandas | decisiones/s (mediana) | rango entre tandas | variación | p50 ms (mediana) | p99 ms (mediana / peor) | errores | objetivo |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for (modo, g, c), v in sorted(datos.items(), key=lambda kv: (kv[0][0], kv[0][2])):
        if g != gen:
            continue
        d = [x[0] for x in v]
        med = statistics.median(d)
        var = (max(d) - min(d)) / med * 100
        p99 = [x[2] for x in v]
        ok = med >= (300 if modo == "l2-forzado" else 5000) and (modo == "l2-forzado" or max(p99) < 20)
        print(f"| {modo} | {c} | {len(v)} | {med:.0f} | {min(d)}–{max(d)} | {var:.0f} % | {statistics.median(x[1] for x in v):.2f} | "
              f"{statistics.median(p99):.2f} / {max(p99):.2f} | {sum(x[3] for x in v)} | {OBJ[modo]}: {'sí' if ok else 'NO'} |")
