"""Informe de la anonimización de PQRS (T1.1c): `python -m model.datos.informe_pqrs --salida /tmp/pqrs-informe`.

Convierte las cuatro fuentes de datos.gov.co, suma los reemplazos por tipo y, en 300 filas al azar (semilla fija) de
las tres fuentes de texto libre, cuenta cuántas AÚN tienen un nombre visible, por fuente y por patrón (T1.1d):
  - `lista`: una palabra de la lista de nombres/apellidos sin enmascarar (fuera de nombres de entidad);
  - `contexto`: palabra capitalizada o en mayúsculas desconocida tras «C.C.», «identificado con», «ciudadano/a»,
    «firma», «atentamente» o «cordialmente», o justo antes de «identificado con» / «C.C.»;
  - `racha`: 2 o más palabras seguidas con inicial mayúscula fuera del vocabulario y que no son entidad.
`informe.json` lleva SOLO recuentos. `contextos.txt` (fragmentos de las filas marcadas, para la pasada manual) se
escribe en la carpeta de salida: va a /tmp, nunca a git ni al informe. Con `--manual revision.json`
({id_de_fila: patrón}, hecha a mano tras leer `contextos.txt`) suma también los recuentos de la revisión manual.
"""
import argparse
import collections
import json
import random
import re
import sys
from pathlib import Path

from . import anonimizar, pqrs_e86p, pqrs_enrutamiento, pqrs_gb9w, pqrs_xtj2
from .comun import leer_split, raiz_hf, FuenteAusente

FUENTES = (pqrs_gb9w, pqrs_e86p, pqrs_xtj2, pqrs_enrutamiento)
RE_DIGITOS = re.compile(r"\d{6,}")


def vocabulario(filas):
    """Palabras (sin acentos) vistas en minúsculas en español corriente + en los propios textos."""
    voc = set()
    pal = re.compile(r"[a-záéíóúñü]+")
    try:
        for split in ("train",):
            for r in leer_split(raiz_hf("mrm8488/go_emotions-es-mt"), split, "data"):
                voc.update(anonimizar.sin_acentos(w) for w in pal.findall(r["text_es"]))
    except (FuenteAusente, FileNotFoundError):
        pass
    for f in filas:
        voc.update(anonimizar.sin_acentos(w) for w in pal.findall(f["texto"]))
    return voc


_CTX = re.compile(r"(?:c\.?\s?c\.?|identificad[oa] con|ciudadan[oa]|firma|atentamente|cordialmente|se[ñn]or[a]?)\W+"
                  r"((?:[A-ZÁÉÍÓÚÑ][\wáéíóúñü'’]+\s?){1,3})")
_ANTES = re.compile(r"((?:[A-ZÁÉÍÓÚÑ][\wáéíóúñü'’]+\s){1,3})(?:,\s*)?(?:identificad[oa]|c\.?\s?c\.?\s*\[DOC\])")
_ETQ = re.compile(r"\[[A-Z]+\]")


def patrones(texto, voc):
    """Conjunto de patrones de nombre aún visibles en `texto` (ya anonimizado)."""
    out = set()
    toks = list(anonimizar._PALABRA.finditer(texto))
    prot = anonimizar._protegidas(toks, texto)
    for k, m in enumerate(toks):
        if k not in prot and anonimizar.sin_acentos(m.group()) in anonimizar._TODOS and m.group()[0].isupper() \
                and not (k and anonimizar.sin_acentos(toks[k - 1].group()) in anonimizar._NO_PERSONA_ANTES):
            out.add("lista")
    desconocida = lambda w: anonimizar.sin_acentos(w) not in voc and anonimizar.sin_acentos(w) not in anonimizar._ENTIDAD_PALABRAS
    for rx in (_CTX, _ANTES):
        for m in rx.finditer(texto):
            if any(desconocida(w) and len(w) > 2 for w in anonimizar._PALABRA.findall(m.group(1))):
                out.add("contexto")
    for m in re.finditer(r"(?<![\wÁÉÍÓÚÑáéíóúñ])(?:[A-ZÁÉÍÓÚÑ][\wáéíóúñü'’]{2,}\s){1,3}[A-ZÁÉÍÓÚÑ][\wáéíóúñü'’]{2,}", texto):
        ws = anonimizar._PALABRA.findall(m.group())
        ini = not texto[:m.start()].rstrip() or texto[:m.start()].rstrip()[-1] in ".!?:;"
        if all(desconocida(w) for w in ws) and not ini:
            out.add("racha")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--muestra", type=int, default=300)
    ap.add_argument("--semilla", type=int, default=20261027)
    ap.add_argument("--manual", help="JSON {id_de_fila: patrón} de la pasada manual (fuera de git)")
    a = ap.parse_args(argv)
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    todas, por_fuente = [], {}
    for mod in FUENTES:
        filas, info = mod.convertir()
        por_fuente[mod.CORTO] = {"filas": len(filas), "reemplazos": info["reemplazos"]}
        if mod is not pqrs_enrutamiento:  # el «Asunto» de enrutamiento son ~200 rótulos fijos, sin datos personales
            todas.extend((mod.CORTO, f) for f in filas)
    total = collections.Counter()
    for v in por_fuente.values():
        total.update(v["reemplazos"])
    voc = vocabulario([f for _, f in todas])
    azar = random.Random(a.semilla).sample(todas, min(a.muestra, len(todas)))
    manual = {}
    if a.manual:
        with open(a.manual, encoding="utf-8") as fh:
            manual = json.load(fh)
    n_fuente = collections.Counter(c for c, _ in azar)
    filas_heur = collections.Counter()      # fuente -> filas con algún patrón (heurística)
    por_patron = collections.Counter()      # "fuente/patrón" -> filas
    filas_manual, por_patron_manual = collections.Counter(), collections.Counter()
    restos = collections.Counter()
    with open(salida / "contextos.txt", "w", encoding="utf-8") as fh:
        for corto, f in azar:
            ps = patrones(f["texto"], voc)
            if ps:
                filas_heur[corto] += 1
                for p in ps:
                    por_patron["%s/%s" % (corto, p)] += 1
                fh.write("%s [%s]: %s\n" % (f["id"], ",".join(sorted(ps)), f["texto"][:600]))
            if f["id"] in manual:
                filas_manual[corto] += 1
                por_patron_manual["%s/%s" % (corto, manual[f["id"]])] += 1
            if RE_DIGITOS.search(f["texto"]):
                restos["numero_6_digitos"] += 1
            if "@" in f["texto"]:
                restos["arroba"] += 1
    informe = {"reemplazos_total": dict(total), "por_fuente": por_fuente, "filas_texto_libre": len(todas),
               "muestra": len(azar), "muestra_por_fuente": dict(n_fuente),
               "heuristica_filas_con_nombre_por_fuente": dict(filas_heur), "heuristica_por_patron": dict(por_patron),
               "muestra_con_otros_restos": dict(restos)}
    if a.manual:
        informe.update(manual_filas_con_nombre_por_fuente=dict(filas_manual), manual_por_patron=dict(por_patron_manual),
                       manual_filas_con_nombre=sum(filas_manual.values()))
    with open(salida / "informe.json", "w", encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print(json.dumps(informe, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
