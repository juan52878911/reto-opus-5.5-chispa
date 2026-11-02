"""Fixture inventado de Clandestino: `python -m model.datos.fixtures.generar_clandestino`.

Nada viene del dataset real (las columnas son la hipótesis de `model/datos/clandestino.py`): 100 plantillas × 2 mensajes de personas, más 30
filas `Is AI Generated = true` que el conversor tiene que descartar.
"""
import csv
from pathlib import Path

AQUI = Path(__file__).parent
TIPOS = ("burla", "amenaza", "exclusion")
GRUPOS = ("vecinos", "turistas", "estudiantes")


def filas():
    out = []
    for t in range(100):
        for k in range(2):
            n = t * 2 + k
            gs = [g for j, g in enumerate(GRUPOS) if (n >> j) & 1 and n % 5]
            out.append({"Text": "Mensaje inventado número %d de la plantilla %d: ¿qué opinan de la situación?" % (n, t), "Is AI Generated": "false",
                        "Template ID": "plantilla-%03d" % t, "Language": "es", "Score": 1 + n % 5, "Label": "true" if n % 3 == 0 else "false",
                        "Type": TIPOS[n % 3], "Groups": ";".join(gs)})
    for n in range(30):
        out.append({"Text": "Texto generado por máquina %d" % n, "Is AI Generated": "true", "Template ID": "plantilla-%03d" % (n % 100),
                    "Language": "es", "Score": 5, "Label": "true", "Type": TIPOS[0], "Groups": GRUPOS[0]})
    return out


def main():
    d = AQUI / "clandestino"
    d.mkdir(parents=True, exist_ok=True)
    (d / "README.md").write_text("---\nlicense: mit\n---\n# Tarjeta inventada del fixture clandestino\n", encoding="utf-8")
    fs = filas()
    with open(d / "clandestino.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fs[0]))
        w.writeheader()
        w.writerows(fs)


if __name__ == "__main__":
    main()
