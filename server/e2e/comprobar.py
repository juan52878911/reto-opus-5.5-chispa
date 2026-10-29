#!/usr/bin/env python3
"""Comprobaciones HTTP de la prueba e2e (solo biblioteca estándar). Sale con 1 si algo no cumple.

  comprobar.py decidir URL PETICION.json [--capa L2] [--sin-escalar] [--esperar-http 200] [--guardar salida.json]
  comprobar.py metrica URL NOMBRE [ETIQUETA] --min N | --igual N
  comprobar.py recarga URL PETICION.json --pid PID --hups N --hilos H [--segundos S]
"""
import argparse
import json
import os
import re
import signal
import sys
import threading
import time
import urllib.error
import urllib.request


def post(url, cuerpo, timeout=20):
    req = urllib.request.Request(url + "/v1/decide", data=cuerpo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def metricas(url):
    with urllib.request.urlopen(url + "/metrics", timeout=10) as r:
        txt = r.read().decode()
    out = {}
    for ln in txt.splitlines():
        if ln and not ln.startswith("#"):
            k, _, v = ln.rpartition(" ")
            out[k] = float(v)
    return out


def forma_multi(qid, ids, r, p):
    """multi: `answers` = opciones activas en el orden de la pregunta; `answer` = la activa de mayor p ("" si ninguna); una p en [0,1] por opción
    (no suman 1). Escalado sin respuesta: probs vacías."""
    errs = []
    ans = r.get("answers")
    if not isinstance(ans, list) or [a for a in ans if a not in ids] or ans != [i for i in ids if i in ans]:
        return [f"{qid}: answers {ans!r} no son opciones activas en el orden {ids}"]
    if r.get("escalate") and not p:
        return [f"{qid}: escaló sin respuesta con answers {ans!r} (esperaba []/\"\")"] if ans or r.get("answer") else []
    if sorted(p) != sorted(ids):
        return [f"{qid}: probs {sorted(p)} ≠ opciones {sorted(ids)}"]
    if any(not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in p.values()):
        errs.append(f"{qid}: probs fuera de [0,1]: {p}")
    esperada = max(ans, key=lambda a: p[a]) if ans else ""
    if r.get("answer") != esperada:
        errs.append(f"{qid}: answer {r.get('answer')!r} ≠ la activa de mayor p {esperada!r}")
    return errs


def forma(resp, peticion):
    """Errores de forma de una respuesta de /v1/decide frente a su petición."""
    errs = []
    res = resp.get("results")
    pregs = peticion["questions"]
    if not isinstance(res, list) or len(res) != len(pregs):
        return [f"results: {res!r} no tiene {len(pregs)} elementos"]
    for r, q in zip(res, pregs):
        ids = [o["id"] for o in q["options"]]
        if r.get("id") != q["id"] or r.get("kind") != q["kind"]:
            errs.append(f"{q['id']}: id/kind {r.get('id')}/{r.get('kind')}")
        if not isinstance(r.get("escalate"), bool) or not isinstance(r.get("layer"), str) or not isinstance(r.get("ms"), (int, float)):
            errs.append(f"{q['id']}: escalate/layer/ms mal tipados: {r}")
        p = r.get("probs") or {}
        if q["kind"] == "multi":
            errs += forma_multi(q["id"], ids, r, p)
            continue
        if r.get("answer") not in ids:
            errs.append(f"{q['id']}: answer {r.get('answer')!r} no es una opción {ids}")
        if sorted(p) != sorted(ids):
            errs.append(f"{q['id']}: probs {sorted(p)} ≠ opciones {sorted(ids)}")
        elif abs(sum(p.values()) - 1) > 1e-3:
            errs.append(f"{q['id']}: probs suman {sum(p.values()):.4f}")
    return errs


def cmd_decidir(a):
    pet = json.load(open(a.peticion))
    st, cuerpo = post(a.url, json.dumps(pet).encode())
    if st != a.esperar_http:
        print(f"FALLO HTTP {st} (esperaba {a.esperar_http}): {cuerpo[:300]!r}")
        return 1
    if a.esperar_http != 200:
        print(f"HTTP {st} ok")
        return 0
    resp = json.loads(cuerpo)
    errs = forma(resp, pet)
    capas = [r["layer"] for r in resp["results"]]
    if a.capa and a.capa not in capas:
        errs.append(f"ninguna decisión de {a.capa}: capas {capas}")
    if a.sin_escalar and any(r["escalate"] for r in resp["results"]):
        errs.append(f"hay escalados: {capas}")
    if a.guardar:
        json.dump(resp, open(a.guardar, "w"))
    for e in errs:
        print("FALLO " + e)
    if a.multi_con_probs:
        for r in resp["results"]:
            if r["kind"] == "multi" and (r["escalate"] or len(r["probs"]) < 2):
                errs.append(f"{r['id']}: multi sin probs por opción (escalate={r['escalate']})")
                print("FALLO " + errs[-1])
    print(f"HTTP 200, capas {capas}, answers {[r.get('answers', r['answer']) for r in resp['results']]}")
    return 1 if errs else 0


def cmd_metrica(a):
    m = metricas(a.url)
    clave = a.nombre + (a.etiqueta or "")
    if clave not in m:
        print(f"FALLO métrica {clave} ausente")
        return 1
    v = m[clave]
    ok = (v >= a.min) if a.min is not None else (v == a.igual)
    print(f"{'ok' if ok else 'FALLO'} {clave} = {v:g} ({'≥ ' + str(a.min) if a.min is not None else '= ' + str(a.igual)})")
    return 0 if ok else 1


def cmd_recarga(a):
    pet = json.load(open(a.peticion))
    parado = threading.Event()
    malos, total, lock = [], [0], threading.Lock()
    n = [0]

    def hilo(i):
        while not parado.is_set():
            with lock:
                n[0] += 1
                k = n[0]
            p = json.loads(json.dumps(pet))
            p["state"] = f"{pet['state']} #{k}"  # estado distinto: no acierta la caché de respuestas
            try:
                st, cuerpo = post(a.url, json.dumps(p).encode(), timeout=30)
                ok = st == 200 and not forma(json.loads(cuerpo), p)
                err = None if ok else f"HTTP {st} {cuerpo[:160]!r}"
            except Exception as e:  # corte de conexión, timeout…
                err = repr(e)
            with lock:
                total[0] += 1
                if err:
                    malos.append(err)

    hs = [threading.Thread(target=hilo, args=(i,)) for i in range(a.hilos)]
    antes = metricas(a.url).get('chispa_recargas_total{resultado="ok"}', 0)
    for h in hs:
        h.start()
    t0 = time.time()
    for i in range(a.hups):
        time.sleep(a.segundos)
        os.kill(a.pid, signal.SIGHUP)
        # una recarga a la vez: los SIGHUP seguidos se pueden fundir en uno
        fin = time.time() + 30
        while time.time() < fin and metricas(a.url).get('chispa_recargas_total{resultado="ok"}', 0) < antes + i + 1:
            time.sleep(0.1)
    time.sleep(a.segundos)
    parado.set()
    for h in hs:
        h.join()
    despues = metricas(a.url).get('chispa_recargas_total{resultado="ok"}', 0)
    print(f"{total[0]} peticiones en {time.time() - t0:.1f} s con {a.hups} recargas; recargas ok {antes:g} → {despues:g}; fallidas {len(malos)}")
    for m in malos[:5]:
        print("FALLO petición en curso: " + m)
    if despues - antes != a.hups:
        print(f"FALLO: esperaba {a.hups} recargas contadas")
        return 1
    return 1 if malos or total[0] < a.hups * 5 else 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("decidir"); d.add_argument("url"); d.add_argument("peticion"); d.add_argument("--capa")
    d.add_argument("--sin-escalar", action="store_true"); d.add_argument("--esperar-http", type=int, default=200); d.add_argument("--guardar")
    d.add_argument("--multi-con-probs", action="store_true", help="cada multi debe traer una p por opción (no escalar sin respuesta)")
    m = sub.add_parser("metrica"); m.add_argument("url"); m.add_argument("nombre"); m.add_argument("etiqueta", nargs="?")
    m.add_argument("--min", type=float); m.add_argument("--igual", type=float)
    r = sub.add_parser("recarga"); r.add_argument("url"); r.add_argument("peticion"); r.add_argument("--pid", type=int, required=True)
    r.add_argument("--hups", type=int, default=3); r.add_argument("--hilos", type=int, default=8); r.add_argument("--segundos", type=float, default=1.5)
    a = ap.parse_args()
    sys.exit({"decidir": cmd_decidir, "metrica": cmd_metrica, "recarga": cmd_recarga}[a.cmd](a))


main()
