"""Sondeo: manda N mensajes reales a /v1/decide y cuenta qué capa responde. Uso: capas.py URL MENSAJES [N]"""
import collections
import json
import sys
import urllib.request

url, msgs = sys.argv[1], sys.argv[2]
n = int(sys.argv[3]) if len(sys.argv) > 3 else 200
cuenta = collections.Counter()
ms = []
for t in [l.strip() for l in open(msgs, encoding="utf-8") if l.strip()][:n]:
    q = {"id": "q0", "question": "¿Qué quiere hacer el cliente?", "kind": "choice",
         "options": [{"id": o} for o in ("compra", "queja", "saludo", "soporte")]}
    r = urllib.request.Request(url, json.dumps({"state": t, "questions": [q]}).encode(), {"Content-Type": "application/json"})
    res = json.load(urllib.request.urlopen(r))["results"][0]
    cuenta[res["layer"]] += 1
    ms.append(res["ms"])
print(json.dumps({"capas": dict(cuenta), "ms_medio_cascada": round(sum(ms) / len(ms), 3)}))
