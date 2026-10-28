"""Comprueba el contrato de chispa-server con 18 peticiones a /v1/decide más /healthz y /metrics.
Uso: python3 -I contrato.py http://127.0.0.1:8090 server/decide/testdata   (sale con 1 si algo falla)"""
import json, sys, urllib.request, urllib.error

base, td = sys.argv[1], sys.argv[2]
carga = lambda n: json.load(open(f"{td}/{n}.req.json"))
fallos = 0

def http(metodo, ruta, cuerpo=None):
    datos = cuerpo if isinstance(cuerpo, bytes) else (json.dumps(cuerpo).encode() if cuerpo is not None else None)
    r = urllib.request.Request(base + ruta, data=datos, method=metodo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as x:
            return x.status, x.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def ok(nombre, cond, detalle=""):
    global fallos
    print(("OK    " if cond else "FALLO ") + nombre + (" " + detalle if detalle and not cond else ""))
    fallos += 0 if cond else 1

def forma(req, cuerpo):
    """results en el orden de questions, mismos id, answer entre las opciones (o vacío si escala)."""
    res = json.loads(cuerpo)["results"]
    if [r["id"] for r in res] != [q["id"] for q in req["questions"]]:
        return "ids u orden distintos"
    for q, r in zip(req["questions"], res):
        ids = [o["id"] for o in q.get("options", [])] or (["false", "true"] if q["kind"] == "noul" else [])
        if r["answer"] not in ids + [""] or not r["layer"] or "escalate" not in r or "ms" not in r:
            return f"resultado raro: {r}"
        if r["answer"] and abs(sum(r["probs"].values()) - 1) > 1e-3:
            return f"probs no suman 1: {r['probs']}"
    return ""

for i in range(8):
    req = carga("choice"); req["questions"][0]["nonce"] = f"c-{i}"; req["state"] += f" {i}"
    s, b = http("POST", "/v1/decide", req)
    ok(f"choice {i}", s == 200 and not forma(req, b), f"status={s} {forma(req, b) if s == 200 else b[:120]}")
for i in range(7):
    req = carga("noul_score_escala"); req["state"] += f" {i}"
    s, b = http("POST", "/v1/decide", req)
    ok(f"noul+score {i}", s == 200 and not forma(req, b), f"status={s} {forma(req, b) if s == 200 else b[:120]}")
s, b = http("POST", "/v1/decide", carga("kind_invalido_400"))
ok("kind inválido → 400 con error", s == 400 and "error" in json.loads(b), f"status={s}")
req = carga("choice"); req["questions"][0]["nonce"] = "idem-1"
s1, b1 = http("POST", "/v1/decide", req); s2, b2 = http("POST", "/v1/decide", req)
ok("nonce idempotente (misma respuesta, ms incluido)", s1 == s2 == 200 and b1 == b2, f"{s1} {s2}")
s, b = http("GET", "/healthz")
ok("/healthz", s == 200 and json.loads(b).get("status") == "ok", f"status={s}")
s, b = http("GET", "/metrics")
t = b.decode()
ok("/metrics", s == 200 and "chispa_peticiones_total" in t and "chispa_decididas_total" in t, f"status={s}")
print("\n".join(l for l in t.splitlines() if l.startswith(("chispa_decididas_total", "chispa_escalados_total", "chispa_peticiones_total"))))
print("contrato:", "FALLO (%d)" % fallos if fallos else "20/20 OK")
sys.exit(1 if fallos else 0)
