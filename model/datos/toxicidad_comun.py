"""Lectura común de los corpus de toxicidad de bgonzalezbustamante (tuits anotados por dos codificadores).

Ojo con `consensus`: NO es la etiqueta, es una marca de acuerdo entre `coder_1` y `coder_2` (vale 1 si coinciden;
las filas con ambos en 1 pueden venir como NA). La etiqueta es la de los codificadores cuando coinciden; las filas
con desacuerdo se descartan (se cuentan en `info`).
"""
from pathlib import Path

from .comun import fila, raiz_hf, split_por_clave
from .libres import licencia_estricta

PREGUNTA = "¿El mensaje es tóxico (insulta, ataca o amenaza) a una persona o a un grupo?"
DESCRIPCIONES = {
    "false": "mensaje civilizado: puede ser crítico o duro con las ideas, pero sin insultos ni ataques personales",
    "true": "mensaje tóxico: insulta, humilla, amenaza o ataca a una persona o a un grupo",
}


def convertir_toxicidad(raiz, repo, corto, fichero, variedad_de, raiz_defecto=None):
    raiz = Path(raiz or raiz_hf(repo))
    from .comun import leer_tabla
    lic, com = licencia_estricta(raiz, ("cc-by-4.0",), "cc-by-4.0")
    cont, filas, desacuerdo, dup, vistos = {}, [], 0, 0, set()
    for r in leer_tabla(raiz / fichero):
        c1, c2 = r["coder_1"].strip(), r["coder_2"].strip()
        if c1 not in ("0", "1") or c2 not in ("0", "1") or c1 != c2:
            desacuerdo += 1
            continue
        texto = r["text"].strip()
        if not texto or texto in vistos:
            dup += 1
            continue
        vistos.add(texto)
        split = split_por_clave(r["id_obs"], 0.1, 0.1, corto)
        n = cont.get(split, 0)
        cont[split] = n + 1
        f = fila(corto, split, n, tarea="toxicidad", tipo="noul", pregunta=PREGUNTA, texto=texto,
                 opciones=["false", "true"], descripciones=DESCRIPCIONES, etiqueta="true" if c1 == "1" else "false",
                 idioma="es", fuente=repo, licencia=lic, uso_comercial=com)
        f["anotadores"] = 2
        f["blanda"] = {"false": 1.0 if c1 == "0" else 0.0, "true": 1.0 if c1 == "1" else 0.0}
        v = variedad_de(r)
        if v:
            f["variedad"] = v
        filas.append(f)
    total = len(filas) + desacuerdo + dup
    return filas, {"licencia": lic, "desacuerdo_descartadas": desacuerdo, "duplicadas_descartadas": dup,
                   "acuerdo_codificadores": round(1 - desacuerdo / float(total), 3) if total else None,
                   "nota": "`consensus` es una marca de acuerdo, no la etiqueta; etiqueta = codificadores coincidentes"}
