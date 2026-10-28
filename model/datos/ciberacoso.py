"""Ciberacoso en español colombiano (FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1 y _2): `ciberacoso`, `noul`.

Tuits etiquetados a mano (MIT). Se juntan los dos conjuntos, se quitan los repetidos (entre y dentro de ellos), se
sustituyen las @menciones por «@usuario» y no se guarda el autor. Reparto 80/10/10 por hash del texto.
"""
import re
from pathlib import Path

from .comun import FuenteAusente, fila, leer_tabla, raiz_hf, split_por_clave
from .libres import licencia_estricta, normalizar

REPOS = ("FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_1", "FelipeGuerra/Colombian_Spanish_Cyberbullying_Dataset_2")
CORTO = "ciberacoso"
PREGUNTA = "¿El tuit es ciberacoso (insulto, amenaza, maldición o difamación dirigidos a alguien)?"
DESCRIPCIONES = {
    "false": "no es ciberacoso: puede traer groserías de uso coloquial, pero sin atacar a una persona",
    "true": "ciberacoso: insulta, amenaza, desea mal o difama a una persona",
}


def convertir(raiz=None):
    """`raiz` (fixtures) = carpeta con subcarpetas `d1` y `d2`; si no, las dos de ~/hf."""
    if raiz:
        raices = [Path(raiz) / "d1", Path(raiz) / "d2"]
    else:
        raices = [raiz_hf(r) for r in REPOS]
    cont, filas, vistos, dup, malas, lics = {}, [], set(), 0, 0, []
    for repo, rz in zip(REPOS, raices):
        lic, com = licencia_estricta(rz, ("mit",), "mit")
        lics.append(lic)
        csvs = sorted(rz.glob("*.csv"))
        if not csvs:
            raise FuenteAusente(repo)
        for r in leer_tabla(csvs[0]):
            etq = (r.get("ciberacoso") or "").strip()
            t = re.sub(r"@\w+", "@usuario", (r.get("texto") or "").strip())
            if etq not in ("0", "1", "0.0", "1.0") or not t:
                malas += 1
                continue
            k = normalizar(t)
            if k in vistos:
                dup += 1
                continue
            vistos.add(k)
            split = split_por_clave(k, 0.1, 0.1, CORTO)
            n = cont.get(split, 0)
            cont[split] = n + 1
            filas.append(fila(CORTO, split, n, tarea="ciberacoso", tipo="noul", pregunta=PREGUNTA, texto=t,
                              opciones=["false", "true"], descripciones=DESCRIPCIONES, etiqueta="true" if etq[0] == "1" else "false",
                              idioma="es-CO", fuente=repo, licencia=lic, uso_comercial=com))
    return filas, {"licencias": lics, "repetidas_descartadas": dup, "sin_etiqueta_valida": malas}
