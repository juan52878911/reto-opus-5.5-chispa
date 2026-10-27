"""Acuerdo entre dos anotadores: κ de Cohen por tarea y global, confusión, discrepancias y adjudicación.

Uso: python -m model.etiquetado.acuerdo --a ana.jsonl --b luis.jsonl [--oro muestra.jsonl] [--salida adjudicado.jsonl]
`--oro` es el JSONL de filas (con `tarea` y `etiqueta` original); sin él no hay tareas ni acuerdo con el original.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict


def leer(ruta):
    out = {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                r = json.loads(linea)
                out[r["id"]] = r
    return out


def kappa(pares):
    """κ de Cohen de una lista de (a, b). Sin pares: None. Si el azar ya lo explica todo (pe=1): 1.0 si coinciden, si no 0.0."""
    n = len(pares)
    if n == 0:
        return None
    po = sum(1 for x, y in pares if x == y) / n
    ca = Counter(x for x, _ in pares)
    cb = Counter(y for _, y in pares)
    pe = sum(ca[c] * cb[c] for c in ca) / (n * n)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return (po - pe) / (1 - pe)


def confusion(pares):
    m = defaultdict(Counter)
    for x, y in pares:
        m[x][y] += 1
    return m


def adjudicar(a, b, oro=None):
    """Mayoría entre a, b y (si hay) el original. Con dos votos distintos y sin desempate: conflicto."""
    if a == b:
        return a, False
    if oro in (a, b):
        return oro, False
    return None, True


def analizar(A, B, oro=None):
    oro = oro or {}
    ids = sorted(set(A) & set(B))
    por_tarea = defaultdict(list)
    for i in ids:
        tarea = oro[i]["tarea"] if i in oro else "?"
        por_tarea[tarea].append((A[i]["etiqueta"], B[i]["etiqueta"]))
    res = {"n": len(ids), "solo_a": len(set(A) - set(B)), "solo_b": len(set(B) - set(A)),
           "kappa": {t: kappa(p) for t, p in sorted(por_tarea.items())},
           "kappa_global": kappa([x for p in por_tarea.values() for x in p]),
           "confusion": {t: confusion(p) for t, p in sorted(por_tarea.items())},
           "con_original": {}, "discrepancias": [], "adjudicado": []}
    for nombre, X in (("a", A), ("b", B)):
        comunes = [i for i in ids if i in oro]
        if comunes:
            res["con_original"][nombre] = sum(X[i]["etiqueta"] == oro[i]["etiqueta"] for i in comunes) / len(comunes)
    for i in ids:
        ea, eb = A[i]["etiqueta"], B[i]["etiqueta"]
        o = oro[i]["etiqueta"] if i in oro else None
        et, conflicto = adjudicar(ea, eb, o)
        if ea != eb:
            res["discrepancias"].append({"id": i, "tarea": oro[i]["tarea"] if i in oro else "?",
                                         "a": ea, "b": eb, "original": o})
        res["adjudicado"].append({"id": i, "etiqueta": et, "conflicto": conflicto, "a": ea, "b": eb,
                                  "dudoso": bool(A[i].get("dudoso") or B[i].get("dudoso"))})
    return res


def informe(res):
    f = lambda k: "n/d" if k is None else "%.3f" % k
    L = ["Filas comunes: %d (solo en a: %d, solo en b: %d)" % (res["n"], res["solo_a"], res["solo_b"])]
    for t, k in res["kappa"].items():
        L.append("κ %s: %s" % (t, f(k)))
    L.append("κ global: %s" % f(res["kappa_global"]))
    for t, m in res["confusion"].items():
        L.append("Confusión %s (filas = a, columnas = b):" % t)
        for x in sorted(m):
            L.append("  %s -> %s" % (x, dict(sorted(m[x].items()))))
    for n, v in res["con_original"].items():
        L.append("Acuerdo de %s con la etiqueta original: %.3f" % (n, v))
    L.append("Discrepancias: %d" % len(res["discrepancias"]))
    for d in res["discrepancias"]:
        L.append("  %s [%s] a=%s b=%s original=%s" % (d["id"], d["tarea"], d["a"], d["b"], d["original"]))
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--oro")
    p.add_argument("--salida", default="adjudicado.jsonl")
    a = p.parse_args(argv)
    res = analizar(leer(a.a), leer(a.b), leer(a.oro) if a.oro else None)
    print(informe(res))
    with open(a.salida, "w", encoding="utf-8") as f:
        for r in res["adjudicado"]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
