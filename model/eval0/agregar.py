"""Lee out/*.json y escribe resultados_tablas.md (las tablas de resultados.md). Uso: python agregar.py"""
import glob, json, os
import numpy as np
D = os.path.dirname(os.path.abspath(__file__))
R = [json.load(open(f)) | {"_f": os.path.basename(f)} for f in sorted(glob.glob(D + "/out/*.json"))]
TAREAS = ["intencion", "toxicidad", "whatsapp_comercio", "herramientas"]
MODELOS = ["e5_knn8", "e5_knn32", "gliclass", "julia1", "thx01", "laya"]
def sel(m, t, h, n):
    for r in R:
        if r["modelo"] == m and r["tarea"] == t and r["hilos"] == h and ("__n%d" % n in r["_f"] if n else "__n" not in r["_f"]):
            return r
def fila(r):
    if r is None: return "—|—|—|—|—"
    if r["estado"] != "medido": return "no medido|||| " + r.get("error", "")[:80]
    return f'{100*r["macro_f1"]:.1f}|{r["ece"]:.3f}|{r["p50_ms"]:.0f}|{r["p99_ms"]:.0f}|{r["rss_pico_mb"]:.0f}'
out = []
def tabla(titulo, h, n):
    out.append(f"\n### {titulo}\n\n| modelo | tarea | n | macro-F1 | ECE | p50 ms | p99 ms | RSS pico MB |\n|---|---|---|---|---|---|---|---|")
    for m in MODELOS:
        for t in TAREAS:
            r = sel(m, t, h, n)
            if r: out.append(f'| {m} | {t} | {r.get("n","")} | ' + fila(r).replace("|", " | ") + " |")
tabla("A. 1 hilo, subconjunto fijo de 120 ejemplos por tarea (base de la comparación D2)", 1, 120)
tabla("B. 1 hilo, test completo (solo e5; referencia del tamaño de muestra)", 1, 0)
tabla("C. 4 hilos, 30 ejemplos por tarea (p99 sobre 30 = prácticamente el máximo; la macro-F1 no es comparable)", 4, 30)
tabla("C'. 4 hilos, 60 ejemplos por tarea (solo e5, primera pasada)", 4, 60)
# D2
out.append("\n### D. Regla de D2 (≥ 5 puntos de macro-F1 de media sobre e5 kNN-32 y p99 ≤ 50 ms), tabla A\n")
out.append("| modelo | macro-F1 media (4 tareas) | Δ vs e5_knn32 | p99 máx entre tareas (ms) | cumple |\n|---|---|---|---|---|")
def media(m):
    rs = [sel(m, t, 1, 120) for t in TAREAS]
    if any(r is None or r["estado"] != "medido" for r in rs): return None, None
    return float(np.mean([r["macro_f1"] for r in rs])) * 100, max(r["p99_ms"] for r in rs)
base, _ = media("e5_knn32")
for m in MODELOS:
    f1, p99 = media(m)
    if f1 is None: out.append(f"| {m} | no medido en alguna tarea | | | no |"); continue
    d = f1 - base if base is not None else float("nan")
    ok = d >= 5 and p99 <= 50
    out.append(f"| {m} | {f1:.1f} | {d:+.1f} | {p99:.0f} | {'sí' if ok else 'no'} |")
open(D + "/resultados_tablas.md", "w").write("\n".join(out) + "\n")
print("\n".join(out))
