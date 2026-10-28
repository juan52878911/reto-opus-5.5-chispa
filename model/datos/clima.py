"""somosnlp/spa_climate_detection (BERTIN-ClimID): `clima`, `noul` (true = habla de cambio climático o sostenibilidad).

Licencia: la cabecera YAML dice cc-by-4.0, pero el cuerpo de la tarjeta dice cc-by-nc-sa-4.0 («por herencia de los datos»).
Se toma la restrictiva: `uso_comercial=false`, así que TODAS las filas van a `test` (solo sirven para evaluar).
Si la tarjeta algún día se corrige y confirma una licencia libre, se reparte 80/10/10 por hash del texto.
"""
from pathlib import Path

from .comun import fila, leer_tabla, raiz_hf, split_por_clave
from .libres import licencia_estricta, normalizar

REPO = "somosnlp/spa_climate_detection"
CORTO = "clima"
PREGUNTA = "¿El texto trata de cambio climático, medio ambiente o sostenibilidad?"
DESCRIPCIONES = {
    "false": "el texto no tiene relación con el clima ni con la sostenibilidad",
    "true": "el texto trata de cambio climático, medio ambiente o sostenibilidad",
}


def convertir(raiz=None):
    raiz = Path(raiz or raiz_hf(REPO))
    lic, com = licencia_estricta(raiz, ("cc-by-4.0",), "cc-by-4.0")
    cont, filas, vistos, dup = {}, [], set(), 0
    for p in sorted((raiz / "csv").glob("*.csv")):
        for r in leer_tabla(p):
            t = (r["question"] or "").strip()
            k = normalizar(t)
            if r["answer"] not in ("0", "1") or not k or k in vistos:
                dup += 1
                continue
            vistos.add(k)
            split = split_por_clave(k, 0.1, 0.1, CORTO) if com else "test"
            n = cont.get(split, 0)
            cont[split] = n + 1
            filas.append(fila(CORTO, split, n, tarea="clima", tipo="noul", pregunta=PREGUNTA, texto=t, opciones=["false", "true"],
                              descripciones=DESCRIPCIONES, etiqueta="true" if r["answer"] == "1" else "false", idioma="es",
                              fuente="%s %s" % (REPO, p.name), licencia=lic, uso_comercial=com))
    return filas, {"licencia": lic, "repetidas_o_invalidas": dup,
                   "nota": "licencia contradictoria (YAML libre, texto NC-SA): todo a test" if not com else ""}
