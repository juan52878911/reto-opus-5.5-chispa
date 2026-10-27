"""Adaptador de la Arena: lee `data/ledger.jsonl` (una `AttackRound` por línea, ver
arena/contracts/contracts.go) y calcula el ASR.

ASR de un detector = rondas con `fooled` / rondas que contestó (sin `error`), como el ledger de la Arena.
ASR del enjambre = rondas con `swarm.fooled` / rondas, por dimensión.
"""
import json
from collections import defaultdict


def asr_desde_ledger(ruta):
    det = defaultdict(lambda: {"dimension": None, "ataques": 0, "engañados": 0, "errores": 0, "escalados": 0})
    sw = defaultdict(lambda: {"ataques": 0, "engañados": 0, "escalados": 0})
    rondas = 0
    with open(ruta, encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            if not linea.strip():
                continue
            try:
                r = json.loads(linea)
                dims = r["attack"]["dimension"]
                dets, s = r["detectors"] or [], r["swarm"]
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                raise ValueError(f"{ruta}:{n}: no es una AttackRound ({e!r})") from None
            rondas += 1
            for d in dets:
                a = det[d["detector_id"]]
                a["dimension"] = dims
                if d.get("error"):
                    a["errores"] += 1
                    continue
                a["ataques"] += 1
                a["engañados"] += bool(d.get("fooled"))
                a["escalados"] += bool(d.get("escalate"))
            g = sw[s.get("dimension", dims)]
            g["ataques"] += 1
            g["engañados"] += bool(s.get("fooled"))
            g["escalados"] += bool(s.get("escalated"))
    for a in list(det.values()) + list(sw.values()):
        a["asr"] = a["engañados"] / a["ataques"] if a["ataques"] else None
    return {"rondas": rondas, "detectores": dict(det), "enjambre": dict(sw)}
