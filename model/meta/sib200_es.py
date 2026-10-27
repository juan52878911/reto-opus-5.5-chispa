"""SIB-200 `spa_Latn` (Davlan/sib200) -> tema del texto, `choice` de 7 clases.

Licencia: la tarjeta declara cc-by-sa-4.0 (y «CC 4.0 Commercial» en el texto); se da por buena solo si la
tarjeta lo sigue diciendo.
"""
import csv

from .comun import Numerador, licencia_tarjeta, raiz_hf

REPO = "Davlan/sib200"
CORTO = "sib200"
PREGUNTA = "¿Sobre qué tema trata el texto?"
DESCRIPCIONES = {
    "science/technology": "ciencia o tecnología: descubrimientos, investigación, aparatos, informática",
    "travel": "viajes: destinos, transporte, alojamiento, turismo",
    "politics": "política: gobiernos, elecciones, leyes, relaciones entre países",
    "sports": "deportes: competiciones, equipos, atletas, resultados",
    "health": "salud: medicina, enfermedades, bienestar, nutrición",
    "entertainment": "entretenimiento: cine, música, televisión, espectáculos, famosos",
    "geography": "geografía: lugares, relieve, clima, países, ciudades",
}
OPCIONES = list(DESCRIPCIONES)
SPLIT_ORIGEN = {"train": "train", "dev": "dev", "test": "test"}
LICENCIAS_OK = ("cc-by-sa-4.0",)


def _tsv(ruta):
    # Sin comillas: los textos pueden llevar «"» sueltas y el lector por defecto se comería líneas.
    with open(ruta, encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)


def filas(raiz=None, info=None, tope=None):
    raiz = raiz or raiz_hf(REPO)
    info = info if info is not None else {}
    leida = licencia_tarjeta(raiz)
    com = leida in LICENCIAS_OK
    lic = "cc-by-sa-4.0" if com else "sin verificar (tarjeta: %s; se esperaba cc-by-sa-4.0)" % (leida or "sin licencia")
    info["licencia"] = lic
    etiquetas = (raiz / "data" / "spa_Latn" / "labels.txt").read_text(encoding="utf-8").split()
    if sorted(etiquetas) != sorted(OPCIONES):
        raise ValueError("SIB-200 spa_Latn: las clases de labels.txt no son las 7 esperadas: %s" % etiquetas)
    num = Numerador(CORTO)
    emitidas = 0
    for split, nombre in SPLIT_ORIGEN.items():
        for r in _tsv(raiz / "data" / "spa_Latn" / (nombre + ".tsv")):
            if tope is not None and emitidas >= tope:
                return
            texto, cat = (r.get("text") or "").strip(), r.get("category")
            if not texto or cat not in DESCRIPCIONES:
                info["descartadas_invalidas"] = info.get("descartadas_invalidas", 0) + 1
                continue
            f = num.numerar(split, dict(
                tarea="tema", tipo="choice", pregunta=PREGUNTA, texto=texto, opciones=OPCIONES,
                descripciones=DESCRIPCIONES, etiqueta=cat, idioma="es",
                fuente="%s spa_Latn %s" % (REPO, nombre), licencia=lic), com)
            if f is None:
                continue
            emitidas += 1
            yield f
    info["descartadas_licencia_nc_fuera_de_test"] = num.descartadas_nc


def convertir(raiz=None, **kw):
    info = {}
    return list(filas(raiz, info, **kw)), info
