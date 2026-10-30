"""Genera el fixture inventado de M2/M5 (formato JevBench): `fixtures_largos/jevbench/datasets/public/{easy,hard,original}.jsonl`.

    python -m model.l2.tests.gen_largos

Textos de palabras inventadas con longitudes de 6 a 420 palabras (la mitad pasa de 64 tokens); 3 esquemas score (K = 4, 4 y 5),
1 choice y 1 noul. Sin datos reales.
"""
import json
import random
from pathlib import Path

PAL = "alfa beto cora duna epsa fido gamo hila ixto jovu kera lumo mide nova opal pura quen rilo sumo tavi ulfo vero wimo xeno yuma zilo".split()
DEST = Path(__file__).resolve().parent / "fixtures_largos" / "jevbench" / "datasets" / "public"


def texto(rng, n, marca):
    return " ".join(rng.choice(PAL) for _ in range(n // 2)) + " " + marca + " " + " ".join(rng.choice(PAL) for _ in range(n - n // 2))


def casos():
    rng = random.Random(7)
    out = {"easy": [], "hard": [], "original": []}
    esquemas = [("score", 4, "Rate the alfa quality"), ("score", 4, "Rate the beto clarity"), ("score", 5, "Rate the cora tone")]
    n = 0
    for tipo, k, instr in esquemas:
        for i in range(24):
            nivel = i % k
            largo = rng.choice([6, 20, 60, 140, 300, 420])
            n += 1
            out[("easy", "hard", "original")[i % 3]].append({
                "id": "fx-%03d" % n, "family": "calidad", "group": None, "split": "public",
                "state": texto(rng, largo, "nivel" + "x" * nivel),
                "question": {"type": "score", "instructions": instr, "criteria": ["level %d means %s" % (j, PAL[j]) for j in range(k)]},
                "labels": [str(j) for j in range(k)], "expected": nivel, "provenance": {"license": "MIT", "source": "inventado"}})
    for i in range(14):
        largo = rng.choice([6, 40, 120, 350])
        n += 1
        a = i % 3
        out[("easy", "hard", "original")[i % 3]].append({
            "id": "fx-%03d" % n, "family": "intencion", "group": None, "split": "public", "state": texto(rng, largo, "tema%d" % a),
            "question": {"type": "choice", "instructions": "Which topic?", "criteria": {"a": "about a", "b": "about b", "c": "about c"}},
            "labels": ["a", "b", "c"], "expected": "abc"[a], "provenance": {"license": "MIT", "source": "inventado"}})
    for i in range(14):
        largo = rng.choice([6, 40, 120, 350])
        n += 1
        out[("easy", "hard", "original")[i % 3]].append({
            "id": "fx-%03d" % n, "family": "senal", "group": None, "split": "public", "state": texto(rng, largo, "senal"),
            "question": {"type": "noul", "instructions": "Is there a signal?", "criteria": {"true": "yes", "false": "no"}},
            "labels": ["no", "yes"], "expected": "yes" if i % 2 else "no", "provenance": {"license": "MIT", "source": "inventado"}})
    return out


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    for s, cs in casos().items():
        (DEST / (s + ".jsonl")).write_text("".join(json.dumps(c) + "\n" for c in cs))


if __name__ == "__main__":
    main()
