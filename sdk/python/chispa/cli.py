"""`chispa train …` y `chispa decide …`."""
from __future__ import annotations

import argparse
import json
import sys

from .cliente import Chispa, ChispaError
from .tipos import Choice, Noul, Score


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="chispa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train", help="entrena un .chispa v3 con pocos ejemplos, en CPU")
    t.add_argument("--ejemplos", required=True, help="CSV/JSONL con columnas texto|text y etiqueta|label")
    t.add_argument("--esquema", required=True, help="YAML/JSON: id, pregunta, tipo, opciones (con descripciones)")
    t.add_argument("--salida", required=True)
    t.add_argument("--l1", help=".chispa-l1 (potion exportado con runtime/l1/exportar.py)")
    t.add_argument("--ckpt", help="checkpoint de L2: calibra y exporta L2 y ESQUEMAS con model/l2")
    t.add_argument("--l2", help=".chispa ya exportado por model/l2/exportar.py: de aquí salen L2 y ESQUEMAS")
    t.add_argument("--conjunta", action="store_true",
                   help="añade la cabeza conjunta L0 + L2 (sección CONJ); necesita --ckpt y --l2 (o --ckpt solo)")
    t.add_argument("--repo", help="raíz del repositorio (por defecto CHISPA_REPO o el que contiene este paquete)")
    t.add_argument("--pregunta", help="id de la pregunta si el esquema trae varias")
    t.add_argument("--semilla", type=int, default=1)
    t.add_argument("--frac-valid", type=float, default=0.2)
    t.add_argument("--l0-max-mb", type=float, default=48.0,
                   help="tope de la tabla de pesos de L0 en MB; reduce los buckets de hashing hasta que cabe (kindling rechaza > 64 MiB)")
    t.add_argument("--l0tf-max-mb", type=float, default=48.0,
                   help="con --conjunta: tope de los coeficientes de L0TF en MB; poda el vocabulario por frecuencia hasta que cabe")
    t.add_argument("--precision-objetivo", type=float, default=0.95,
                   help="con --conjunta: precisión mínima de lo aceptado para fijar el τ de L2c fuera de pliegue (0,95)")
    t.add_argument("--validacion", help="con --conjunta: CSV/JSONL de texto y etiqueta, fuera de --ejemplos; el τ de L2c se elige sobre estas filas")
    t.add_argument("--margen", type=float, default=0.02,
                   help="con --conjunta y sin --validacion: el τ fuera de pliegue se fija para precisión objetivo + margen (0,02)")
    t.add_argument("--suelo", type=float, default=0.05,
                   help="con --conjunta y sin --validacion: suelo de τ = el que deja fuera esta fracción fuera de pliegue (0,05)")
    t.add_argument("--l0tf-f16", action="store_true", help="con --conjunta: coeficientes de L0TF en f16 en vez de f32")
    d = sub.add_parser("decide", help="una pregunta contra un servidor")
    d.add_argument("--url", required=True)
    d.add_argument("--estado", required=True)
    d.add_argument("--tipo", choices=["choice", "noul", "score"], default="choice")
    d.add_argument("--pregunta", required=True)
    d.add_argument("--opciones", nargs="*", default=[], help="choice: ids; score: el número de niveles")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "train":
            from .train import entrenar
            entrenar(a.ejemplos, a.esquema, a.salida, l1=a.l1, ckpt=a.ckpt, l2=a.l2, conjunta=a.conjunta, repo=a.repo,
                     pregunta=a.pregunta, semilla=a.semilla, frac_valid=a.frac_valid, l0_max_mb=a.l0_max_mb,
                     l0tf_max_mb=a.l0tf_max_mb, l0tf_f16=a.l0tf_f16,
                     precision_objetivo=a.precision_objetivo, validacion=a.validacion, margen=a.margen, suelo=a.suelo,
                     log=lambda m: print(m, file=sys.stderr))
        else:
            q = {"choice": lambda: Choice("q", a.pregunta, a.opciones), "noul": lambda: Noul("q", a.pregunta),
                 "score": lambda: Score("q", a.pregunta, int(a.opciones[0]))}[a.tipo]()
            r = Chispa(a.url).decidir(a.estado, [q])[0]
            print(json.dumps(r.__dict__, ensure_ascii=False))
    except (ChispaError, ValueError, OSError) as e:
        print(f"chispa: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
