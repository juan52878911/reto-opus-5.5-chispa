"""`python -m tetris_ale evaluar|generar …`"""
import sys

from . import evaluar, generar

ORDENES = {"evaluar": evaluar.main, "generar": generar.main}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ORDENES:
        print("uso: python -m tetris_ale {" + "|".join(ORDENES) + "} [opciones]", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(ORDENES[sys.argv[1]](sys.argv[2:]))
