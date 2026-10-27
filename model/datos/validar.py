"""Validación de filas contra `model/esquema.md` (v1) y la regla de licencias.

`python -m model.datos.validar <fichero.jsonl>...` imprime los errores y sale con 1 si hay alguno.
"""
import json
import re
import sys

OBLIGATORIOS = {
    "id": str, "tarea": str, "tipo": str, "pregunta": str, "texto": str, "opciones": list,
    "descripciones": dict, "etiqueta": str, "idioma": str, "split": str, "fuente": str,
    "licencia": str, "uso_comercial": bool,
}
TIPOS = ("choice", "noul", "score")
SPLITS = ("train", "dev", "test")
# Licencias que no permiten uso comercial (o no lo permiten con claridad).
RE_NO_COMERCIAL = re.compile(r"(^|[^a-z])(nc|nd)([^a-z]|$)|sin verificar|no clara|unknown|desconocida", re.I)


def errores_fila(f):
    """Lista de textos de error de una fila (vacía si es válida)."""
    e = []
    for campo, t in OBLIGATORIOS.items():
        if campo not in f:
            e.append("falta %s" % campo)
        elif not isinstance(f[campo], t) or (t is str and not f[campo].strip()):
            e.append("%s: tipo o valor inválido" % campo)
    if e:
        return e
    ops, desc = f["opciones"], f["descripciones"]
    if f["tipo"] not in TIPOS:
        e.append("tipo %r desconocido" % f["tipo"])
    if f["split"] not in SPLITS:
        e.append("split %r desconocido" % f["split"])
    if not ops or not all(isinstance(o, str) for o in ops) or len(set(ops)) != len(ops):
        e.append("opciones vacías, no texto o repetidas")
        return e
    if f["tipo"] == "noul" and ops != ["false", "true"]:
        e.append("noul exige opciones ['false','true']")
    if f["tipo"] == "score" and ops != [str(i) for i in range(1, len(ops) + 1)]:
        e.append("score exige opciones ['1',…,'K']")
    if f["etiqueta"] not in ops:
        e.append("etiqueta %r fuera de opciones" % f["etiqueta"])
    faltan = [o for o in ops if not str(desc.get(o, "")).strip()]
    if faltan:
        e.append("opciones sin descripción: %s" % faltan[:3])
    if not f["uso_comercial"] and f["split"] != "test":
        e.append("uso_comercial=false en split %s (solo test)" % f["split"])
    if f["uso_comercial"] and RE_NO_COMERCIAL.search(f["licencia"]):
        e.append("licencia %r no comercial/dudosa con uso_comercial=true" % f["licencia"])
    if "plantilla" in f and not isinstance(f["plantilla"], str):
        e.append("plantilla debe ser str")
    return e


def errores_conjunto(filas):
    """Errores de cada fila (`id: error`) más los de conjunto: ids únicos y plantillas sin fugas."""
    out, vistos, plantillas = [], set(), {}
    for f in filas:
        for m in errores_fila(f):
            out.append("%s: %s" % (f.get("id", "?"), m))
        if f.get("id") in vistos:
            out.append("%s: id repetido" % f["id"])
        vistos.add(f.get("id"))
        if isinstance(f.get("id"), str) and isinstance(f.get("split"), str):
            partes = f["id"].split(":")
            if len(partes) != 3 or partes[1] != f["split"]:
                out.append("%s: el id no sigue <fuente>:<split>:<n> con el split de la fila" % f["id"])
        if "plantilla" in f:
            plantillas.setdefault((f.get("fuente", "").split(" ")[0], f["plantilla"]), set()).add(f.get("split"))
    for (fuente, p), splits in plantillas.items():
        if len(splits) > 1:
            out.append("plantilla %s/%s en varios splits: %s" % (fuente, p, sorted(splits)))
    return out


def leer_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def main(argv=None):
    paths = (argv if argv is not None else sys.argv[1:])
    malo = 0
    for p in paths:
        errs = errores_conjunto(leer_jsonl(p))
        print("%s: %s" % (p, "OK" if not errs else "%d errores" % len(errs)))
        for m in errs[:20]:
            print("  " + m)
        malo += bool(errs)
    return 1 if malo else 0


if __name__ == "__main__":
    sys.exit(main())
