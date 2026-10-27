"""Acuerdo entre humanos por tarea: el techo contra el que se mide a Chispa.

    python -m model.liston.acuerdo_humano [--salida /tmp/liston] [--fuentes a,b] [--readme]

Por tarea: α de Krippendorff (nominal, admite nº variable de anotadores), κ de Fleiss (sobre las
unidades con el nº de anotadores más frecuente), κ de Cohen si hay dos codificadores fijos (con
`model.etiquetado.acuerdo.kappa`) y el «techo humano»: exactitud media de un anotador contra la mayoría
de los demás (si los demás empatan, se reparte el acierto entre las clases empatadas).
Con `--readme` reescribe la tabla de `README.md` entre las marcas <!-- tabla -->.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

from model.etiquetado.acuerdo import kappa as kappa_cohen

from . import fuentes

DIR = Path(__file__).parent
MARCA = ("<!-- tabla -->", "<!-- /tabla -->")


def alfa_krippendorff(unidades):
    """α nominal. `unidades` = listas de etiquetas; las de <2 votos no cuentan. None si no hay varianza."""
    o = collections.defaultdict(float)
    n = 0
    for v in unidades:
        m = len(v)
        if m < 2:
            continue
        c = collections.Counter(v)
        n += m
        for a in c:
            for b in c:
                o[a, b] += c[a] * (c[b] - (a == b)) / (m - 1)
    if n < 2:
        return None
    nc = collections.Counter()
    for (a, _), x in o.items():
        nc[a] += x
    do = sum(x for (a, b), x in o.items() if a != b) / n
    de = sum(nc[a] * nc[b] for a in nc for b in nc if a != b) / (n * (n - 1))
    return None if de == 0 else 1 - do / de


def fleiss(unidades):
    """(κ, unidades usadas, anotadores por unidad). Solo entran las unidades con el nº de votos más frecuente."""
    if not unidades:
        return None, 0, 0
    m = collections.Counter(len(v) for v in unidades).most_common(1)[0][0]
    us = [collections.Counter(v) for v in unidades if len(v) == m]
    if m < 2:
        return None, len(us), m
    pbar = sum((sum(x * x for x in c.values()) - m) / (m * (m - 1)) for c in us) / len(us)
    tot = collections.Counter()
    for c in us:
        tot.update(c)
    pe = sum((x / (m * len(us))) ** 2 for x in tot.values())
    return (None if pe == 1 else (pbar - pe) / (1 - pe)), len(us), m


def cohen(unidades):
    """κ de Cohen entre el codificador 1 y el 2, si todas las unidades tienen exactamente dos votos ordenados."""
    if not unidades or any(len(v) != 2 for v in unidades):
        return None
    return kappa_cohen([(v[0], v[1]) for v in unidades])


def techo(unidades):
    """Exactitud media de un anotador frente a la mayoría de los demás (acierto repartido si empatan)."""
    tot = n = 0
    for v in unidades:
        if len(v) < 2:
            continue
        for j, propio in enumerate(v):
            c = collections.Counter(v[:j] + v[j + 1:])
            tope = max(c.values())
            cima = [k for k, x in c.items() if x == tope]
            tot += (propio in cima) / len(cima)
            n += 1
    return tot / n if n else None


def resumen(unidades):
    votos = [u["votos"] if isinstance(u, dict) else u for u in unidades]
    k, nf, m = fleiss(votos)
    return {"unidades": len(votos), "anotadores_medios": sum(map(len, votos)) / len(votos) if votos else 0,
            "alfa": alfa_krippendorff(votos), "fleiss": k, "fleiss_unidades": nf, "fleiss_anotadores": m,
            "cohen": cohen(votos), "techo": techo(votos)}


def desglose(unidades, clave):
    grupos = collections.defaultdict(list)
    for u in unidades:
        grupos[clave(u)].append(u)
    return {g: resumen(us) for g, us in sorted(grupos.items())}


def tareas(solo=None):
    """{nombre: (tarea, unidades, filas, info)} para cada fuente convertible. Una que falla se marca y se sigue."""
    out, fallos = {}, {}
    pasos = {
        "multipico": ("ironia", lambda: (fuentes.registros_multipico(), fuentes.convertir_multipico, {})),
        "alia": ("odio", lambda: (fuentes.registros_alia(), fuentes.convertir_alia, {})),
        "toxprotestas": ("toxicidad", lambda: (fuentes.registros_toxicidad("protests"),
                                               lambda: fuentes.convertir_toxicidad("protests"), {})),
        "toxconstitucion": ("toxicidad", lambda: (fuentes.registros_toxicidad("constitution"),
                                                  lambda: fuentes.convertir_toxicidad("constitution"), {})),
        "goemotions": ("emocion", None),
    }
    for nombre, (tarea, f) in pasos.items():
        if solo and nombre not in solo:
            continue
        try:
            if nombre == "goemotions":
                unidades, info = fuentes.registros_goemotions()
                filas, _ = fuentes.convertir_goemotions()
            else:
                unidades, conv, info = f()
                filas = conv()
            out[nombre] = (tarea, unidades, filas, info)
        except Exception as e:  # una fuente que falla se marca y no frena a las demás
            fallos[nombre] = "%s: %s" % (type(e).__name__, e)
    return out, fallos


def _f(x, d=3):
    return "n/d" if x is None else ("%.*f" % (d, x))


def tabla(res):
    L = ["| Fuente | Tarea | Filas | Anotadores/fila | α Krippendorff | κ Fleiss | κ Cohen | Techo humano |",
         "|---|---|---|---|---|---|---|---|"]
    for nombre, r in res.items():
        s = r["resumen"]
        L.append("| %s | %s | %d | %s | %s | %s | %s | %s |" % (
            nombre, r["tarea"], s["unidades"], _f(s["anotadores_medios"], 2), _f(s["alfa"]),
            _f(s["fleiss"]) + (" (n=%d)" % s["fleiss_anotadores"] if s["fleiss"] is not None else ""),
            _f(s["cohen"]), _f(s["techo"])))
    return "\n".join(L)


def escribir_readme(texto, ruta=DIR / "README.md"):
    ini, fin = MARCA
    t = Path(ruta).read_text(encoding="utf-8")
    a, b = t.index(ini) + len(ini), t.index(fin)
    Path(ruta).write_text(t[:a] + "\n" + texto + "\n" + t[b:], encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default="/tmp/liston")
    ap.add_argument("--fuentes", default="")
    ap.add_argument("--readme", action="store_true")
    a = ap.parse_args(argv)
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    datos, fallos = tareas(set(filter(None, a.fuentes.split(","))))
    res = {}
    for nombre, (tarea, unidades, filas, info) in datos.items():
        with open(salida / (nombre + ".jsonl"), "w", encoding="utf-8") as fh:
            for f in filas:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
        res[nombre] = {"tarea": tarea, "resumen": resumen(unidades), "info": info}
        if nombre == "multipico":
            res[nombre]["por_variedad"] = desglose(unidades, lambda u: u["extra"]["variedad"])
    (salida / "acuerdo.json").write_text(json.dumps({"fuentes": res, "fallos": fallos}, ensure_ascii=False, indent=1))
    txt = tabla(res)
    print(txt)
    for n, e in fallos.items():
        print("FALLA %s: %s" % (n, e))
    if a.readme:
        escribir_readme(txt)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
