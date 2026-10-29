"""Cuenta las filas noul cuya torre de entrenamiento cambia con `texto_consulta` (R9b): `opciones == ["true", "false"]` o con
«true» en una posición distinta de la última. Por fuente, tarea y split.

    python -m model.l2.contar_orden_noul --salida <dir> [--meta <dir>] [--convertir] [--jevbench <ruta>] [--fixtures]

Fuentes: `meta/<fuente>/**/*.jsonl.gz` (tsjev, tsinst, …), los conversores de `model.datos` (todos los splits, dev incluido; con
`--fixtures`, los fixtures) y JevBench. Escribe `<dir>/orden-noul.json` y `<dir>/orden-noul.md`.
"""
import argparse
import collections
import gzip
import json
import sys
from pathlib import Path

CAMPOS = ("noul", "true_false", "true_no_ultima", "afectadas", "sin_true")


def clasifica(ops):
    """(true_false, true_no_ultima, sin_true) de las opciones de una fila noul."""
    if "true" not in ops:
        return False, False, True
    return list(ops) == ["true", "false"], ops.index("true") != len(ops) - 1, False


def contar(filas, fuente, cuentas):
    for r in filas:
        if r.get("tipo") != "noul":
            continue
        tf, nu, st = clasifica(r["opciones"])
        c = cuentas[(fuente, r.get("tarea", "?"), r.get("split", "?"))]
        c["noul"] += 1
        c["true_false"] += tf
        c["true_no_ultima"] += nu
        c["afectadas"] += tf or nu
        c["sin_true"] += st


def lineas(abrir):
    with abrir as fh:   # solo \n: splitlines cortaría en U+2028 dentro de las cadenas
        for l in fh.read().split("\n"):
            if l.strip():
                yield json.loads(l)


def filas_meta(raiz):
    raiz = Path(raiz)
    for f in sorted(raiz.glob("*/**/*.jsonl.gz")):
        yield "meta/" + f.relative_to(raiz).parts[0], lineas(gzip.open(f, "rt", encoding="utf-8"))


def filas_datos(fuentes, fixtures):
    from model.datos import convertir as cv
    for n in fuentes:
        try:
            filas, _ = cv._convertir_una(n, fixtures)
        except Exception as e:
            print("aviso: %s no se pudo convertir (%s: %s)" % (n, type(e).__name__, e), file=sys.stderr)
            continue
        yield "datos/" + n, filas


def tabla(cuentas):
    out = ["| fuente | tarea | split | noul | [true,false] | true no última | afectadas | sin true |", "|---|---|---|---:|---:|---:|---:|---:|"]
    tot = collections.Counter()
    for (f, t, s), c in sorted(cuentas.items()):
        out.append("| %s | %s | %s | %s |" % (f, t, s, " | ".join(str(c[k]) for k in CAMPOS)))
        tot.update(c)
    out.append("| **total** | | | %s |" % " | ".join("**%d**" % tot[k] for k in CAMPOS))
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--meta")
    ap.add_argument("--convertir", action="store_true", help="contar los conversores de model.datos")
    ap.add_argument("--fixtures", action="store_true", help="los conversores leen sus fixtures en vez de ~/hf")
    ap.add_argument("--jevbench")
    a = ap.parse_args(argv)
    cuentas = collections.defaultdict(collections.Counter)
    fuentes = []
    if a.meta:
        fuentes.append(filas_meta(a.meta))
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
    plano = [dict(zip(("fuente", "tarea", "split"), k), **{x: c[x] for x in CAMPOS}) for k, c in sorted(cuentas.items())]
    tot = {k: sum(c[k] for c in cuentas.values()) for k in CAMPOS}
    (out / "orden-noul.json").write_text(json.dumps({"total": tot, "filas": plano}, ensure_ascii=False, indent=1), encoding="utf-8")
    md = tabla(cuentas)
    (out / "orden-noul.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
