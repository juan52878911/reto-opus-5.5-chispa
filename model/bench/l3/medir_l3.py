"""Prueba real de L3 (LLM local por Ollama) como cierre de la cascada: escalar → L3. Solo biblioteca estándar.

Dos pasadas contra `chispa-server` (`POST /v1/decide`), con las mismas filas (`model/esquema.md`, split test, submuestra
determinista por conjunto):
  sin-l3  servidor sin la sección `l3`: % de escalada con el τ actual y la conjetura de L2/L1 (argmax de `probs`) en cada fila
  con-l3  servidor con `l3` en la config: solo las filas que escalaron (tope total `--max-escaladas`): qué contesta L3, si
          escala aún, su latencia y el tiempo por cada 1000 decisiones

    python medir_l3.py sin-l3 --url URL --conjunto massive=ruta.jsonl --conjunto hatecheck=ruta.jsonl --n 600 --salida A.jsonl
    python medir_l3.py con-l3 --url URL --entrada A.jsonl --max-escaladas 500 --salida B.jsonl
    python medir_l3.py informe --a A.jsonl --b B.jsonl --salida informe.json"""
import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request


def peticion(f: dict) -> dict:
    tipo = f["tipo"]
    ops = [{"id": o, "description": (f.get("descripciones") or {}).get(o, "")} for o in f["opciones"]]
    return {"state": f["texto"], "questions": [{"id": "q", "question": f["pregunta"], "kind": tipo, "options": ops}]}


def decidir(url: str, cuerpo: dict, timeout: float) -> tuple:
    req = urllib.request.Request(url.rstrip("/") + "/v1/decide", data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read())["results"][0]
        err = ""
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        res, err = {}, str(e)[:160]
    return res, (time.perf_counter() - t0) * 1000, err


def argmax(probs: dict, opciones: list):
    vals = {o: probs.get(o) for o in opciones if isinstance(probs.get(o), (int, float))}
    return max(vals, key=vals.get) if vals else None


def leer(ruta: str):
    with open(ruta, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def sin_l3(a) -> int:
    filas = []
    for c in a.conjunto:
        nombre, ruta = c.split("=", 1)
        t = [x for x in leer(ruta) if x.get("split", "test") == "test"]
        random.Random(f"{nombre}-{a.semilla}").shuffle(t)
        filas += [(nombre, x) for x in t[:a.n]]
    with open(a.salida, "w", encoding="utf-8") as out:
        for i, (nombre, f) in enumerate(filas):
            res, ms, err = decidir(a.url, peticion(f), a.timeout)
            probs = res.get("probs") or {}
            out.write(json.dumps({"i": i, "conjunto": nombre, "fila": f, "etiqueta": f["etiqueta"], "capa": res.get("layer"),
                                  "escala": bool(res.get("escalate")), "motivo": res.get("escalate_reason"),
                                  "respuesta": res.get("answer"), "argmax": argmax(probs, f["opciones"]), "ms": round(ms, 2),
                                  "error": err}, ensure_ascii=False) + "\n")
    return 0


def con_l3(a) -> int:
    esc = [x for x in leer(a.entrada) if x["escala"] and not x["error"]]
    random.Random(a.semilla).shuffle(esc)
    esc = esc[:a.max_escaladas]
    t0 = time.perf_counter()
    with open(a.salida, "w", encoding="utf-8") as out:
        for x in esc:
            res, ms, err = decidir(a.url, peticion(x["fila"]), a.timeout)
            probs = res.get("probs") or {}
            out.write(json.dumps({"i": x["i"], "conjunto": x["conjunto"], "etiqueta": x["etiqueta"], "capa": res.get("layer"),
                                  "escala": bool(res.get("escalate")), "motivo": res.get("escalate_reason"),
                                  "respuesta": res.get("answer"), "argmax": argmax(probs, x["fila"]["opciones"]),
                                  "ms": round(ms, 2), "error": err}, ensure_ascii=False) + "\n")
    print(json.dumps({"escaladas_medidas": len(esc), "segundos": round(time.perf_counter() - t0, 1)}))
    return 0


def pct(n, d):
    return round(100 * n / d, 1) if d else None


def percentil(v, q):
    v = sorted(v)
    return round(v[min(len(v) - 1, int(q / 100 * len(v)))], 1) if v else None


def informe(a) -> int:
    A, B = leer(a.a), {x["i"]: x for x in leer(a.b)}
    out = {}
    for nombre in sorted({x["conjunto"] for x in A}) + ["total"]:
        fa = [x for x in A if nombre in ("total", x["conjunto"]) and not x["error"]]
        esc = [x for x in fa if x["escala"]]
        medidas = [x for x in esc if x["i"] in B]
        b = [B[x["i"]] for x in medidas]
        l3_opina = [y for y in b if y["capa"] == "L3" and not y["escala"]]
        l3_ok = [y for y in b if not y["error"]]
        # cascada en las filas cuyas escaladas se midieron con L3: no escaladas (respuesta de su capa) + escaladas medidas
        # (respuesta de L3 si opina; si sigue escalando, el argmax de lo que haya: pista que un cliente podría usar)
        cascada = [x["respuesta"] == x["etiqueta"] for x in fa if not x["escala"]]
        cascada += [(y["respuesta"] if not y["escala"] else y["argmax"]) == y["etiqueta"] for y in b]
        n_casc = len([x for x in fa if not x["escala"]]) + len(b)
        sin_l3_total = [(x["respuesta"] if not x["escala"] else x["argmax"]) == x["etiqueta"] for x in fa if not x["escala"] or x["i"] in B]
        lat = [y["ms"] for y in l3_ok]
        out[nombre] = {
            "filas": len(fa), "escaladas": len(esc), "escalada_pct": pct(len(esc), len(fa)), "escaladas_medidas_l3": len(b),
            "no_escaladas_exactitud_pct": pct(sum(x["respuesta"] == x["etiqueta"] for x in fa if not x["escala"]), len(fa) - len(esc)),
            "l2_en_escaladas_exactitud_pct": pct(sum(x["argmax"] == x["etiqueta"] for x in medidas), len(medidas)),
            "l3_en_escaladas_exactitud_pct": pct(sum((y["respuesta"] if not y["escala"] else y["argmax"]) == y["etiqueta"] for y in b), len(b)),
            "l3_opina_pct": pct(len(l3_opina), len(b)),
            "l3_exactitud_cuando_opina_pct": pct(sum(y["respuesta"] == y["etiqueta"] for y in l3_opina), len(l3_opina)),
            "l3_errores": len(b) - len(l3_ok),
            "cascada_sin_l3_exactitud_pct": pct(sum(sin_l3_total), len(sin_l3_total)),
            "cascada_con_l3_exactitud_pct": pct(sum(cascada), n_casc),
            "l3_p50_ms": percentil(lat, 50), "l3_p99_ms": percentil(lat, 99),
            "sin_l3_p50_ms": percentil([x["ms"] for x in fa], 50),
            "segundos_por_1000_decisiones": round((sum(x["ms"] for x in fa) + sum(lat) * (len(esc) / len(b) if b else 0)) / len(fa), 1) if fa else None,
        }
    texto = json.dumps(out, ensure_ascii=False, indent=1)
    print(texto)
    with open(a.salida, "w", encoding="utf-8") as fh:
        fh.write(texto + "\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="orden", required=True)
    p = sub.add_parser("sin-l3")
    p.add_argument("--url", required=True)
    p.add_argument("--conjunto", action="append", required=True, help="nombre=ruta.jsonl (filas de model/esquema.md)")
    p.add_argument("--n", type=int, default=600, help="filas de test por conjunto (submuestra determinista)")
    p.add_argument("--semilla", type=int, default=1)
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--salida", required=True)
    p = sub.add_parser("con-l3")
    p.add_argument("--url", required=True)
    p.add_argument("--entrada", required=True)
    p.add_argument("--max-escaladas", type=int, default=500)
    p.add_argument("--semilla", type=int, default=1)
    p.add_argument("--timeout", type=float, default=120)
    p.add_argument("--salida", required=True)
    p = sub.add_parser("informe")
    p.add_argument("--a", required=True)
    p.add_argument("--b", required=True)
    p.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    return {"sin-l3": sin_l3, "con-l3": con_l3, "informe": informe}[a.orden](a)


if __name__ == "__main__":
    sys.exit(main())
