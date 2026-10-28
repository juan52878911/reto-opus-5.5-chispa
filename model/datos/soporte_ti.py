"""tasksource/it-support-tickets: `soporte_ti`, `choice` de 7 categorías. Tickets reales de una empresa brasileña, ya
sin datos personales (marcas `[NAME]`, `[TICKET ID]`…); el texto va en inglés, alemán, portugués o español.

`idioma` se estima con palabras vacías (en/de/pt/es; sin señal clara queda «en», la lengua mayoritaria). Se juntan los
dos splits de origen y se reparte 80/10/10 por plantilla (texto sin números ni marcas), estratificado por categoría.
"""
import re
from pathlib import Path

from .comun import leer_split, raiz_hf, fila, SPLITS
from .libres import licencia_estricta, normalizar, reparto_estratificado

REPO = "tasksource/it-support-tickets"
CORTO = "soporte-ti"
NOMBRES = ["Active Directory", "Computer-Services", "EOL", "Fileservice", "O365", "Software", "Support general"]  # orden del ClassLabel
OPCIONES = ["active_directory", "computer_services", "eol", "fileservice", "o365", "software", "support_general"]
DESCRIPCIONES = {
    "active_directory": "cuentas, usuarios, contraseñas y permisos de Active Directory",
    "computer_services": "servicios de equipos: ordenadores, periféricos, impresoras y red",
    "eol": "equipos o software al final de su vida útil (EOL) y su sustitución o baja",
    "fileservice": "acceso a carpetas, unidades y recursos compartidos de archivos",
    "o365": "Office 365: correo, Teams, OneDrive y SharePoint",
    "software": "instalación, licencias o fallos de programas",
    "support_general": "soporte general que no encaja en las demás categorías",
}
PREGUNTA = "¿A qué categoría de soporte de TI pertenece el ticket?"
VACIAS = {
    "en": "the and to for of is on with please you your we are not have be this that from can will".split(),
    "de": "der die das und ist nicht mit ein eine für bitte auf zu den von wir ich sie".split(),
    "pt": "o a os as de do da em um uma para por com não que você preciso favor obrigado e".split(),
    "es": "el la los las de del en un una para por con no que su favor gracias necesito y".split(),
}


def idioma_de(texto):
    pal = re.findall(r"[a-zà-ÿ]+", texto.lower())
    puntos = {l: sum(p in set(v) for p in pal) for l, v in VACIAS.items()}
    mejor = max(puntos, key=lambda l: (puntos[l], l == "en"))
    return mejor if puntos[mejor] else "en"


def _plantilla(texto):
    t = re.sub(r"\[[^\]]*\]|\d+", "#", texto.lower())
    return "ti-" + re.sub(r"\W+", "", normalizar(t))[:40]


def convertir(raiz=None):
    raiz = Path(raiz or raiz_hf(REPO))
    lic, com = licencia_estricta(raiz, ("cc-by-4.0",), "cc-by-4.0")
    reg, grupos = [], {}
    for origen in ("train", "test"):
        for r in leer_split(raiz, origen, "data"):
            t = (r["text"] or "").strip()
            if not t:
                continue
            e = OPCIONES[int(r["label"])]
            p = _plantilla(t)
            reg.append((t, e, p, origen))
            g = grupos.setdefault(p, [e, 0])
            g[1] += 1
    split_de = reparto_estratificado([(p, g[0], g[1]) for p, g in grupos.items()], sal=CORTO)
    cont, filas = {}, []
    for t, e, p, origen in reg:
        sp = split_de[p]
        n = cont.get(sp, 0)
        cont[sp] = n + 1
        f = fila(CORTO, sp, n, tarea="soporte_ti", tipo="choice", pregunta=PREGUNTA, texto=t, opciones=OPCIONES,
                 descripciones=DESCRIPCIONES, etiqueta=e, idioma=idioma_de(t), fuente="%s %s" % (REPO, origen),
                 licencia=lic, uso_comercial=com, plantilla=p)
        filas.append(f)
    idiomas = {}
    for f in filas:
        idiomas[f["idioma"]] = idiomas.get(f["idioma"], 0) + 1
    return filas, {"licencia": lic, "idiomas": idiomas, "categorias_origen": NOMBRES}
