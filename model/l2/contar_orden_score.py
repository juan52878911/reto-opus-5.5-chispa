"""Cuenta las filas score cuyo entrenamiento cambia con `niveles_score` (R16): orden no ascendente de las opciones (CORAL se
indexaba por la posición declarada) y ids fuera de `1..K` (`"0"`, `"01"`, huecos, no enteros; se descartan al cargar). Por fuente,
tarea, split y K.

    python -m model.l2.contar_orden_score --salida <dir> [--meta <dir>] [--datos <dir>] [--convertir] [--jevbench <ruta>] [--fixtures]

Fuentes: `meta/<fuente>/**/*.jsonl.gz`, los `*.jsonl` ya convertidos de `--datos` (salida de `model.datos.convertir`), los conversores de `model.datos` (todos los splits, dev incluido; con `--fixtures`, los
fixtures) y JevBench. Escribe `<dir>/orden-score.json` y `<dir>/orden-score.md`. Mismas fuentes que `contar_orden_noul`.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

from model.datos.comun import score_valido
from model.l2.contar_orden_noul import filas_datos, filas_meta, lineas

CAMPOS = ("score", "no_ascendente", "fuera_de_1k", "afectadas")


def clasifica(ops):
    """(no_ascendente, fuera_de_1k) de las opciones de una fila score: el primero solo cuenta si los ids son 1..K en otro orden."""
    if not score_valido(ops):
        return False, True
    return [str(o) for o in ops] != sorted((str(o) for o in ops), key=int), False


def contar(filas, fuente, cuentas):
    for r in filas:
        if r.get("tipo") != "score":
            continue
        na, fuera = clasifica(r["opciones"])
        c = cuentas[(fuente, r.get("tarea", "?"), r.get("split", "?"), len(r["opciones"]))]
        c["score"] += 1
        c["no_ascendente"] += na
        c["fuera_de_1k"] += fuera
        c["afectadas"] += na or fuera


def filas_convertidas(raiz):
    """Los `<fuente>.jsonl` de una salida de `model.datos.convertir` (el SEPARADOR es \\n, como en `lineas`)."""
    for f in sorted(Path(raiz).glob("*.jsonl")):
        yield "datos/" + f.stem, lineas(open(f, encoding="utf-8"))


def tabla(cuentas):
    out = ["| fuente | tarea | split | K | score | no ascendente | fuera de 1..K | afectadas |", "|---|---|---|---:|---:|---:|---:|---:|"]
    tot = collections.Counter()
    for (f, t, s, k), c in sorted(cuentas.items()):
        out.append("| %s | %s | %s | %d | %s |" % (f, t, s, k, " | ".join(str(c[x]) for x in CAMPOS)))
        tot.update(c)
    out.append("| **total** | | | | %s |" % " | ".join("**%d**" % tot[x] for x in CAMPOS))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--meta")
    ap.add_argument("--datos", help="directorio con los .jsonl ya convertidos por model.datos.convertir")
    ap.add_argument("--convertir", action="store_true", help="contar los conversores de model.datos")
    ap.add_argument("--fixtures", action="store_true", help="los conversores leen sus fixtures en vez de ~/hf")
    ap.add_argument("--jevbench")
    a = ap.parse_args(argv)
    cuentas = collections.defaultdict(collections.Counter)
    fuentes = []
    if a.meta:
        fuentes.append(filas_meta(a.meta))
    if a.datos:
        fuentes.append(filas_convertidas(a.datos))
    if a.convertir:
        from model.datos.convertir import FUENTES
        fuentes.append(filas_datos(FUENTES, a.fixtures))
    if a.jevbench:
        from model.evaluacion.jevbench import cargar_jevbench
        fuentes.append([("jevbench", cargar_jevbench(a.jevbench))])
    for gen in fuentes:
        for fuente, filas in gen:
            contar(filas, fuente, cuentas)
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    plano = [dict(zip(("fuente", "tarea", "split", "k"), k), **{x: c[x] for x in CAMPOS}) for k, c in sorted(cuentas.items())]
    tot = {x: sum(c[x] for c in cuentas.values()) for x in CAMPOS}
    (out / "orden-score.json").write_text(json.dumps({"total": tot, "filas": plano}, ensure_ascii=False, indent=1), encoding="utf-8")
    md = tabla(cuentas)
    (out / "orden-score.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
