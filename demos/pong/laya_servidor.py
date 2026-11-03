"""Servidor HTTP mínimo para Laya (`pip install laya`, `convaiinnovations/laya`) con la interfaz que espera `pong.partida.AgenteLaya`.

    python laya_servidor.py [--puerto 8095] [--modelo multilingual] [--hilos 4]

POST /decide  {"state": str, "instructions": str, "criteria": {id: descripción}}
           →  {"choice": id, "probs": {id: p}, "ms": ms de cálculo}
GET  /healthz → {"status": "ok", "modelo": …}
Es la misma llamada que `model/evaluacion/laya.py` (Router.predict con una pregunta `choice`; Laya pone un `[MASK]` por opción
y hace softmax). Solo biblioteca estándar más el paquete `laya`."""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROUTER, MODELO = None, "multilingual"


def _probs(resp, ids, descs):
    for k in ("probs", "distribution", "probabilities"):
        d = resp.get(k)
        if isinstance(d, dict):
            out = {}
            for c, p in d.items():
                i = c if c in ids else (ids[descs.index(c)] if c in descs else None)
                if i is not None and isinstance(p, (int, float)):
                    out[i] = float(p)
            if out:
                return out
        if isinstance(d, (list, tuple)) and len(d) == len(ids):
            return {i: float(p) for i, p in zip(ids, d)}
    return {}


def decidir(cuerpo: dict) -> dict:
    crit = cuerpo["criteria"]
    ids, descs = list(crit), list(crit.values())
    t0 = time.perf_counter()
    r = ROUTER.predict(cuerpo["state"], {"q": {"type": "choice", "instructions": cuerpo["instructions"], "criteria": crit}},
                       model=MODELO)
    ms = (time.perf_counter() - t0) * 1000
    a = r["answers"]["q"]
    probs = _probs(a, ids, descs)
    c = a.get("choice")
    c = c if c in ids else (ids[descs.index(c)] if c in descs else (max(probs, key=probs.get) if probs else None))
    return {"choice": c, "probs": probs, "ms": round(ms, 2)}


class Manejador(BaseHTTPRequestHandler):
    def _json(self, codigo, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self._json(200, {"status": "ok", "modelo": MODELO}) if self.path == "/healthz" else self._json(404, {})

    def do_POST(self):
        if self.path != "/decide":
            return self._json(404, {})
        try:
            cuerpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self._json(200, decidir(cuerpo))
        except Exception as e:  # noqa: BLE001 — se devuelve al cliente
            self._json(500, {"error": str(e)[:300]})

    def log_message(self, *a):
        pass


def main():
    global ROUTER, MODELO
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--puerto", type=int, default=8095)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--modelo", default="multilingual")
    ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--ruta", help="checkpoint local (p. ej. el ajustado con `laya.train_cli --out`); se sirve como modelo «ajustado»")
    a = ap.parse_args()
    import torch
    torch.set_num_threads(a.hilos)
    from laya import Router
    if a.ruta:
        ROUTER, MODELO = Router(models={"ajustado": a.ruta}), "ajustado"
    else:
        ROUTER, MODELO = Router(), a.modelo
    decidir({"state": "calentamiento", "instructions": "¿Qué hago?", "criteria": {"1": "subir", "2": "bajar", "3": "quieta"}})
    print(f"laya_servidor: {MODELO} listo en http://{a.host}:{a.puerto}", flush=True)
    ThreadingHTTPServer((a.host, a.puerto), Manejador).serve_forever()


if __name__ == "__main__":
    main()
