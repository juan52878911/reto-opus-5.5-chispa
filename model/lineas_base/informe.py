"""Tablas de `informe.md` a partir de `resultados.json`: python -m model.lineas_base.informe > tablas.md"""
import json
from pathlib import Path

AQUI = Path(__file__).resolve().parent
NOMBRES = {"massive": "MASSIVE es (intención, 60 clases)", "hatecheck": "HateCheck-ES (toxicidad, 2 clases)",
           "clinc150": "CLINC150 con oos→escalate (151 clases)", "inyecciones": "deepset (inyección, 2 clases)",
           "herramientas": "Herramientas (32 clases, con escalate)"}
SISTEMAS = ("l0_tfidf_lr", "e5_knn8", "e5_knn32", "thx01")


def f(v, d=3):
    return "-" if v is None else ("%.*f" % (d, v)).replace(".", ",")


def main():
    res = json.load(open(AQUI / "resultados.json"))
    for t, nombre in NOMBRES.items():
        if t not in res:
            continue
        print("### %s\n" % nombre)
        print("| sistema | n | macro-F1 | ECE | cob@0,95 | AUROC escalate | p99 ms | T |")
        print("|---|---|---|---|---|---|---|---|")
        for s in SISTEMAS:
            r = res[t].get(s)
            if not r:
                continue
            print("| %s | %d | %s | %s | %s | %s | %s | %s |" % (
                s, r["n"], f(r["macro_f1"]), f(r["ece"]), f(r["cobertura_p95"]["cobertura"]),
                f(r.get("auroc_escalate")), f(r.get("latencia", {}).get("p99_ms"), 1), f(r.get("temperatura"), 3)))
        print()


if __name__ == "__main__":
    main()
