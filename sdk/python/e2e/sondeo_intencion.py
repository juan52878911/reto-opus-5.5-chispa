"""Punta a punta (T4.3): 50 por clase de intención → `chispa train` → .chispa → cargar con chispa3 → precisión en el test del sondeo.

    python sdk/python/e2e/sondeo_intencion.py [--l1 /tmp/potion.chispa-l1] [--k 50] [--trabajo DIR]

El sondeo trae 32 por clase en `train_intencion.jsonl`; para llegar a 50 se completan con filas de MASSIVE es (train) de ~/hf,
sin repetir texto del test del sondeo. Todo en un directorio temporal que se borra."""
import argparse
import glob
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "sdk/python"))
from chispa.train import GO_DIR, encontrar_go  # noqa: E402


def jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--l1", default="")
    ap.add_argument("--k", type=int, default=50)
    ap.add_argument("--trabajo")
    a = ap.parse_args()
    S = RAIZ / "model/sondeo"
    train, test = jsonl(S / "train_intencion.jsonl"), jsonl(S / "intencion.jsonl")
    desc, opciones = train[0]["descripciones"], train[0]["opciones"]
    en_test = {r["texto"] for r in test}
    por = {c: [] for c in opciones}
    vistos = set()
    for r in train:
        por[r["etiqueta"]].append(r["texto"])
        vistos.add(r["texto"])
    b = glob.glob(os.path.expanduser("~/hf/hub/datasets--mteb--amazon_massive_intent/snapshots/*/"))[0]
    for r in map(json.loads, gzip.open(b + "train/es.json.gz", "rt", encoding="utf-8")):
        c, t = r["label_text"], r["text"]
        if c in por and len(por[c]) < a.k and t not in vistos and t not in en_test:
            por[c].append(t)
            vistos.add(t)
    for c, l in por.items():
        assert len(l) >= a.k, (c, len(l))
        del l[a.k:]
    d = Path(a.trabajo or tempfile.mkdtemp(prefix="chispa-e2e-"))
    d.mkdir(exist_ok=True)
    try:
        with open(d / "ejemplos.csv", "w", encoding="utf-8", newline="") as f:
            import csv
            w = csv.writer(f)
            w.writerow(["texto", "etiqueta"])
            for c, l in por.items():
                w.writerows((t, c) for t in l)
        (d / "esquema.json").write_text(json.dumps(
            {"id": "intencion", "pregunta": "¿Qué quiere hacer la persona?", "tipo": "choice", "opciones": desc}, ensure_ascii=False))
        cmd = [sys.executable, "-m", "chispa", "train", "--ejemplos", str(d / "ejemplos.csv"), "--esquema", str(d / "esquema.json"),
               "--salida", str(d / "intencion.chispa")] + (["--l1", a.l1] if a.l1 else [])
        t0 = time.time()
        r = subprocess.run(cmd, env=dict(os.environ, PYTHONPATH=str(RAIZ / "sdk/python")), capture_output=True, text=True)
        reloj = time.time() - t0
        print(r.stderr.strip())
        if r.returncode:
            sys.exit(f"chispa train falló ({r.returncode})")
        print(f"RELOJ chispa train ({len(opciones)} clases × {a.k} = {len(opciones) * a.k} ejemplos): {reloj:.1f} s")
        with open(d / "prueba.jsonl", "w", encoding="utf-8") as f:
            for r_ in test:
                f.write(json.dumps({"text": r_["texto"], "label": r_["etiqueta"]}, ensure_ascii=False) + "\n")
        plan = {"salida": str(d / "intencion.chispa"), "prueba": str(d / "prueba.jsonl"),
                "pregunta": {"id": "intencion", "texto": "¿Qué quiere hacer la persona?", "kind": "choice",
                             "opciones": [{"id": k, "description": v} for k, v in desc.items()]}}
        (d / "plan.json").write_text(json.dumps(plan, ensure_ascii=False))
        env = dict(os.environ, GOFLAGS="-mod=mod", GOPROXY="off")
        r = subprocess.run([encontrar_go(), "run", ".", "evaluar", str(d / "plan.json")], cwd=GO_DIR, env=env, capture_output=True, text=True)
        if r.returncode:
            sys.exit(r.stderr)
        print("TEST del sondeo (%d filas):" % len(test), r.stdout.strip())
        print("tamaño .chispa: %.1f MB" % (os.path.getsize(d / "intencion.chispa") / 1e6))
    finally:
        if not a.trabajo:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    main()
