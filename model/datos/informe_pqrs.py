"""Informe de la anonimización de PQRS (T1.1c): `python -m model.datos.informe_pqrs --salida /tmp/pqrs-informe`.

Convierte las cuatro fuentes de datos.gov.co, suma los reemplazos por tipo y, en 100 filas al azar (semilla fija),
cuenta (sobre las tres fuentes de texto libre) cuántas AÚN parecen tener un nombre (heurística `anonimizar.sospechosas`). Escribe `informe.json` con solo
cifras y, aparte, `sospechosas.txt` con las palabras marcadas de esas filas para la revisión a mano (en /tmp, nunca en git).
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--salida", required=True)
    ap.add_argument("--muestra", type=int, default=100)
    a = ap.parse_args(argv)
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    todas, por_fuente = [], {}
    for mod in FUENTES:
        filas, info = mod.convertir()
        por_fuente[mod.CORTO] = {"filas": len(filas), "reemplazos": info["reemplazos"]}
        if mod is not pqrs_enrutamiento:  # el «Asunto» de enrutamiento son ~200 rótulos fijos, sin datos personales
            todas.extend(filas)
    total = collections.Counter()
    for v in por_fuente.values():
        total.update(v["reemplazos"])
    voc = vocabulario(todas)
    azar = random.Random(20261027).sample(todas, min(a.muestra, len(todas)))
    marcadas, restos = 0, collections.Counter()
    with open(salida / "sospechosas.txt", "w", encoding="utf-8") as fh:
        for f in azar:
            s = anonimizar.sospechosas(f["texto"], voc)
            if s:
                marcadas += 1
                fh.write("%s: %s\n" % (f["id"], " ".join(s)))
            if RE_DIGITOS.search(f["texto"]):
                restos["numero_6_digitos"] += 1
            if "@" in f["texto"]:
                restos["arroba"] += 1
    informe = {"reemplazos_total": dict(total), "por_fuente": por_fuente, "filas_texto_libre": len(todas),
               "muestra": len(azar), "muestra_con_nombre_aparente": marcadas, "muestra_con_otros_restos": dict(restos)}
    with open(salida / "informe.json", "w", encoding="utf-8") as fh:
        json.dump(informe, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print(json.dumps(informe, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
