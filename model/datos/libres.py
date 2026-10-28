"""Ayudas comunes de los conversores de datos de libre uso (T1.1c): licencia estricta, reparto y duplicados."""
import collections
import re
import unicodedata

from .comun import bucket, licencia_fuente, split_por_clave, tarjeta  # noqa: F401  (tarjeta: reexportada)

RE_CC_NC = re.compile(r"cc[-\s]?by[-\s]?nc", re.I)
RE_NC_EN_LINEA = re.compile(r"[-\s]nc[-\s]|non[-\s]?commercial|no[-\s]?comercial", re.I)  # solo en líneas que hablan de licencia
RAZONES_DUDOSA = "contradictoria"


def licencia_estricta(raiz, esperadas, canonica, comercial=True):
    """Como `comun.licencia_fuente`, pero además lee el cuerpo de los README: si la cabecera YAML dice una
    licencia libre y el texto de la tarjeta menciona NC, la licencia queda «contradictoria» y `uso_comercial=False`.
    """
    lic, com = licencia_fuente(raiz, esperadas, canonica, comercial)
    if not com:
        return lic, com
    from pathlib import Path
    for rd in sorted(Path(raiz).glob("README*.md")):
        cuerpo = rd.read_text(encoding="utf-8")
        cuerpo = re.sub(r"^---\n.*?\n---", "", cuerpo, count=1, flags=re.S)
        cuerpo = re.sub(r"<!--.*?-->", "", cuerpo, flags=re.S)  # las plantillas HTML no cuentan
        if RE_CC_NC.search(cuerpo) or any(RE_NC_EN_LINEA.search(l) for l in cuerpo.splitlines() if "licen" in l.lower()):
            return "%s (cabecera %s) pero el texto de la tarjeta dice NC: licencia no clara" % (RAZONES_DUDOSA, canonica), False
    return lic, com


def normalizar(texto):
    """Clave de duplicado: sin acentos, en minúsculas y con espacios colapsados."""
    t = unicodedata.normalize("NFD", texto.casefold())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def sin_duplicados(filas, clave):
    """(filas únicas por `clave(fila)`, nº descartadas); se queda con la primera aparición."""
    vistos, out = set(), []
    for r in filas:
        k = clave(r)
        if k in vistos:
            continue
        vistos.add(k)
        out.append(r)
    return out, len(filas) - len(out)


def reparto_estratificado(grupos, p_dev=0.1, p_test=0.1, sal=""):
    """Reparto 80/10/10 por filas dentro de cada estrato, sin partir los grupos de duplicados.

    `grupos`: iterable de (clave_grupo, estrato, n_filas). Dentro de cada estrato los grupos se ordenan por un
    hash fijo (semilla = `sal`) y el primer `p_test` de las filas va a test, el siguiente `p_dev` a dev y el resto
    a train. Si un estrato de 2+ grupos se quedaría sin test (o de 3+ sin dev), el primer grupo (o el segundo) pasa
    a ese split, para que ningún tipo raro falte en test. Devuelve {clave_grupo: split}; un estrato de 1 grupo va a train.
    """
    por_estrato = collections.defaultdict(list)
    for clave, estrato, n in grupos:
        por_estrato[estrato].append((bucket(clave, sal), str(clave), n))
    out = {}
    for estrato, gs in por_estrato.items():
        gs.sort()
        total = float(sum(n for _, _, n in gs))
        antes = 0
        asignado = []
        for _, clave, n in gs:
            p = (antes + n / 2.0) / total
            out[clave] = "test" if p < p_test else "dev" if p < p_test + p_dev else "train"
            asignado.append(clave)
            antes += n
        if len(gs) >= 2 and "test" not in {out[c] for c in asignado}:
            out[asignado[0]] = "test"
        if len(gs) >= 3 and "dev" not in {out[c] for c in asignado}:
            out[asignado[1]] = "dev"
    return out
