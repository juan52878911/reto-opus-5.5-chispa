"""Equilibrio por tarea y tareas que se dejan fuera para medir (G.8).

- `es_fuera(tarea)`: ~10 % de las tareas de tasksource, fijo y con semilla (`SEMILLA_FUERA`). Se decide por el hash del nombre
  de la tarea, no por su posición en un catálogo: la misma tarea cae del mismo lado aunque el catálogo cambie, y las dos
  fuentes (tsjev e instruct) comparten la decisión porque se compara el nombre base (`tarea_base`).
  Solo se aplica a tareas de tasksource (`es_tasksource`); lo demás se deja fuera por conjunto (`CONJUNTOS_FUERA`).
- `cupos(cuentas, tope, maximo)`: filas que se conservan de cada tarea. Nadie pasa de `tope`; si aun así se pasa de `maximo`,
  el tope baja hasta que cabe (las tareas pequeñas se conservan enteras).
- El muestreo en entrenamiento es p(tarea) ∝ n_t^ALFA_TAREA sobre lo conservado (`model.l2.datos.Muestreador`, `--alfa`).
"""
import hashlib

PREFIJO_INSTRUCT = "instruct/"
SEMILLA_FUERA = 20261029
FRAC_FUERA = 0.10
CONJUNTOS_FUERA = ("massive", "hatecheck", "inyecciones")
ALFA_TAREA = 0.3
TOPE_TAREA = 2000
FUENTES_TASKSOURCE = ("tsjev", "tsinst")


def tarea_base(tarea):
    """Nombre de la tarea de tasksource sin el prefijo de instruct."""
    return tarea[len(PREFIJO_INSTRUCT):] if tarea.startswith(PREFIJO_INSTRUCT) else tarea


def _u(nombre, semilla):
    h = hashlib.blake2b(("%d|%s" % (semilla, nombre)).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2 ** 64


def es_tasksource(fila):
    return fila["id"].partition(":")[0] in FUENTES_TASKSOURCE


def tarea_fuera(tarea, frac=FRAC_FUERA, semilla=SEMILLA_FUERA):
    return _u(tarea_base(tarea), semilla) < frac


def es_fuera(fila, frac=FRAC_FUERA, semilla=SEMILLA_FUERA):
    """True si la fila es de una tarea de tasksource que se deja fuera."""
    return es_tasksource(fila) and tarea_fuera(fila["tarea"], frac, semilla)


def lista_fuera(tareas, frac=FRAC_FUERA, semilla=SEMILLA_FUERA):
    """Tareas (de las dadas) que se dejan fuera, sin repetir y ordenadas por nombre base."""
    return sorted({tarea_base(t) for t in tareas if tarea_fuera(t, frac, semilla)})


def cupos(cuentas, tope=TOPE_TAREA, maximo=None):
    """{tarea: filas a conservar}: min(n, tope), con el tope bajado (búsqueda binaria) si el total pasa de `maximo`."""
    def total(t):
        return sum(min(n, t) for n in cuentas.values())
    if maximo is not None and total(tope) > maximo:
        lo, hi = 1, tope
        while lo < hi:
            medio = (lo + hi + 1) // 2
            if total(medio) <= maximo:
                lo = medio
            else:
                hi = medio - 1
        tope = lo
    return {t: min(n, tope) for t, n in cuentas.items()}


def main(argv=None):
    """`python -m model.meta.muestreo DIR_META`: lista de tareas que se dejan fuera, en JSON por stdout."""
    import json
    import sys
    from model.l2 import datos as D
    meta = (argv if argv is not None else sys.argv[1:])[0]
    tareas = {r["tarea"] for f in D.ficheros(meta) for r in D._filas_meta(f, "train") if es_tasksource(r)}
    print(json.dumps({"semilla": SEMILLA_FUERA, "fraccion": FRAC_FUERA, "conjuntos_fuera": list(CONJUNTOS_FUERA),
                      "tareas_tasksource": len(tareas), "tareas_fuera": lista_fuera(tareas)}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
