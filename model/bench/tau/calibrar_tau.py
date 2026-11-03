"""Hito 2: un τ por conjunto elegido con validación (nunca con test) y su efecto en test. Solo biblioteca estándar.

Para cada conjunto se pregunta a `chispa-server` (`POST /v1/decide`) por las filas de calibración (split dev, o la mitad de test
por plantilla si no hay dev) y por las de test, y se guarda la probabilidad máxima de `probs` y si su argmax acierta. En
calibración se elige el τ con más cobertura cuya precisión (aciertos entre las filas con p_max ≥ τ) sea ≥ `--precision`; en
test se publica la tasa de escalada (p_max < τ) y la precisión cuando no escala.

    python calibrar_tau.py medir --url URL --conjunto clinc150=clinc150.jsonl ... --salida filas.jsonl [--max-cal 1500]
    python calibrar_tau.py elegir --filas filas.jsonl --precision 0.85 --salida tau.json"""
import argparse
import hashlib
import json
import random
import sys
import time
import urllib.error
import urllib.request


def peticion(f: dict) -> dict:
    ops = [{"id": o, "description": (f.get("descripciones") or {}).get(o, "")} for o in f["opciones"]]
    return {"state": f["texto"], "questions": [{"id": "q", "question": f["pregunta"], "kind": f["tipo"], "options": ops}]}


def decidir(url: str, cuerpo: dict, timeout: float):
    req = urllib.request.Request(url.rstrip("/") + "/v1/decide", data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
                                 method="POST", headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())["results"][0], (time.perf_counter() - t0) * 1000, ""
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        return {}, (time.perf_counter() - t0) * 1000, str(e)[:160]


def mitad(f: dict) -> str:
    """Sin dev: la mitad de test por hash de la plantilla (las dos mitades no comparten plantilla)."""
    clave = f.get("plantilla") or f.get("id") or f["texto"]
    return "cal" if int(hashlib.sha256(clave.encode("utf-8")).hexdigest(), 16) % 2 == 0 else "test"


def medir(a) -> int:
    with open(a.salida, "w", encoding="utf-8") as out:
        for c in a.conjunto:
            nombre, ruta = c.split("=", 1)
            with open(ruta, encoding="utf-8") as fh:
                filas = [json.loads(l) for l in fh if l.strip()]
            splits = {x.get("split") for x in filas}
            if "dev" in splits:
                cal = [x for x in filas if x.get("split") == "dev"]
                test = [x for x in filas if x.get("split") == "test"]
                origen = "dev"
            else:
                t = [x for x in filas if x.get("split", "test") == "test"]
                cal, test = [x for x in t if mitad(x) == "cal"], [x for x in t if mitad(x) == "test"]
                origen = "mitad de test por plantilla"
            random.Random(f"{nombre}-cal").shuffle(cal)
            for parte, fs in (("cal", cal[:a.max_cal]), ("test", test)):
                for f in fs:
                    res, ms, err = decidir(a.url, peticion(f), a.timeout)
                    probs = {k: v for k, v in (res.get("probs") or {}).items() if k in f["opciones"] and isinstance(v, (int, float))}
                    pred = max(probs, key=probs.get) if probs else None
                    out.write(json.dumps({"conjunto": nombre, "parte": parte, "origen_cal": origen, "p_max": max(probs.values()) if probs else 0.0,
                                          "acierta": pred == f["etiqueta"], "escala_servidor": bool(res.get("escalate")),
                                          "capa": res.get("layer"), "ms": round(ms, 2), "error": err}, ensure_ascii=False) + "\n")
            print(nombre, origen, "cal", min(len(cal), a.max_cal), "test", len(test), flush=True)
    return 0


def elegir_tau(cal: list, precision: float):
    """(τ, cobertura, precisión) en calibración: el τ con más cobertura y precisión ≥ objetivo; None si ninguno llega."""
    orden = sorted(cal, key=lambda x: -x["p_max"])
    mejor, aciertos = None, 0
    for i, x in enumerate(orden, 1):
        aciertos += x["acierta"]
        if i < len(orden) and orden[i]["p_max"] == x["p_max"]:
            continue  # τ en un valor de p_max: o entran todas las filas con ese valor o ninguna
        if aciertos / i >= precision:
            mejor = (x["p_max"], i / len(orden), aciertos / i)
    return mejor


def elegir(a) -> int:
    with open(a.filas, encoding="utf-8") as fh:
        filas = [json.loads(l) for l in fh if l.strip()]
    out = {"precision_objetivo": a.precision, "conjuntos": {}}
    for nombre in dict.fromkeys(x["conjunto"] for x in filas):
        cal = [x for x in filas if x["conjunto"] == nombre and x["parte"] == "cal" and not x["error"]]
        test = [x for x in filas if x["conjunto"] == nombre and x["parte"] == "test" and not x["error"]]
        e = elegir_tau(cal, a.precision)
        r = {"origen_cal": cal[0]["origen_cal"] if cal else None, "n_cal": len(cal), "n_test": len(test),
             "exactitud_argmax_test": round(sum(x["acierta"] for x in test) / len(test), 4) if test else None,
             "escalada_servidor_test_pct": round(100 * sum(x["escala_servidor"] for x in test) / len(test), 1) if test else None}
        if e is None:
            r.update({"tau": None, "escalada_test_pct": 100.0, "precision_no_escala_test": None,
                      "nota": f"ningún τ llega a precisión {a.precision} en calibración: escala todo"})
        else:
            tau = e[0]
            acept = [x for x in test if x["p_max"] >= tau]
            r.update({"tau": round(tau, 4), "cobertura_cal": round(e[1], 4), "precision_cal": round(e[2], 4),
                      "escalada_test_pct": round(100 * (1 - len(acept) / len(test)), 1) if test else None,
                      "precision_no_escala_test": round(sum(x["acierta"] for x in acept) / len(acept), 4) if acept else None})
        r["cumple"] = bool(r["escalada_test_pct"] is not None and r["escalada_test_pct"] <= 30.0 and (r["precision_no_escala_test"] or 0) >= a.precision)
        out["conjuntos"][nombre] = r
    texto = json.dumps(out, ensure_ascii=False, indent=1)
    print(texto)
    with open(a.salida, "w", encoding="utf-8") as fh:
        fh.write(texto + "\n")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="orden", required=True)
    p = sub.add_parser("medir")
    p.add_argument("--url", required=True)
    p.add_argument("--conjunto", action="append", required=True, help="nombre=ruta.jsonl (filas de model/esquema.md)")
    p.add_argument("--max-cal", type=int, default=1500)
    p.add_argument("--timeout", type=float, default=60)
    p.add_argument("--salida", required=True)
    p = sub.add_parser("elegir")
    p.add_argument("--filas", required=True)
    p.add_argument("--precision", type=float, default=0.85)
    p.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    return {"medir": medir, "elegir": elegir}[a.orden](a)


if __name__ == "__main__":
    sys.exit(main())
