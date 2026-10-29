"""Torres al vuelo de punta a punta: `chispa train --torre` sobre un esquema mínimo inventado, `chispa-server` y esquemas de JevBench que
NO están en el .chispa, decididos por /v1/decide.

    python -m model.bench.torre.servidor --jevbench RUTA --salida DIR --ckpt mejor.pt --torre torre.onnx --servidor BIN --tok e5.chispa-tok \
        [--repo RAIZ] [--ort-lib SO] [--tau-nuevo X] [--exigir-torres] [--puerto 8091] [--n-esquemas 5] [--todos] [--minutos 15]

Escribe DIR/servidor.json: {cinco: [{id, esquema, layer, escalate, acierto}], cinco_l2: bool, todos: {...}|null, train_s, ...}.
`todos` (231 casos) lleva la exactitud del servidor y la de Python k=0 sobre los mismos ids si existe DIR/pred/l2_k0.jsonl.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from model.evaluacion import chispa_eval as CE
from model.evaluacion.jevbench import cargar_jevbench
from model.evaluacion.jevbench_cascada import decidir

ESQUEMA = {"id": "minimo-saludo", "pregunta": "¿El mensaje es un saludo o una despedida?", "tipo": "choice",
           "opciones": {"saludo": "La persona saluda al empezar.", "despedida": "La persona se despide al terminar."}}
EJEMPLOS = ([("hola, buenos días a todos", "saludo"), ("buenas tardes, ¿cómo estáis?", "saludo"), ("qué tal, encantado de verte", "saludo"),
             ("hola de nuevo", "saludo"), ("muy buenas", "saludo"), ("saludos desde aquí", "saludo"), ("hey, ¿hay alguien?", "saludo"),
             ("bienvenidos al grupo", "saludo")] +
            [("adiós, hasta mañana", "despedida"), ("nos vemos pronto", "despedida"), ("me voy, que paséis buena noche", "despedida"),
             ("hasta luego", "despedida"), ("chao, cuídate", "despedida"), ("un abrazo y hasta la próxima", "despedida"),
             ("me despido por hoy", "despedida"), ("buen viaje y hasta pronto", "despedida")])


def entrenar(a, trabajo):
    (trabajo / "ejemplos.jsonl").write_text("".join(json.dumps({"texto": t, "etiqueta": e}, ensure_ascii=False) + "\n" for t, e in EJEMPLOS))
    (trabajo / "esquema.json").write_text(json.dumps(ESQUEMA, ensure_ascii=False))
    salida = trabajo / "minimo.chispa"
    cmd = [sys.executable, "-u", "-m", "chispa", "train", "--ejemplos", str(trabajo / "ejemplos.jsonl"), "--esquema", str(trabajo / "esquema.json"),
           "--salida", str(salida), "--ckpt", a.ckpt, "--torre", a.torre, "--repo", a.repo]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=a.repo)
    (trabajo / "train.log").write_text(r.stdout + "\n" + r.stderr)
    if r.returncode or not salida.exists():
        raise RuntimeError("chispa train --torre: " + (r.stderr or r.stdout)[-800:])
    return salida


def elegir_cinco(filas, n):
    """n casos choice de n esquemas distintos, el primero de cada esquema, en orden estable."""
    vistos, sel = set(), []
    for r in filas:
        if r["tipo"] == "choice" and r["esquema"] not in vistos and r["esquema"] != ESQUEMA["id"]:
            vistos.add(r["esquema"])
            sel.append(r)
    return sel[:n]


def metricas(url):
    """/metrics (texto Prometheus) → {serie: valor}; las series con etiquetas llevan la etiqueta en la clave."""
    m = {}
    for l in urllib.request.urlopen(url + "/metrics", timeout=10).read().decode().splitlines():
        if l and not l.startswith("#"):
            k, _, v = l.rpartition(" ")
            try:
                m[k] = float(v)
            except ValueError:
                pass
    return {k: v for k, v in m.items() if k.startswith(("chispa_torres_", "chispa_decididas_total", "chispa_escalados_total", "chispa_preguntas_total", "chispa_capa_errores_total"))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for k in ("jevbench", "salida", "ckpt", "torre", "servidor", "tok"):
        ap.add_argument("--" + k, required=True)
    ap.add_argument("--repo", required=True, help="raíz del repo con chispa train (el repo unificado)")
    ap.add_argument("--puerto", type=int, default=8091)
    ap.add_argument("--n-esquemas", type=int, default=5)
    ap.add_argument("--todos", action="store_true", help="además, todos los casos de JevBench por el servidor")
    ap.add_argument("--minutos", type=float, default=15)
    ap.add_argument("--ort-lib", help="libonnxruntime.so para chispa-server (-ort-lib); vacío = CHISPA_ORT_LIB / la del binario")
    ap.add_argument("--tau-nuevo", type=float, help="tau_l2_esquema_nuevo: arranca con -config {capas por defecto, tau_l2_esquema_nuevo}")
    ap.add_argument("--exigir-torres", action="store_true", help="FALLO (código 1) si /metrics no muestra torres calculadas o L2 no decide ningún caso")
    ap.add_argument("--pred", help="predicciones de Python k=0 (por defecto SALIDA/pred/l2_k0.jsonl)")
    a = ap.parse_args(argv)
    sal = Path(a.salida)
    trabajo = sal / "servidor"
    trabajo.mkdir(parents=True, exist_ok=True)
    filas = cargar_jevbench(a.jevbench)
    out = {"esquema_minimo": ESQUEMA["id"]}
    t0 = time.time()
    modelo = entrenar(a, trabajo)
    out["train_s"] = round(time.time() - t0, 1)
    out["chispa_bytes"] = modelo.stat().st_size
    url = f"http://127.0.0.1:{a.puerto}"
    with open(trabajo / "servidor.log", "w") as log:
        cmd = [a.servidor, "-addr", f"127.0.0.1:{a.puerto}", "-modelo", str(modelo), "-tok", a.tok]
        if a.ort_lib:
            cmd += ["-ort-lib", a.ort_lib]
        if a.tau_nuevo is not None:   # con -config no valen los τ de CALIB: se repiten las capas por defecto (L1 0,8 · L2 0,7 · L3 0,6)
            cfg = trabajo / "config.json"
            cfg.write_text(json.dumps({"capas": [{"nombre": "L0", "tau": 0.8}, {"nombre": "L1", "tau": 0.8}, {"nombre": "L2", "tau": 0.7},
                                                 {"nombre": "L3", "tau": 0.6}], "tau_l2_esquema_nuevo": a.tau_nuevo}))
            cmd += ["-config", str(cfg)]
            out["tau_l2_esquema_nuevo"] = a.tau_nuevo
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(120):
                if p.poll() is not None:
                    raise RuntimeError("el servidor terminó: " + (trabajo / "servidor.log").read_text()[-600:])
                try:
                    urllib.request.urlopen(url + "/healthz", timeout=2).read()
                    break
                except OSError:
                    time.sleep(1)
            else:
                raise RuntimeError("el servidor no responde en /healthz")
            cinco = []
            for r in elegir_cinco(filas, a.n_esquemas):
                d = decidir(url, r)
                top = max((o for o in r["opciones"] if o in d["probs"]), key=lambda o: d["probs"][o], default=None)
                cinco.append({"id": r["id"], "esquema": r["esquema"], "layer": d["layer"], "escalate": d["escalate"], "ms": d["ms"],
                              "acierto": top == r["etiqueta"] and not d["escalate"], "error": d.get("error")})
                print("  ", cinco[-1], flush=True)
            out["cinco"] = cinco
            out["cinco_l2"] = len(cinco) >= a.n_esquemas and all(c["layer"] == "L2" for c in cinco)
            out["cinco_aciertos"] = sum(c["acierto"] for c in cinco)
            if a.todos:
                preds, limite = [], time.time() + a.minutos * 60
                for r in filas:
                    if time.time() > limite:
                        break
                    preds.append(decidir(url, r))
                ids = {q["id"] for q in preds}
                sub = [r for r in filas if r["id"] in ids]
                res = CE.evaluar(sub, [{x: q[x] for x in ("id", "probs", "ms")} for q in preds])["global"]
                capas = {}
                for q in preds:
                    capas[q["layer"]] = capas.get(q["layer"], 0) + 1
                todos = {"casos": len(preds), "de": len(filas), "exactitud_servidor": res["exactitud"], "capas": capas}
                py = Path(a.pred) if a.pred else sal / "pred" / "l2_k0.jsonl"
                if py.exists():
                    pp = [json.loads(l) for l in py.read_text().splitlines() if l.strip() and json.loads(l)["id"] in ids]
                    todos["exactitud_python_k0"] = CE.evaluar(sub, [{x: q[x] for x in ("id", "probs", "ms")} for q in pp])["global"]["exactitud"]
                out["todos"] = todos
                (sal / "capas_por_caso.jsonl").write_text("".join(json.dumps({"id": q["id"], "layer": q["layer"], "escalate": q["escalate"]}) + "\n" for q in preds))
            m = metricas(url)
            out["metricas"] = m
            # comprobación obligatoria: la torre se calculó de verdad y L2 decidió algo (si no, todo salió de L0/L1 o escaló por el τ)
            l2 = out.get("todos", {}).get("capas", {}).get("L2", 0) if a.todos else sum(c["layer"] == "L2" for c in cinco)
            out["torres_ok"] = m.get("chispa_torres_calculadas_total", 0) > 0 and l2 > 0
        finally:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()
    (sal / "servidor.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(out, ensure_ascii=False))
    print("torres_ok =", out.get("torres_ok"))
    if a.exigir_torres and not out.get("torres_ok"):
        print("FALLO: chispa_torres_calculadas_total = 0 o L2 no decidió ningún caso", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
