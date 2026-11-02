"""Traduce al español las filas del meta tsjev (tasksource-jev commercial) para reducir la brecha es/en de L2 (W10).

    python -m model.meta.traducir META SALIDA [--traductor opus|falso|auto] [--max-por-tarea 300] [--max-filas N]
        [--minutos M] [--semilla 0] [--revision-muestra 50]

`META` es el directorio del meta convertido (con `tsjev/<split>-NNNNN.jsonl.gz`). Se traducen `texto`, `pregunta` y
`descripciones`; los ids de `opciones`, `etiqueta`, `blanda`, `tipo`, `split` y `plantilla` quedan como están, de modo que la
fila nueva cae en el mismo split que la original (el test de tsjev sigue siendo test). Cada fila nueva lleva `idioma: "es"`,
`traducida: {modelo, revision, de}`, el id original con sufijo `:es` y la licencia original más la del traductor.

Salida: `SALIDA/tsjev-es/<split>-NNNNN.jsonl.gz`, `muestra-revision.md` y `resumen.json`.
Se elige un subconjunto determinista (hash de la semilla y del id) con tope por tarea y total, se deduplican los textos antes
de traducir, y se traduce por trozos de filas en ese orden: si se acaba `--minutos`, las filas que faltan se cuentan y no se
escriben. Las traducciones basura (vacía, idéntica, longitud fuera de [0,3; 3] o n-gramas repetidos) se descartan y se cuentan.

Traductores: `opus` = Helsinki-NLP/opus-mt-en-es (CC-BY-4.0, con atribución; se comprueba la licencia de la tarjeta);
`falso` = marcador determinista para pruebas en seco (modelo «FALSO:…»; nunca para entrenar); `auto` = opus si está en la caché.
"""
import argparse
import glob
import gzip
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

from .comun import Salida, hf_hub

MODELO_OPUS = "Helsinki-NLP/opus-mt-en-es"
LICENCIAS_TRADUCTOR = {"cc-by-4.0": "CC-BY-4.0", "apache-2.0": "Apache-2.0"}
LICENCIA_OPUS = "CC-BY-4.0 (Helsinki-NLP/opus-mt-en-es, OPUS-MT, atribución)"
FUENTE = "tsjev"
CORTO = "tsjev-es"
RATIO_MIN, RATIO_MAX = 0.3, 3.0
LARGO_MIN_RATIO = 15
MAX_TOK = 400  # tokens de entrada; lo que pase de aquí se trunca y suele caer en la heurística de longitud
TROZO_TOK = 200  # un texto con más tokens se parte por frases en trozos de ≤ TROZO_TOK, que se traducen por separado y se unen
MAX_POS = 512  # posiciones de Marian (opus-mt-en-es): ni la entrada ni la salida pueden pasar de aquí
TROZO_FILAS = 1000


# --- traductores ---------------------------------------------------------------------------------------------------
class TraductorFalso:
    """Determinista y marcado: antepone «[falso-es] ». Solo para pruebas en seco; su salida no sirve para entrenar."""
    modelo = "FALSO:marcador"
    revision = "falso"
    licencia = "ninguna (traductor falso de pruebas)"

    def traducir(self, textos):
        return ["[falso-es] " + t for t in textos]


class TraductorIdentidad:
    """Devuelve el texto tal cual (para probar la heurística de «idéntica»)."""
    modelo = "FALSO:identidad"
    revision = "falso"
    licencia = "ninguna (traductor falso de pruebas)"

    def traducir(self, textos):
        return list(textos)


def snapshot_modelo(modelo=MODELO_OPUS):
    d = hf_hub() / ("models--" + modelo.replace("/", "--")) / "snapshots"
    snaps = sorted(p for p in d.glob("*") if p.is_dir() and (p / "config.json").is_file()) if d.is_dir() else []
    return snaps[-1] if snaps else None


def licencia_tarjeta_modelo(snap):
    """`license:` de la cabecera YAML de la tarjeta del modelo, en minúsculas, o None."""
    r = Path(snap) / "README.md"
    if not r.is_file():
        return None
    m = re.search(r"^license:\s*([^\s#]+)", r.read_text(encoding="utf-8", errors="replace"), re.M | re.I)
    return m.group(1).strip("'\"").lower() if m else None


def trozos(texto, n_tok, tope=TROZO_TOK):
    """(trozos, frases truncadas): `texto` en trozos de ≤ `tope` tokens, cortando por frases (tras . ! ? … o salto de línea).
    Una frase sola de más de `tope` tokens va en su propio trozo y se cuenta como truncada (el tokenizador la corta)."""
    if n_tok(texto) <= tope:
        return [texto], 0
    frases = [f for f in re.split(r"(?<=[.!?…])\s+|\n+", texto) if f.strip()]
    out, actual, trunc = [], "", 0
    for f in frases:
        cand = (actual + " " + f).strip() if actual else f
        if actual and n_tok(cand) > tope:
            out.append(actual)
            actual = f
        else:
            actual = cand
        if n_tok(f) > tope:
            trunc += 1
    if actual:
        out.append(actual)
    return out, trunc


class TraductorOpus:
    """Opus-MT en→es con transformers (CPU o GPU). Revisión = nombre del snapshot de la caché de HF."""

    def __init__(self, modelo=MODELO_OPUS, device=None, lote=32, beams=2):
        snap = snapshot_modelo(modelo)
        if snap is None:
            raise FileNotFoundError("%s no está en %s" % (modelo, hf_hub()))
        lic = licencia_tarjeta_modelo(snap)
        if lic not in LICENCIAS_TRADUCTOR:
            raise ValueError("licencia de %s en su tarjeta: %r (se aceptan %s)" % (modelo, lic, sorted(LICENCIAS_TRADUCTOR)))
        import torch
        from transformers import AutoTokenizer, MarianMTModel
        self.modelo, self.revision, self.licencia = modelo, snap.name, "%s (%s)" % (LICENCIAS_TRADUCTOR[lic], modelo)
        self.tok = AutoTokenizer.from_pretrained(str(snap))
        self.mod = MarianMTModel.from_pretrained(str(snap)).eval()
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.mod.to(self.device)
        self.lote, self.beams, self.torch = lote, beams, torch

    def _traducir_cortos(self, textos):
        out = []
        for i in range(0, len(textos), self.lote):
            lote = textos[i:i + self.lote]
            enc = self.tok(lote, return_tensors="pt", padding=True, truncation=True, max_length=TROZO_TOK).to(self.device)
            with self.torch.inference_mode():   # la salida también cabe en las MAX_POS posiciones del decodificador
                gen = self.mod.generate(**enc, num_beams=self.beams, max_new_tokens=MAX_POS - 2, do_sample=False)
            out.extend(self.tok.batch_decode(gen, skip_special_tokens=True))
        return out

    def traducir(self, textos):
        """Los textos de más de TROZO_TOK tokens se parten por frases (`trozos`) y se unen tras traducir; cuenta en `partidas` las
        cadenas partidas y en `truncadas` las frases sueltas que aun así pasan de TROZO_TOK (esas sí se truncan)."""
        n_tok = lambda t: len(self.tok(t, add_special_tokens=False)["input_ids"])  # noqa: E731
        piezas, mapa = [], []
        for t in textos:
            tr, trunc = trozos(t, n_tok, TROZO_TOK)
            if len(tr) > 1:
                self.partidas = getattr(self, "partidas", 0) + 1
            self.truncadas = getattr(self, "truncadas", 0) + trunc
            mapa.append((len(piezas), len(tr)))
            piezas.extend(tr)
        trad = self._traducir_cortos(piezas)
        return [" ".join(trad[i:i + n]) for i, n in mapa]


def elegir_traductor(nombre, device=None):
    if nombre == "falso":
        return TraductorFalso()
    if nombre == "identidad":
        return TraductorIdentidad()
    if nombre == "auto" and snapshot_modelo() is None:
        print("AVISO: Opus-MT no está en la caché de HF; se usa el traductor FALSO (prueba en seco)", file=sys.stderr)
        return TraductorFalso()
    try:
        return TraductorOpus(device=device)
    except ImportError as e:  # p. ej. sin sentencepiece
        if nombre == "auto":
            print("AVISO: no se puede cargar Opus-MT (%s); se usa el traductor FALSO" % e, file=sys.stderr)
            return TraductorFalso()
        raise


# --- heurísticas de basura -------------------------------------------------------------------------------------------
def _palabras(s):
    return re.findall(r"\w+", s.lower())


def max_repeticion(s, n=3):
    """Veces que se repite el n-grama de palabras más frecuente."""
    p = _palabras(s)
    c = {}
    for i in range(len(p) - n + 1):
        g = tuple(p[i:i + n])
        c[g] = c.get(g, 0) + 1
    return max(c.values(), default=0)


def basura(original, traduccion, identica=True):
    """Motivo por el que una traducción es basura, o None: vacia | identica | longitud | repeticion."""
    if not isinstance(traduccion, str) or not traduccion.strip():
        return "vacia"
    o, t = original.strip(), traduccion.strip()
    if identica and o.casefold() == t.casefold():
        return "identica"
    if len(o) >= LARGO_MIN_RATIO and not RATIO_MIN <= len(t) / len(o) <= RATIO_MAX:  # en cadenas cortas la razón no dice nada
        return "longitud"
    if max_repeticion(t) >= 3 and max_repeticion(t) > max_repeticion(o):
        return "repeticion"
    return None


# --- selección de filas ------------------------------------------------------------------------------------------------
def _clave(semilla, id_):
    return hashlib.sha1(("%s|%s" % (semilla, id_)).encode("utf-8")).hexdigest()


def leer_meta(meta, corto=FUENTE):
    for ruta in sorted(glob.glob(str(Path(meta) / corto / "*.jsonl.gz"))):
        with gzip.open(ruta, "rt", encoding="utf-8") as f:
            for linea in f:
                if linea.strip():
                    yield json.loads(linea)


def seleccionar(meta, max_por_tarea=300, max_filas=None, semilla=0, info=None, mas_largas=0):
    """Filas a traducir, ordenadas por clave hash (determinista). Tope por tarea y total sobre ese orden."""
    info = info if info is not None else {}
    cont = lambda k: info.__setitem__(k, info.get(k, 0) + 1)  # noqa: E731
    por_tarea = {}
    for f in leer_meta(meta):
        cont("filas_leidas")
        if not f.get("uso_comercial"):
            cont("saltadas_no_comerciales")
        elif f.get("idioma") != "en":
            cont("saltadas_idioma_%s" % f.get("idioma"))
        else:
            por_tarea.setdefault(f["tarea"], []).append((_clave(semilla, f["id"]), f["id"], f))
    sel = []
    for tarea, lst in por_tarea.items():
        lst.sort(key=lambda x: x[:2])
        info["filas_recortadas_por_tarea"] = info.get("filas_recortadas_por_tarea", 0) + max(0, len(lst) - max_por_tarea)
        sel.extend(lst[:max_por_tarea])
    sel.sort(key=lambda x: x[:2])
    if max_filas is not None and len(sel) > max_filas:
        info["filas_recortadas_por_total"] = len(sel) - max_filas
        sel = sel[:max_filas]
    info["tareas_con_filas"] = len(por_tarea)
    if mas_largas:   # prueba dura: añade las `mas_largas` filas de texto más largo de todo el meta (que no estén ya)
        ya = {x[1] for x in sel}
        todas = sorted((x for lst in por_tarea.values() for x in lst if x[1] not in ya), key=lambda x: (-len(x[2]["texto"]), x[1]))
        sel.extend(todas[:mas_largas])
        info["filas_largas_anadidas"] = min(mas_largas, len(todas))
    return [x[2] for x in sel]


# --- traducción de una fila ---------------------------------------------------------------------------------------------
def textos_de(f):
    """Cadenas a traducir de una fila (las descripciones de `noul` se rehacen desde la pregunta)."""
    ts = [f["texto"], f["pregunta"]]
    if f["tipo"] != "noul":
        ts.extend(f["descripciones"][o] for o in f["opciones"])
    return ts


def construir(f, tr, trad, licencia_tr):
    """Fila nueva a partir de la original y un dict texto->traducción. Devuelve (fila, None) o (None, motivo)."""
    texto, pregunta = tr[f["texto"]], tr[f["pregunta"]]
    for orig, t in ((f["texto"], texto), (f["pregunta"], pregunta)):
        m = basura(orig, t)
        if m:
            return None, m
    if f["tipo"] == "noul":
        desc = {"false": "false: no (%s)" % pregunta, "true": "true: %s" % pregunta}
    else:
        desc = {}
        for o in f["opciones"]:
            t = tr[f["descripciones"][o]]
            m = basura(f["descripciones"][o], t, identica=False)  # un nombre propio o un número pueden coincidir
            if m:
                return None, m
            desc[o] = t
    g = dict(f)
    g.update(id=f["id"] + ":es", texto=texto, pregunta=pregunta, descripciones=desc, idioma="es",
             traducida={"modelo": trad.modelo, "revision": trad.revision, "de": "en"},
             licencia="%s; traducción: %s" % (f["licencia"], licencia_tr))
    return g, None


def traducir_filas(filas, trad, minutos=None, trozo=TROZO_FILAS, info=None):
    """Genera (original, nueva|None, motivo). Traduce por trozos de filas deduplicando textos; corta a los `minutos`."""
    info = info if info is not None else {}
    t0 = time.time()
    cache = {}
    for i in range(0, len(filas), trozo):
        if minutos is not None and (time.time() - t0) / 60 >= minutos:
            info["sin_traducir_por_tiempo"] = len(filas) - i
            return
        parte = filas[i:i + trozo]
        nuevos = sorted({t for f in parte for t in textos_de(f)} - cache.keys(), key=lambda s: (len(s), s))
        info["textos_unicos"] = info.get("textos_unicos", 0) + len(nuevos)
        info["textos_totales"] = info.get("textos_totales", 0) + sum(len(textos_de(f)) for f in parte)
        if nuevos:
            cache.update(zip(nuevos, trad.traducir(nuevos)))
        for f in parte:
            g, motivo = construir(f, cache, trad, getattr(trad, "licencia", "?"))
            yield f, g, motivo
        print("   %d/%d filas (%.0f s)" % (min(i + trozo, len(filas)), len(filas), time.time() - t0), flush=True)


# --- muestra de revisión ----------------------------------------------------------------------------------------------------
def escribir_muestra(ruta, pares, trad, semilla, n=50, descartes=None):
    """`pares`: lista de (original, nueva). Muestra al azar con semilla fija, en Markdown."""
    rnd = random.Random(semilla)
    idx = sorted(rnd.sample(range(len(pares)), min(n, len(pares))))
    L = ["# Muestra de revisión de tsjev-es", "",
         "Traductor: `%s` (revisión `%s`). Semilla %s. %d de %d pares aceptados." % (trad.modelo, trad.revision, semilla, len(idx), len(pares)),
         ""]
    if descartes:
        L += ["Descartadas por heurística: %s." % json.dumps(descartes, ensure_ascii=False, sort_keys=True), ""]
    if trad.modelo.startswith("FALSO"):
        L += ["**Traductor FALSO (prueba en seco): esta muestra no sirve para revisar la calidad.**", ""]
    for k, i in enumerate(idx, 1):
        o, g = pares[i]
        L += ["## %d. `%s` (%s, %s)" % (k, g["id"], o["tarea"], o["split"]), "",
              "- **pregunta:** %s" % o["pregunta"], "  - → %s" % g["pregunta"],
              "- **texto:** %s" % o["texto"].replace("\n", " ⏎ "), "  - → %s" % g["texto"].replace("\n", " ⏎ ")]
        for op in o["opciones"][:6]:
            if o["tipo"] != "noul":
                L.append("- opción `%s`: %s → %s" % (op, o["descripciones"][op], g["descripciones"][op]))
        L.append("- etiqueta: `%s`" % o["etiqueta"])
        L.append("")
    Path(ruta).write_text("\n".join(L) + "\n", encoding="utf-8")
    return len(idx)


# --- principal ----------------------------------------------------------------------------------------------------------------
def correr(meta, salida, trad, max_por_tarea=300, max_filas=None, minutos=None, semilla=0, n_muestra=50, trozo=TROZO_FILAS, mas_largas=0):
    t0 = time.time()
    info = {}
    filas = seleccionar(meta, max_por_tarea, max_filas, semilla, info, mas_largas)
    print("seleccionadas %d filas de %d tareas" % (len(filas), info.get("tareas_con_filas", 0)), flush=True)
    Path(salida).mkdir(parents=True, exist_ok=True)
    out = Salida(salida)
    descartes, pares, por_tarea = {}, [], {}
    for o, g, motivo in traducir_filas(filas, trad, minutos, trozo, info):
        if motivo:
            descartes[motivo] = descartes.get(motivo, 0) + 1
            continue
        out.anadir(CORTO, g)
        pares.append((o, g))
        por_tarea[g["tarea"]] = por_tarea.get(g["tarea"], 0) + 1
    out.cerrar()
    n_muestra = escribir_muestra(Path(salida) / "muestra-revision.md", pares, trad, semilla, n_muestra, descartes) if pares else 0
    res = out.resumen()
    res.update(
        traductor={"modelo": trad.modelo, "revision": trad.revision, "licencia": getattr(trad, "licencia", None)},
        cadenas_partidas=getattr(trad, "partidas", 0), frases_truncadas=getattr(trad, "truncadas", 0),
        filas_por_tarea=dict(sorted(por_tarea.items())), descartadas_heuristica=descartes,
        descartadas_total=sum(descartes.values()), filas_seleccionadas=len(filas), filas_escritas=len(pares),
        pares_en_muestra=n_muestra, info=info, max_por_tarea=max_por_tarea, max_filas=max_filas, semilla=semilla,
        minutos_tope=minutos, segundos=round(time.time() - t0, 1))
    (Path(salida) / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return res


def crear_fixture(destino, tareas=3, por_tarea=40):
    """Meta tsjev inventado (sin datos reales) con las tres clases de tipo y los tres splits, para pruebas en seco."""
    out = Salida(destino)
    n = {}
    for t in range(tareas):
        for i in range(por_tarea):
            split = ("train", "train", "train", "dev", "test")[i % 5]
            tipo = ("choice", "score", "noul")[(t + i) % 3]
            q = "Is this text about topic %d?" % t
            if tipo == "noul":
                ops, desc, et = ["false", "true"], {"false": "false: not (%s)" % q, "true": "true: " + q}, "true"
            elif tipo == "score":
                ops = ["1", "2", "3"]
                desc = {"1": "very bad", "2": "so-so", "3": "very good"}
                et = "3"
            else:
                ops = ["red", "green", "blue"]
                desc = {o: o for o in ops}
                et = "green"
            k = n[split] = n.get(split, -1) + 1
            out.anadir(FUENTE, {
                "id": "tsjev:%s:%d" % (split, k), "split": split, "uso_comercial": True, "tarea": "demo/t%d" % t, "tipo": tipo,
                "pregunta": q, "texto": "Invented sample text number %d about the weather and the sea." % (t * 1000 + i),
                "opciones": ops, "descripciones": desc, "etiqueta": et, "blanda": {o: 1.0 if o == et else 0.0 for o in ops},
                "idioma": "en", "fuente": "tasksource/tasksource-jev-typed-decisions:demo/t%d %s" % (t, split), "licencia": "mit",
                "plantilla": "p%d-%s-%d" % (t, split, i // 10)})
    out.cerrar()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("meta")
    ap.add_argument("salida", nargs="?")
    ap.add_argument("--traductor", default="auto", choices=("auto", "opus", "falso", "identidad"))
    ap.add_argument("--max-por-tarea", type=int, default=300)
    ap.add_argument("--max-filas", type=int, default=None)
    ap.add_argument("--minutos", type=float, default=None, help="tope de traducción; lo que falte se cuenta y no se escribe")
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--device", default=None)
    ap.add_argument("--mas-largas", type=int, default=0, help="añade las N filas de texto más largo del meta (prueba dura)")
    ap.add_argument("--crear-fixture", action="store_true", help="escribe un meta tsjev inventado en META y sale")
    a = ap.parse_args(argv)
    if a.crear_fixture:
        crear_fixture(a.meta)
        return 0
    if not a.salida:
        ap.error("falta SALIDA")
    trad = elegir_traductor(a.traductor, a.device)
    print("traductor: %s revisión %s" % (trad.modelo, trad.revision), flush=True)
    res = correr(a.meta, a.salida, trad, a.max_por_tarea, a.max_filas, a.minutos, a.semilla, mas_largas=a.mas_largas)
    print(json.dumps({k: v for k, v in res.items() if k in (
        "filas_escritas", "descartadas_heuristica", "filas_seleccionadas", "segundos", "traductor")}, ensure_ascii=False, indent=1))
    if res["filas_escritas"] == 0:
        print("FALLO: ninguna fila traducida", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
