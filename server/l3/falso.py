#!/usr/bin/env python3
"""Servidor falso OpenAI-compatible (POST /v1/chat/completions) para probar medir.sh sin un LLM real. Solo stdlib.

Elige la opción con más palabras en común con el texto (sobre id y descripción); no es un clasificador serio, solo da
respuestas con la forma que L3 espera. Variables: FALSO_LATENCIA (s, por defecto 0.05), FALSO_INVALIDAS (fracción 0-1 de
respuestas que no son JSON válido, por defecto 0.1), FALSO_PUERTO_ARCHIVO (donde escribir el puerto elegido), FALSO_CLAVE
(si está, exige Authorization: Bearer <clave> y responde 401 si no)."""
import hashlib, json, os, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LAT = float(os.environ.get("FALSO_LATENCIA", "0.05"))
INV = float(os.environ.get("FALSO_INVALIDAS", "0.1"))
CLAVE = os.environ.get("FALSO_CLAVE", "")
palabras = lambda s: set(re.findall(r"\w{3,}", str(s).lower()))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        cuerpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        if not self.path.endswith("/chat/completions"):
            return self.responder(404, {"error": "ruta"})
        if CLAVE and self.headers.get("Authorization") != "Bearer " + CLAVE:
            return self.responder(401, {"error": "clave"})
        e = json.loads(cuerpo["messages"][-1]["content"])
        time.sleep(LAT)
        h = int(hashlib.sha1(cuerpo["messages"][-1]["content"].encode()).hexdigest(), 16)
        if (h % 1000) / 1000 < INV:
            contenido = "no sé responder en JSON"
        else:
            t = palabras(e["texto"])
            ops = e["opciones"]
            pts = [1 + len(t & palabras(o["id"] + " " + o.get("descripcion", ""))) for o in ops]
            mejor = max(range(len(ops)), key=lambda i: pts[i])
            probs = {o["id"]: (0.8 if i == mejor else 0.2 / max(1, len(ops) - 1)) for i, o in enumerate(ops)}
            contenido = json.dumps({"probs": probs})
        self.responder(200, {"choices": [{"message": {"role": "assistant", "content": contenido}}]})

    def responder(self, st, o):
        b = json.dumps(o).encode()
        self.send_response(st)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


s = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 0), H)
if os.environ.get("FALSO_PUERTO_ARCHIVO"):
    open(os.environ["FALSO_PUERTO_ARCHIVO"], "w").write(str(s.server_address[1]))
s.serve_forever()
