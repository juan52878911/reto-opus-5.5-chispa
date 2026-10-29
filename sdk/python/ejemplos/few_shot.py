"""Few-shot: el esquema de ferretería con 5 ejemplos por opción (ejemplos.csv). Con < 10 por opción no se entrena L0 y
L1 se calibra con los 25 ejemplos.

    python few_shot.py --l1 potion.chispa-l1 [--salida ferreteria-fs.chispa]
"""
import argparse
from pathlib import Path

import chispa

AQUI = Path(__file__).resolve().parent

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--l1", required=True, help="potion .chispa-l1 exportado con runtime/l1/exportar.py")
ap.add_argument("--salida", default="ferreteria-fs.chispa")
ap.add_argument("--sin-go", action="store_true", help="no usa el entrenador de Go (L1 no se calibra; solo para probar sin un L1 real)")
a = ap.parse_args()

inf = chispa.entrenar(AQUI / "ejemplos.csv", AQUI / "ferreteria.json", a.salida, l1=a.l1, usar_go=not a.sin_go)
print(f"{inf['salida']}: modo {inf['modo']}, secciones {'+'.join(inf['secciones'])}")
for k, v in inf["omitidas"].items():
    print(f"  sin {k}: {v}")
