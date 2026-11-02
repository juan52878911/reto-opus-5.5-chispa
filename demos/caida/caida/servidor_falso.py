"""Servidor HTTP falso con la forma de `/v1/decide` (http.server, sin modelos). Para tests y pruebas de humo.

Modos: «primera» (choice → "1", score → 2, noul → true), «escalar» (todo escala, sin opinión),
«aleatorio» (choice al azar), «escalar_probs» (todo escala pero con `probs`: el choice favorece la opción 1),
«escalar_probs_ciego» (como el anterior, pero el choice favorece una opción al azar). `python -m caida.servidor_falso --modo primera --puerto 8099`.
"""
from __future__ import annotations

import argparse
import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


MODOS = ("primera", "escalar", "aleatorio", "escalar_probs", "escalar_probs_ciego")


def responder(q: dict, modo: str, rng: random.Random) -> dict:
    base = {"id": q["id"], "kind": q["kind"], "ms": 1.0}
    if modo == "escalar":
        return {**base, "answer": "", "probs": {}, "layer": "escalar", "escalate": True, "escalate_reason": "sin_opinion"}
    esc = modo.startswith("escalar_probs")
    ext = {"escalate": True, "escalate_reason": "bajo_tau"} if esc else {"escalate": False}
    resp = (lambda a: "") if esc else (lambda a: a)
    capa = (lambda c: "escalar") if esc else (lambda c: c)
    if q["kind"] == "choice":
        ids = [o["id"] for o in q["options"]]
        r = rng.choice(ids) if modo in ("aleatorio", "escalar_probs_ciego") else ids[0]
        resto = (1.0 - 0.7) / max(1, len(ids) - 1)
        probs = {i: (0.7 if i == r else resto) for i in ids}
        return {**base, "answer": resp(r), "probs": probs, "layer": capa("L1"), **ext}
    if q["kind"] == "score":
        ids = sorted(o["id"] for o in q["options"])
        probs = {i: (0.5 if i == "2" else 0.5 / (len(ids) - 1)) for i in ids}
        return {**base, "answer": resp("2"), "probs": probs, "layer": capa("L0"), **ext}
    return {**base, "answer": resp("true"), "probs": {"false": 0.2, "true": 0.8}, "layer": capa("L0"), **ext}


class ServidorFalso:
    def __init__(self, modo: str = "primera", puerto: int = 0, retardo_ms: float = 0.0, semilla: int = 1):
        self.modo, self.retardo, self.peticiones = modo, retardo_ms, []
        rng = random.Random(semilla)
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # silencioso
                pass

            def do_GET(self):
                if self.path == "/healthz":
                    self._json(200, {"ok": True, "falso": True})
                else:
                    self._json(404, {"error": {"code": "not_found", "message": self.path}})

            def do_POST(self):
                if self.path != "/v1/decide":
                    return self._json(404, {"error": {"code": "not_found", "message": self.path}})
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    cuerpo = json.loads(self.rfile.read(n))
                except ValueError:
                    return self._json(400, {"error": {"code": "invalid_json", "message": "json ilegible"}})
                outer.peticiones.append(cuerpo)
                if outer.retardo:
                    time.sleep(outer.retardo / 1000.0)
                self._json(200, {"results": [responder(q, outer.modo, rng) for q in cuerpo.get("questions", [])]})

            def _json(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", puerto), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self._hilo = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self._hilo.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--modo", choices=MODOS, default="primera")
    ap.add_argument("--puerto", type=int, default=8099)
    ap.add_argument("--retardo-ms", type=float, default=0.0)
    a = ap.parse_args(argv)
    with ServidorFalso(a.modo, a.puerto, a.retardo_ms) as s:
        print(f"servidor falso ({a.modo}) en {s.url}", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
