"""Zero-shot: un .chispa solo con el esquema de ferretería (docs/02-inicio-rapido.md), sin ejemplos.

    python zero_shot.py --l1 potion.chispa-l1 [--salida ferreteria.chispa]
"""
import argparse
from pathlib import Path

import chispa

AQUI = Path(__file__).resolve().parent

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--l1", required=True, help="potion .chispa-l1 exportado con runtime/l1/exportar.py")
ap.add_argument("--salida", default="ferreteria.chispa")
a = ap.parse_args()

inf = chispa.entrenar(None, AQUI / "ferreteria.json", a.salida, l1=a.l1)  # sin ejemplos: zero-shot
print(f"{inf['salida']}: modo {inf['modo']}, secciones {'+'.join(inf['secciones'])}")
