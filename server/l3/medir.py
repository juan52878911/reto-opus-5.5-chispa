#!/usr/bin/env python3
"""Mide L3 a través de un chispa-server ya en marcha (lo arranca medir.sh). Solo stdlib.

Manda cada caso como una pregunta a /v1/decide y resume: latencia por pregunta (p50/p95), tasa de respuestas válidas de L3 y
exactitud. «Válida» = L3 contestó con probabilidades que pasaron la validación (contador chispa_l3_llamadas_total{resultado="ok"}
de /metrics, antes y después); el resto son invalida/error/timeout/presupuesto. Una pregunta cuenta como acertada solo si
layer == "L3" y answer == oro; si L3 no opinó queda como escalada (no acierto)."""
import argparse, json, random, re, sys, time, urllib.request
from pathlib import Path


def jev_a_fila(c):
    q, labels, crit, oro = c["question"], [str(x) for x in c["labels"]], c["question"].get("criteria"), c["expected"]
    t = q.get("type")
    if t == "choice":
        crit = crit or {}
        ops, desc, etq = labels, {o: crit.get(o, "") for o in labels}, str(oro)
    elif t == "noul":
        crit = crit or {}
        ops, desc, etq = ["false", "true"], {"false": crit.get("false", ""), "true": crit.get("true", "")}, {"no": "false", "yes": "true"}[str(oro)]
    elif t == "score":
        niv = list(crit or [])
        ops = [str(i + 1) for i in range(len(labels))]
        desc, etq = {str(i + 1): (niv[i] if i < len(niv) else "") for i in range(len(labels))}, str(int(oro) + 1)
    else:
        raise ValueError(f"tipo {t!r}")
    st = c["state"]
    return {"id": "jev:" + c["id"], "tipo": t, "pregunta": q.get("instructions", ""),
            "texto": st if isinstance(st, str) else json.dumps(st, ensure_ascii=False),
            "opciones": ops, "descripciones": desc, "etiqueta": etq}


def cargar_jev(ruta, n, semilla):
    p = Path(ruta)
    d = p / "datasets" / "public" if (p / "datasets" / "public").is_dir() else p
    fs = [d] if d.is_file() else [d / f"{s}.jsonl" for s in ("easy", "hard", "original") if (d / f"{s}.jsonl").is_file()]
    if not fs:
        sys.exit(f"medir.py: no hay datasets/public/{{easy,hard,original}}.jsonl en {ruta}")
    filas = []
    for f in fs:
        for ln in f.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    filas.append(jev_a_fila(json.loads(ln)))
                except (ValueError, KeyError) as e:
                    print(f"aviso: caso saltado en {f.name}: {e}", file=sys.stderr)
    random.Random(semilla).shuffle(filas)
    return filas[:n]


def cargar_jsonl(ruta, n):
    filas = [json.loads(l) for l in Path(ruta).read_text(encoding="utf-8").splitlines() if l.strip()]
    return filas[:n]


def post(url, cuerpo, clave=""):
    h = {"Content-Type": "application/json"}
    if clave:
        h["Authorization"] = "Bearer " + clave
    r = urllib.request.Request(url, json.dumps(cuerpo).encode(), h)
    try:
        with urllib.request.urlopen(r, timeout=300) as x:
            return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")[:200]}


def l3_cuentas(base):
    with urllib.request.urlopen(base + "/metrics", timeout=10) as x:
        txt = x.read().decode()
    return {m.group(1): float(m.group(2)) for m in re.finditer(r'^chispa_l3_llamadas_total\{resultado="(\w+)"\} ([\d.e+]+)$', txt, re.M)}


def pct(xs, p):
    if not xs:
        return float("nan")
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    i = int(k)
    return xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * (k - i)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="URL del chispa-server, p. ej. http://127.0.0.1:8090")
    ap.add_argument("--respaldo", required=True)
    ap.add_argument("--jevbench", default="", help="clon de JevBench, su datasets/public o un .jsonl")
    ap.add_argument("-n", type=int, default=50)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--clave", default="", help="api key de chispa-server si la usa")
    ap.add_argument("--salida", default="", help="JSONL con una línea por caso")
    a = ap.parse_args()

    if a.jevbench:
        filas, fuente = cargar_jev(a.jevbench, a.n, a.semilla), "JevBench"
    else:
        filas, fuente = cargar_jsonl(a.respaldo, a.n), "respaldo"
    if not filas:
        sys.exit("medir.py: sin casos")
    antes = l3_cuentas(a.base)
    res = []
    for f in filas:
        q = {"id": "q", "question": f["pregunta"], "kind": f["tipo"],
             "options": [{"id": o, **({"description": f["descripciones"][o]} if f.get("descripciones", {}).get(o) else {})} for o in f["opciones"]]}
        t = time.perf_counter()
        st, r = post(a.base + "/v1/decide", {"state": f["texto"], "questions": [q]}, a.clave)
        wall = (time.perf_counter() - t) * 1000
        x = (r.get("results") or [{}])[0] if st == 200 else {}
        res.append({"id": f["id"], "tipo": f["tipo"], "http": st, "layer": x.get("layer"), "answer": x.get("answer"),
                    "oro": f["etiqueta"], "ms": x.get("ms"), "wall_ms": round(wall, 1), "error": None if st == 200 else r})
    d = {k: v - antes.get(k, 0) for k, v in l3_cuentas(a.base).items()}
    if a.salida:
        Path(a.salida).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in res), encoding="utf-8")

    n = len(res)
    por_l3 = [r for r in res if r["layer"] == "L3"]
    acierta = [r for r in por_l3 if r["answer"] == r["oro"]]
    llam = sum(d.values())
    print(f"casos: {n} ({fuente})   errores HTTP: {sum(r['http'] != 200 for r in res)}")
    print(f"llamadas a L3: {int(llam)}   " + "  ".join(f"{k}={int(v)}" for k, v in sorted(d.items())))
    print(f"respuestas válidas (L3 ok / llamadas): {d.get('ok', 0) / llam:.1%}" if llam else "respuestas válidas: sin llamadas a L3 (¿se resolvió todo antes de L3?)")
    antes_l3 = [r for r in res if r["layer"] not in ("L3", "escalar")]
    print(f"preguntas contestadas por L3: {len(por_l3)}/{n}   escaladas (L3 no opinó): {sum(r['layer'] == 'escalar' for r in res)}   resueltas antes de L3: {len(antes_l3)}"
          + (f" ({', '.join(sorted({str(r['layer']) for r in antes_l3}))}; no miden L3)" if antes_l3 else ""))
    print(f"exactitud sobre contestadas: {len(acierta) / len(por_l3):.1%}" if por_l3 else "exactitud sobre contestadas: n/a")
    print(f"exactitud sobre todas (no contestadas = fallo): {len(acierta) / n:.1%}")
    ms = [r["ms"] for r in res if r["ms"] is not None]
    wl = [r["wall_ms"] for r in res]
    print(f"latencia por pregunta, campo ms del servidor: p50={pct(ms, 50):.0f} ms  p95={pct(ms, 95):.0f} ms")
    print(f"latencia por pregunta, reloj del cliente:     p50={pct(wl, 50):.0f} ms  p95={pct(wl, 95):.0f} ms")
    for tipo in sorted({r["tipo"] for r in res}):
        g = [r for r in res if r["tipo"] == tipo]
        print(f"  {tipo}: {len(g)} casos, contestadas L3 {sum(r['layer'] == 'L3' for r in g)}, aciertos {sum(r['layer'] == 'L3' and r['answer'] == r['oro'] for r in g)}")


main()
