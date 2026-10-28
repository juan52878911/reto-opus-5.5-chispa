"""Tres tandas de latencia en el i7: e5-small (3 variantes x 1/4 hilos) y L1. Uso:
CHISPA_WORK=/tmp/i7work CHISPA_REPS=300 python medir_i7.py SALIDA.jsonl  (L1: /tmp/l1medir /tmp/potion.chispa-l1)"""
import json, os, subprocess, sys, time
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent / "codificadores.py"
VARIANTES = ["e5-small-int8-podado", "e5-small-fp32-podado", "e5-small-fp32"]
sal = Path(sys.argv[1])


def estado():
    mem = {l.split(":")[0]: int(l.split()[1]) // 1024 for l in open("/proc/meminfo") if l.startswith(("MemTotal", "MemAvailable"))}
    return dict(t=time.strftime("%H:%M:%S"), loadavg=open("/proc/loadavg").read().split()[:3], mem_mb=mem)


def anota(**d):
    with sal.open("a") as f:
        f.write(json.dumps(d) + "\n")
    print(json.dumps(d)[:200], flush=True)


for tanda in (1, 2, 3):
    if tanda > 1:
        time.sleep(60)
    for v in VARIANTES:
        for h in (1, 4):
            antes = estado()
            for intento in (1, 2):
                p = subprocess.run([sys.executable, str(BENCH), "_trabajador", v, str(h)], capture_output=True, text=True)
                if p.returncode == 0 and p.stdout.strip():
                    break
            if p.returncode != 0:
                anota(tanda=tanda, variante=v, hilos=h, error=p.stderr[-300:]); continue
            anota(tanda=tanda, antes=antes, despues=estado(), **json.loads(p.stdout.strip().splitlines()[-1]))
    antes = estado()
    p = subprocess.run(["/tmp/l1medir", "/tmp/potion.chispa-l1"], capture_output=True, text=True)
    anota(tanda=tanda, variante="l1", antes=antes, despues=estado(), salida=p.stdout, rc=p.returncode, err=p.stderr[-200:])
