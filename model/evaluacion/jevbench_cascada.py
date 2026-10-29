"""La cascada que montaría un cliente nuevo sobre JevBench público: `chispa train` SIN --conjunta (L0 de Chispa + L2 con soporte)
servida por `chispa-server`, un modelo por pliegue.

    python -m model.evaluacion.jevbench_cascada --jevbench RUTA --salida DIR --ckpt mejor.pt --servidor BIN --tok e5.chispa-tok \
        [--k 8 32] [--repo RAIZ] [--puerto 8090] [--minutos 30] [--max-pliegues N]

Pliegue = esquema + grupo de paráfrasis (ver jevbench.pliegues): el soporte de sus casos son los demás casos del esquema (hasta k por
opción), sin ellos ni sus paráfrasis. `chispa train` exige un ejemplo de cada opción: un pliegue cuyo soporte no cubre todas las
opciones, o que no tiene soporte, NO se fuerza (ni se recorta el esquema): queda en `DIR/pred/cascada_k<k>_omitidos.json` con el motivo.
Si el soporte de un pliegue con k = 32 es el mismo que con k = 8 (los esquemas de JevBench son pequeños), se reutiliza el resultado.
Escribe `DIR/pred/cascada_k<k>.jsonl` (`{id, probs, ms, layer, escalate, pliegue}`) y `DIR/cascada_pliegues.jsonl` (tiempos, fallos).
Un pliegue que falla una vez se reintenta una; si falla otra vez se anota y se sigue (el informe lo cuenta).
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .jevbench import cargar_jevbench, cubre_opciones, pliegues
from .jevbench_l2 import escribir


def esquema_json(fila):
    return {"id": fila["esquema"], "pregunta": fila["pregunta"], "tipo": fila["tipo"],
            "opciones": {o: fila["descripciones"].get(o, "") for o in fila["opciones"]}}


def cuerpo_decide(fila):
    q = {"id": fila["id"], "question": fila["pregunta"], "kind": fila["tipo"], "nonce": fila["id"]}
    if fila["tipo"] == "choice":
        q["options"] = [{"id": o, "description": fila["descripciones"].get(o, "")} for o in fila["opciones"]]
    elif fila["tipo"] == "score":
        q["options"] = [{"id": o} for o in fila["opciones"]]  # como sdk.tipos.Score: los niveles "1"…"K"
    return {"state": fila["texto"], "questions": [q]}


def decidir(url, fila, timeout=60):
    """Pred {id, probs, ms, layer, escalate, cliente_ms} de una pregunta; ante error, escalate y `error`."""
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(url + "/v1/decide", json.dumps(cuerpo_decide(fila)).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as x:
            res = json.loads(x.read())["results"][0]
        probs = {o: float(res.get("probs", {}).get(o, 0.0)) for o in fila["opciones"]}
        s = sum(probs.values())
        if s <= 0:
            if not res.get("escalate"):
                raise ValueError("sin probabilidades y sin escalar")
            probs, s = {"escalate": 1.0}, 1.0   # ninguna capa opinó: escala sin respuesta (no es un error)
        return {"id": fila["id"], "probs": {o: p / s for o, p in probs.items()}, "ms": float(res.get("ms", 0.0)), "layer": res.get("layer", ""),
                "escalate": bool(res.get("escalate", False)), "cliente_ms": (time.perf_counter() - t0) * 1000}
    except Exception as e:  # noqa: BLE001: un error de un caso no tira el pliegue; queda anotado
        return {"id": fila["id"], "probs": {"escalate": 1.0}, "ms": 0.0, "layer": "error", "escalate": True,
                "cliente_ms": (time.perf_counter() - t0) * 1000, "error": f"{type(e).__name__}: {e}"}


def entrenar_pliegue(rs, sop, trabajo, a):
    """`chispa train` sin --conjunta; devuelve la ruta del .chispa."""
    trabajo.mkdir(parents=True, exist_ok=True)
    escribir(trabajo / "ejemplos.jsonl", [{"texto": r["texto"], "etiqueta": r["etiqueta"]} for r in sop])
    (trabajo / "esquema.json").write_text(json.dumps(esquema_json(rs[0]), ensure_ascii=False))
    salida = trabajo / "m.chispa"
    cmd = [sys.executable, "-u", "-m", "chispa", "train", "--ejemplos", str(trabajo / "ejemplos.jsonl"), "--esquema", str(trabajo / "esquema.json"),
           "--salida", str(salida), "--ckpt", a.ckpt, "--repo", a.repo]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=a.repo)
    (trabajo / "train.log").write_text(r.stdout + "\n" + r.stderr)
    if r.returncode or not salida.exists():
        raise RuntimeError("chispa train: " + (r.stderr or r.stdout)[-600:])
    return salida


def servir_y_decidir(modelo, rs, trabajo, a):
    cmd = [a.servidor, "-addr", f"127.0.0.1:{a.puerto}", "-modelo", str(modelo), "-tok", a.tok]
    url = f"http://127.0.0.1:{a.puerto}"
    with open(trabajo / "servidor.log", "w") as log:
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(120):
                if p.poll() is not None:
                    raise RuntimeError("el servidor terminó: " + (trabajo / "servidor.log").read_text()[-400:])
                try:
                    urllib.request.urlopen(url + "/healthz", timeout=2).read()
                    break
                except OSError:
                    time.sleep(1)
            else:
                raise RuntimeError("el servidor no responde en /healthz")
            return [decidir(url, r) for r in rs]
        finally:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()


def correr_pliegue(clave, rs, sop, a, base):
    trabajo = base / ("%s__%s" % (clave[0].replace(":", "_"), str(clave[1]).replace(":", "_")))[:120]
    ultimo = None
    for intento in (1, 2):
        try:
            t0 = time.time()
            m = entrenar_pliegue(rs, sop, trabajo, a)
            t_train = time.time() - t0
            preds = servir_y_decidir(m, rs, trabajo, a)
            return preds, {"entrenar_s": round(t_train, 1), "total_s": round(time.time() - t0, 1), "bytes": m.stat().st_size, "intentos": intento}
        except Exception as e:  # noqa: BLE001
            ultimo = f"{type(e).__name__}: {e}"
            print(f"  pliegue {clave}: intento {intento} falló: {ultimo[:300]}", flush=True)
    raise RuntimeError(ultimo)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--jevbench", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--servidor", required=True, help="binario chispa-server")
    ap.add_argument("--tok", required=True, help=".chispa-tok de e5")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--k", type=int, nargs="*", default=[8, 32])
    ap.add_argument("--puerto", type=int, default=8090)
    ap.add_argument("--minutos", type=float, default=0, help="tope de reloj para todos los pliegues (0 = sin tope)")
    ap.add_argument("--max-pliegues", type=int, default=0, help="solo para pruebas en seco")
    a = ap.parse_args(argv)
    a.ckpt, a.servidor, a.tok = (str(Path(x).resolve()) for x in (a.ckpt, a.servidor, a.tok))
    os.environ.setdefault("PYTHONPATH", a.repo + os.pathsep + a.repo + "/sdk/python")
    filas = cargar_jevbench(a.jevbench)
    sal, T0 = Path(a.salida), time.time()
    cache = {}   # (esquema, ids del soporte) -> (preds por id, info): k = 32 reutiliza los pliegues que k = 8 ya corrió
    sal.mkdir(parents=True, exist_ok=True)
    pl_log = open(sal / "cascada_pliegues.jsonl", "a", encoding="utf-8")
    errores = 0
    for k in a.k:
        preds, omitidos, corridos = {}, [], 0
        todos = pliegues(filas, k)
        for n, (clave, rs, sop) in enumerate(todos):
            if not sop:
                omitidos += [{"id": r["id"], "motivo": "sin otros casos de su esquema"} for r in rs]
                continue
            if not cubre_opciones(rs[0], sop):
                omitidos += [{"id": r["id"], "motivo": "el soporte no cubre todas las opciones"} for r in rs]
                continue
            if a.max_pliegues and corridos >= a.max_pliegues:
                omitidos += [{"id": r["id"], "motivo": "tope --max-pliegues"} for r in rs]
                continue
            hue = (clave[0], tuple(sorted(r["id"] for r in sop)))
            if hue in cache:
                res, info = cache[hue]
                info = dict(info, reutilizado=True)
            else:
                if a.minutos and (time.time() - T0) / 60 > a.minutos:
                    omitidos += [{"id": r["id"], "motivo": "sin tiempo (tope --minutos)"} for r in rs]
                    continue
                print(f"== k={k} pliegue {clave[0]}/{clave[1]} ({len(rs)} casos, {len(sop)} ejemplos) {time.time() - T0:.0f} s", flush=True)
                try:
                    res, info = correr_pliegue(clave, rs, sop, a, sal / "pliegues")
                except RuntimeError as e:
                    omitidos += [{"id": r["id"], "motivo": f"falló dos veces: {str(e)[:200]}"} for r in rs]
                    pl_log.write(json.dumps({"k": k, "pliegue": list(clave), "fallo": str(e)[:400]}, ensure_ascii=False) + "\n")
                    pl_log.flush()
                    continue
                cache[hue] = (res, info)
                corridos += 1
            for r, p in zip(rs, res):
                preds[r["id"]] = dict(p, pliegue=f"{clave[0]}/{clave[1]}")
            pl_log.write(json.dumps({"k": k, "pliegue": list(clave), "casos": len(rs), "soporte": len(sop), **info}, ensure_ascii=False) + "\n")
            pl_log.flush()
        errores += sum(p.get("layer") == "error" for p in preds.values())
        escribir(sal / "pred" / f"cascada_k{k}.jsonl", [preds[r["id"]] for r in filas if r["id"] in preds])
        (sal / "pred" / f"cascada_k{k}_omitidos.json").write_text(json.dumps(omitidos, ensure_ascii=False, indent=1))
        print(f"== cascada k={k}: {len(preds)} casos respondidos, {len(omitidos)} omitidos, {corridos} pliegues nuevos, "
              f"{(time.time() - T0) / 60:.1f} min", flush=True)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
