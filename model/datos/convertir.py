"""Convierte los datasets públicos al esquema de Chispa (`model/esquema.md`).

    python -m model.datos.convertir --salida <dir> [--fuentes massive,hatecheck] [--fixtures]

Escribe `<dir>/<fuente>.jsonl` (todos los splits) y `<dir>/resumen.json` con el estado por fuente:
`convertida` (con filas por split), `no disponible` (no está en ~/hf) o `no convertida` (con el error).
`--fixtures` convierte los fixtures de `model/datos/fixtures/` en vez de ~/hf.
"""
import argparse
import collections
import importlib
import json
import sys
import traceback
from pathlib import Path

from . import validar
from .comun import FuenteAusente

FUENTES_LIBRES = ("odio_alia", "toxicidad_protestas", "toxicidad_constitucion", "goemociones", "spam_tanaos", "soporte_ti",
                  "ciberacoso", "clima", "riesgo_suicida", "pqrs_gb9w", "pqrs_e86p", "pqrs_xtj2", "pqrs_enrutamiento")
FUENTES = ("massive", "hatecheck", "banking77", "clinc150", "inyecciones", "xnli", "sib200", "pawsx") + FUENTES_LIBRES
NO_EN_PLAN = {"necos-tox": "no disponible: no está en ~/hf (NECOS-TOX solo si se encuentra)"}
FIXTURES = Path(__file__).parent / "fixtures"


def _convertir_una(nombre, usar_fixtures):
    mod = importlib.import_module("%s.%s" % (__package__, nombre))
    raiz = FIXTURES / nombre if usar_fixtures else None
    filas, info = mod.convertir(raiz)
    errs = validar.errores_conjunto(filas)
    if errs:
        raise ValueError("%d filas inválidas; primera: %s" % (len(errs), errs[0]))
    return filas, info


def convertir_fuentes(salida, fuentes=FUENTES, usar_fixtures=False):
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    resumen = dict(NO_EN_PLAN)
    for nombre in fuentes:
        try:
            try:
                filas, info = _convertir_una(nombre, usar_fixtures)
            except FuenteAusente:
                raise
            except Exception:  # segundo intento y se marca (parada de dos fallos)
                filas, info = _convertir_una(nombre, usar_fixtures)
        except FuenteAusente as e:
            resumen[nombre] = {"estado": "no disponible", "detalle": "%s no está en ~/hf" % e}
            continue
        except Exception as e:
            resumen[nombre] = {"estado": "no convertida", "error": "%s: %s" % (type(e).__name__, e),
                               "traza": traceback.format_exc(limit=3)}
            continue
        with open(salida / (nombre + ".jsonl"), "w", encoding="utf-8") as fh:
            for f in filas:
                fh.write(json.dumps(f, ensure_ascii=False, sort_keys=True) + "\n")
        resumen[nombre] = {"estado": "convertida", "filas": dict(collections.Counter(f["split"] for f in filas)),
                           **info}
    with open(salida / "resumen.json", "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, ensure_ascii=False, indent=2, sort_keys=True)
    return resumen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--fuentes", default=",".join(FUENTES))
    ap.add_argument("--fixtures", action="store_true", help="convertir los fixtures en vez de ~/hf")
    a = ap.parse_args(argv)
    fuentes = [s for s in a.fuentes.split(",") if s]
    mal = [s for s in fuentes if s not in FUENTES]
    if mal:
        ap.error("fuentes desconocidas %s; válidas: %s" % (mal, ",".join(FUENTES)))
    resumen = convertir_fuentes(a.salida, fuentes, a.fixtures)
    for nombre, r in resumen.items():
        print("%-12s %s" % (nombre, r if isinstance(r, str) else
                             r["estado"] + " " + str(r.get("filas") or r.get("error") or r.get("detalle"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
