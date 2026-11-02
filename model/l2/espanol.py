"""M4, español frente a inglés en L2: exactitud y macro-F1 en las tareas que existen en los dos idiomas, con el mismo esquema y el mismo
número de casos, y la diferencia es − en con IC95.

    python -m model.l2.espanol --ckpt mejor.pt --salida DIR [--hf ~/hf/hub] [--max-filas 500] [--boot 1000]

Pares (mismo contenido en los dos idiomas, unidos por id; el esquema, esto es pregunta, ids y descripciones, es el mismo en español para
los dos lados, así que solo cambia el idioma del mensaje): massive (es/en, test), xnli (es/en, test; CC-BY-NC, solo se evalúa),
sib200 (spa_Latn/eng_Latn, test) y paws-x (es/en, test). Un par al que le falte un lado en la caché de HF queda en `no_medido`.
M4 ampliado (v3): MASSIVE es/en ya estaba; se añade MMMLU ES_LA (`openai/MMMLU`, `test/mmlu_ES-LA.csv`) emparejado por posición con el MMLU
original (`cais/mmlu`, `all/test-*.parquet`): un par solo vale si coinciden la materia y la letra correcta (MMMLU traduce el test de MMLU en el
mismo orden; si menos del 95 % coincide, no hay pareja). Sin pareja en inglés, MMMLU se mide solo en español (`solo_es` en el JSON), marcado
«sin pareja en inglés» y fuera de la media es − en. Aquí las opciones son contenido, no esquema: `texto` es la pregunta y las descripciones de A-D
son el texto de cada opción en el idioma de la fila. Solo se mide, nunca se entrena.
L2 va sin soporte (k = 0). IC95 = bootstrap emparejado por caso (B remuestreos, semilla fija); la media entre tareas remuestrea cada tarea.
Si la diferencia pasa de 3 puntos (en exactitud o en macro-F1, en la media o en alguna tarea), `plan.md` prepara el reentrenamiento sin
lanzarlo: fuentes en español de licencia comercial (licencia leída de la tarjeta de HF en la caché), tamaño, cambios en
`model/l2/aws/general.sh` y coste de GPU en g5.
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

UMBRAL_PUNTOS = 3.0
SEMILLA = 0
G5_USD_H = 1.01   # g5.xlarge bajo demanda, el de general.sh

PREGUNTA_SIB = "¿De qué tema trata el texto?"
DESC_SIB = {"science/technology": "ciencia o tecnología", "travel": "viajes y turismo", "politics": "política",
            "sports": "deportes", "health": "salud y medicina", "entertainment": "entretenimiento, cine, música o famosos",
            "geography": "geografía y lugares"}
PREGUNTA_PAWS = "¿Las dos frases significan lo mismo?"
DESC_PAWS = {"false": "las frases dicen cosas distintas, aunque usen casi las mismas palabras", "true": "las frases son paráfrasis una de otra"}

# fuentes candidatas del plan de reentrenamiento: (repo de HF, para qué, filas aprox. que se usarían, `uso` si no entra en train)
FUENTES_PLAN = (
    ("SINAI/ALIA-es-discriminative-hate-speech", "toxicidad/odio en español", 8000, "train"),
    ("Multilingual-Perspectivist-NLU/MultiPICo", "ironía en español (perspectivista)", 6000, "train"),
    ("bgonzalezbustamante/toxicity-Constitution-ES", "toxicidad en español", 4000, "train"),
    ("bgonzalezbustamante/toxicity-protests-ES", "toxicidad en español (protestas)", 4000, "train"),
    ("google-research-datasets/paws-x", "paráfrasis es/en (noul)", 49000, "train"),
    ("Davlan/sib200", "tema es/en (7 clases)", 700, "train"),
    ("(PQRS propios)", "PQRS en español colombiano", 0, "solo test"),
)


# ------------------------------------------------------------------ carga de pares
def _snap(hf, repo):
    d = Path(hf) / ("datasets--" + repo.replace("/", "--")) / "snapshots"
    s = sorted(p for p in d.glob("*") if p.is_dir()) if d.is_dir() else []
    return s[-1] if s else None


def _tabla(ruta):
    from model.datos.comun import leer_tabla
    return leer_tabla(ruta) if Path(ruta).exists() else None


def _fila(par, i, tarea, tipo, pregunta, texto, ops, desc, et, idioma):
    return {"id": "%s:%s:%s" % (par, idioma, i), "tarea": tarea, "tipo": tipo, "pregunta": pregunta, "texto": texto, "opciones": list(ops),
            "descripciones": desc, "etiqueta": et, "idioma": idioma, "split": "test"}


def par_massive(hf):
    from model.datos import massive as M
    r = _snap(hf, M.REPO)
    es, en = (r and _tabla(r / "test" / "es.json.gz")), (r and _tabla(r / "test" / "en.json.gz"))
    if not es or not en:
        return None, "massive: falta test/es.json.gz o test/en.json.gz en la caché de HF"
    ops = sorted(M.DESCRIPCIONES)
    d_en = {x["id"]: x for x in en}
    par = []
    for x in es:
        y = d_en.get(x["id"])
        if y is None or x["label_text"] != y["label_text"] or x["label_text"] not in M.DESCRIPCIONES:
            continue
        par.append((_fila("massive", x["id"], "intencion", "choice", M.PREGUNTA, x["text"], ops, M.DESCRIPCIONES, x["label_text"], "es"),
                    _fila("massive", x["id"], "intencion", "choice", M.PREGUNTA, y["text"], ops, M.DESCRIPCIONES, y["label_text"], "en")))
    return par, None


def par_xnli(hf):
    from model.datos import xnli as X
    r = _snap(hf, X.REPO)
    es = r and _tabla(next(iter(sorted((r / "es").glob("test-*.parquet"))), r / "no"))
    en = r and _tabla(next(iter(sorted((r / "en").glob("test-*.parquet"))), r / "no"))
    if not es or not en or len(es) != len(en):
        return None, "xnli: falta es/test o en/test (o no coinciden en longitud) en la caché de HF"
    par = []
    for i, (x, y) in enumerate(zip(es, en)):
        if x["label"] != y["label"]:
            continue
        et = X.OPCIONES[int(x["label"])]
        par.append((_fila("xnli", i, "nli", "choice", X.PREGUNTA, "Premisa: %s\nHipótesis: %s" % (x["premise"], x["hypothesis"]), X.OPCIONES, X.DESCRIPCIONES, et, "es"),
                    _fila("xnli", i, "nli", "choice", X.PREGUNTA, "Premisa: %s\nHipótesis: %s" % (y["premise"], y["hypothesis"]), X.OPCIONES, X.DESCRIPCIONES, et, "en")))
    return par, None


def par_sib200(hf):
    r = _snap(hf, "Davlan/sib200")
    es = r and _tabla(r / "data" / "spa_Latn" / "test.tsv")
    en = r and _tabla(r / "data" / "eng_Latn" / "test.tsv")
    if not es or not en:
        return None, "sib200: falta data/spa_Latn/test.tsv o data/eng_Latn/test.tsv en la caché de HF"
    ops = sorted(DESC_SIB)
    d_en = {y["index_id"]: y for y in en}
    par = []
    for x in es:
        y = d_en.get(x["index_id"])
        if y is None or x["category"] != y["category"] or x["category"] not in DESC_SIB:
            continue
        par.append((_fila("sib200", x["index_id"], "tema", "choice", PREGUNTA_SIB, x["text"], ops, DESC_SIB, x["category"], "es"),
                    _fila("sib200", x["index_id"], "tema", "choice", PREGUNTA_SIB, y["text"], ops, DESC_SIB, y["category"], "en")))
    return par, None


def par_paws(hf):
    r = _snap(hf, "google-research-datasets/paws-x")
    es = r and _tabla(next(iter(sorted((r / "es").glob("test-*.parquet"))), r / "no"))
    en = r and _tabla(next(iter(sorted((r / "en").glob("test-*.parquet"))), r / "no"))
    if not es or not en:
        return None, "paws-x: falta es/test o en/test en la caché de HF"
    d_en = {y["id"]: y for y in en}
    par = []
    for x in es:
        y = d_en.get(x["id"])
        if y is None or x["label"] != y["label"]:
            continue
        et = "true" if int(x["label"]) == 1 else "false"
        par.append((_fila("paws", x["id"], "parafrasis", "noul", PREGUNTA_PAWS, "Frase 1: %s\nFrase 2: %s" % (x["sentence1"], x["sentence2"]), ["false", "true"], DESC_PAWS, et, "es"),
                    _fila("paws", x["id"], "parafrasis", "noul", PREGUNTA_PAWS, "Frase 1: %s\nFrase 2: %s" % (y["sentence1"], y["sentence2"]), ["false", "true"], DESC_PAWS, et, "en")))
    return par, None


PREGUNTA_MMLU = "¿Cuál es la respuesta correcta?"
MIN_COINCIDE_MMLU = 0.95


def _filas_mmmlu(hf):
    """-> (filas del MMMLU ES_LA, motivo si faltan). Cada una lleva `_materia` y `_pos` (posición en el fichero) para emparejar."""
    r = _snap(hf, "openai/MMMLU")
    ruta = next(iter(sorted(r.glob("**/mmlu_ES*LA*.csv"))), None) if r else None
    if ruta is None:
        return None, "mmmlu: falta test/mmlu_ES-LA.csv de openai/MMMLU en la caché de HF"
    out = []
    for i, x in enumerate(_tabla(ruta) or []):
        if x.get("Answer") not in ("A", "B", "C", "D") or not all(str(x.get(k, "")).strip() for k in ("Question", "A", "B", "C", "D")):
            continue
        f = _fila("mmmlu", i, "conocimiento", "choice", PREGUNTA_MMLU, str(x["Question"]).strip(), "ABCD",
                  {k: str(x[k]).strip() for k in "ABCD"}, x["Answer"], "es")
        f["_materia"], f["_pos"] = str(x.get("Subject", "")), i
        out.append(f)
    return out, (None if out else "mmmlu: el fichero no trae filas válidas (columnas esperadas: Question, A, B, C, D, Answer, Subject)")


def _filas_mmlu_en(hf):
    """-> {posición: (materia, letra, pregunta, opciones)} del MMLU original `cais/mmlu` (config all, test), o None."""
    r = _snap(hf, "cais/mmlu")
    ruta = next(iter(sorted((r / "all").glob("test-*.parquet"))), None) if r else None
    t = _tabla(ruta) if ruta else None
    if not t:
        return None
    return {i: (str(x["subject"]), "ABCD"[int(x["answer"])], str(x["question"]).strip(), [str(c).strip() for c in x["choices"]])
            for i, x in enumerate(t) if len(x["choices"]) == 4 and 0 <= int(x["answer"]) < 4}


def par_mmmlu(hf):
    es, motivo = _filas_mmmlu(hf)
    if not es:
        return None, motivo
    en = _filas_mmlu_en(hf)
    if en is None:
        return None, "mmmlu: sin pareja en inglés (falta cais/mmlu all/test-*.parquet): solo se mide en español"
    par = []
    for x in es:
        y = en.get(x["_pos"])
        if y is None or y[0] != x["_materia"] or y[1] != x["etiqueta"]:
            continue
        g = _fila("mmmlu", x["_pos"], "conocimiento", "choice", PREGUNTA_MMLU, y[2], "ABCD", dict(zip("ABCD", y[3])), y[1], "en")
        par.append(({k: v for k, v in x.items() if not k.startswith("_")}, g))
    if len(par) < MIN_COINCIDE_MMLU * len(es):
        return None, "mmmlu: sin pareja en inglés fiable (coinciden materia y respuesta en %d de %d filas, mínimo %.0f %%): solo se mide en español" % (
            len(par), len(es), 100 * MIN_COINCIDE_MMLU)
    return par, None


def solo_es_mmmlu(hf):
    es, motivo = _filas_mmmlu(hf)
    return ([{k: v for k, v in x.items() if not k.startswith("_")} for x in es] if es else None), motivo


PARES = {"massive": par_massive, "xnli": par_xnli, "sib200": par_sib200, "paws-x": par_paws, "mmmlu": par_mmmlu}
SOLO_ES = {"mmmlu": solo_es_mmmlu}   # si el par no sale (sin pareja en inglés), se mide solo en español


def cargar_pares(hf, max_filas, solo=None):
    """-> {nombre: [(fila_es, fila_en)]} con el mismo número de casos (≤ max_filas, submuestra fija), {nombre: motivo no medido}.
    Lo que se puede medir solo en español queda en `cargar_solo_es`."""
    pares, no_medido = {}, {}
    for nombre, f in PARES.items():
        if solo and nombre not in solo:
            continue
        try:
            p, motivo = f(hf)
        except Exception as e:   # un parquet raro no debe tirar la medida de las demás
            p, motivo = None, "%s: %s: %s" % (nombre, type(e).__name__, e)
        if not p:
            no_medido[nombre] = motivo or "%s: sin pares" % nombre
            continue
        if len(p) > max_filas:
            p = [p[i] for i in sorted(random.Random(SEMILLA).sample(range(len(p)), max_filas))]
        pares[nombre] = p
    return pares, no_medido


def cargar_solo_es(hf, max_filas, no_medido, solo=None):
    """-> {nombre: [fila_es]} de las fuentes de `SOLO_ES` cuyo par falló (están en `no_medido`); misma submuestra fija que los pares."""
    out = {}
    for nombre, f in SOLO_ES.items():
        if nombre not in no_medido or (solo and nombre not in solo):
            continue
        try:
            filas, _ = f(hf)
        except Exception:
            filas = None
        if filas:
            out[nombre] = [filas[i] for i in sorted(random.Random(SEMILLA).sample(range(len(filas)), max_filas))] if len(filas) > max_filas else filas
    return out


# ------------------------------------------------------------------ métricas
def acierto_y_f1(y, p, clases):
    """Exactitud y macro-F1 (clases con soporte o predichas) de dos listas de etiquetas."""
    n = len(y)
    acc = sum(a == b for a, b in zip(y, p)) / n
    f1s = []
    for c in clases:
        tp = sum(a == c and b == c for a, b in zip(y, p))
        fp = sum(a != c and b == c for a, b in zip(y, p))
        fn = sum(a == c and b != c for a, b in zip(y, p))
        if tp + fp + fn:
            f1s.append(2 * tp / (2 * tp + fp + fn))
    return acc, sum(f1s) / len(f1s)


def bootstrap(tareas, B, semilla=SEMILLA):
    """tareas: {nombre: (y, p_es, p_en, clases)} -> métricas por tarea y media entre tareas, con IC95 (percentiles) de es − en."""
    rng = random.Random(semilla)

    def todo(idx):   # idx: {tarea: lista de índices}
        out = {}
        for t, (y, pe, pn, cl) in tareas.items():
            ix = idx[t]
            ys, a, b = [y[i] for i in ix], [pe[i] for i in ix], [pn[i] for i in ix]
            out[t] = (acierto_y_f1(ys, a, cl), acierto_y_f1(ys, b, cl))
        return out

    def resumen(r):
        d = {t: {"acc_es": e[0], "acc_en": n[0], "f1_es": e[1], "f1_en": n[1], "d_acc": e[0] - n[0], "d_f1": e[1] - n[1]} for t, (e, n) in r.items()}
        k = len(d)
        d["__media__"] = {c: sum(v[c] for v in d.values()) / k for c in ("acc_es", "acc_en", "f1_es", "f1_en", "d_acc", "d_f1")}
        return d

    punto = resumen(todo({t: list(range(len(v[0]))) for t, v in tareas.items()}))
    muestras = []
    for _ in range(B):
        muestras.append(resumen(todo({t: [rng.randrange(len(v[0])) for _ in v[0]] for t, v in tareas.items()})))
    for t in punto:
        punto[t]["n"] = len(tareas[t][0]) if t != "__media__" else sum(len(v[0]) for v in tareas.values())
        for c in ("d_acc", "d_f1"):
            xs = sorted(m[t][c] for m in muestras)
            punto[t][c + "_ic95"] = [xs[int(0.025 * (B - 1))], xs[int(0.975 * (B - 1))]] if B >= 20 else [None, None]
    return punto


# ------------------------------------------------------------------ plan de reentrenamiento (no se lanza)
def licencia_tarjeta(hf, repo):
    r = _snap(hf, repo)
    if r is None or not (r / "README.md").exists():
        return None
    cab = (r / "README.md").read_text(encoding="utf-8", errors="replace").split("\n---", 1)[0][:4000]
    m = re.search(r"^license:\s*\n?((?:\s*-\s*\S+\n?)+)|^license:\s*(\S+)", cab, re.M)
    if not m:
        return "tarjeta sin campo license"
    return (m.group(2) or " ".join(re.findall(r"-\s*(\S+)", m.group(1)))).strip()


def plan_md(res, hf):
    fuentes, filas = [], 0
    for repo, para, n, uso in FUENTES_PLAN:
        lic = licencia_tarjeta(hf, repo) if not repo.startswith("(") else "propia (sin publicar)"
        ok = bool(lic) and re.search(r"(?<![a-z])(cc-by-4\.0|cc-by-sa-4\.0|apache-2\.0|mit|cc0-1\.0|odc-by)\b", lic.lower()) and "nc" not in lic.lower().split("-")
        fuentes.append((repo, para, n, uso, lic or "NO COMPROBADA (tarjeta no está en la caché local: comprobar en HF antes de usarla)", bool(ok)))
        filas += n if uso == "train" else 0
    horas = 3.0   # general.sh: ≈ 140 min de entrenamiento + 55 de reserva; las fuentes nuevas sustituyen filas, no alargan el tope de 2000 por tarea
    L = ["# M4 plan de reentrenamiento para cerrar la brecha es − en (preparado, NO lanzado)", "",
         "Motivo: |es − en| > %.0f puntos (ver `espanol.json`)." % UMBRAL_PUNTOS, "",
         "## Fuentes en español con licencia comercial", "", "| fuente | para qué | filas aprox. | uso | licencia en la tarjeta de HF | entra en train |", "|---|---|---|---|---|---|"]
    for repo, para, n, uso, lic, ok in fuentes:
        L.append("| %s | %s | %s | %s | %s | %s |" % (repo, para, n or "-", uso, lic, "sí" if (ok and uso == "train") else ("solo test" if uso != "train" else "NO hasta comprobar")))
    L += ["", "Las licencias se leen de `README.md` de la caché de ~/hf; si no está ahí, queda «NO COMPROBADA». PQRS solo entra en test.", "",
          "## Tamaño", "", "≈ %d filas nuevas en español en `train` (tope por tarea 2000 y p ∝ n^0,3, así que cada fuente aporta como mucho 2000 por tarea tras el reparto: "
          "unas %d filas efectivas). Es < 10 %% de la mezcla de G.8." % (filas, 2000 * sum(1 for f in fuentes if f[3] == "train" and f[5])), "",
          "## Cambios en `model/l2/aws/general.sh`", "",
          "1. `CONV`: pasar `--fuentes` con las nuevas (`odio_alia`, `toxicidad_constitucion`, `toxicidad_protestas` ya están en `model.datos`; "
          "MultiPICo, PAWS-X y SIB-200 necesitan conversor nuevo en `model/datos/` con licencia comprobada en la tarjeta).",
          "2. Descarga de HF: `snapshot_download` de esos datasets (con `HF_HUB_OFFLINE=1` después).",
          "3. `EXCLUIR`: dejar `massive,hatecheck,inyecciones` fuera del entrenamiento (siguen siendo el test no visto) y añadir `xnli` solo a test.",
          "4. `G8`: mantener `--tope-tarea 2000 --alfa 0.3 --max-tok 256`; subir `--frac-es` (o equivalente) si el reparto lo permite, sin tocar el resto.",
          "5. Evaluar con `python -m model.l2.espanol` y `model.l2.robustez` al terminar (mismo checkpoint) para comprobar que la brecha baja de 3 puntos.", "",
          "## Coste en GPU", "",
          "g5.xlarge, ~%.2f USD/h: reentrenamiento completo ≈ %.1f h de entrenamiento + 1 h de descarga y evaluación = tope de 240 min de general.sh = **≈ %.1f USD** "
          "(+ ~0,1 USD de disco). Una corrida de ajuste fino desde el checkpoint de G.8 (1 h de entrenamiento) saldría en ≈ %.1f USD." % (
              G5_USD_H, horas, 4 * G5_USD_H, 2 * G5_USD_H), ""]
    return "\n".join(L)


def informe_md(res):
    L = ["# M4 español frente a inglés (L2, k = 0)", "",
         "Mismo esquema (pregunta, ids y descripciones en español) y los mismos casos en los dos idiomas. Δ = es − en, IC95 por bootstrap emparejado (B = %d). "
         "Puntos = 100 × diferencia." % res["boot"], "",
         "| tarea | n | exact es | exact en | Δ exact (pts) | IC95 | F1 es | F1 en | Δ F1 (pts) | IC95 |", "|---|---|---|---|---|---|---|---|---|---|"]
    for t, r in res["tareas"].items():
        def ic(c):
            lo, hi = r[c + "_ic95"]
            return "-" if lo is None else "%+.1f–%+.1f" % (100 * lo, 100 * hi)
        L.append("| %s | %d | %.3f | %.3f | %+.1f | %s | %.3f | %.3f | %+.1f | %s |" % (
            "**media**" if t == "__media__" else t, r["n"], r["acc_es"], r["acc_en"], 100 * r["d_acc"], ic("d_acc"), r["f1_es"], r["f1_en"], 100 * r["d_f1"], ic("d_f1")))
    L.append("")
    if res.get("solo_es"):
        L += ["Solo en español (sin pareja en inglés: no entra en la media es − en):", "", "| tarea | n | exact es | F1 es |", "|---|---|---|---|"]
        L += ["| %s (sin pareja en inglés) | %d | %.3f | %.3f |" % (t, r["n"], r["acc_es"], r["f1_es"]) for t, r in res["solo_es"].items()]
        L.append("")
    for t, m in res["no_medido"].items():
        L.append("- no medido: %s" % m)
    L += ["", "**Brecha > %.0f puntos: %s.**" % (UMBRAL_PUNTOS, "SÍ, ver plan.md" if res["brecha"] else "no")]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--hf", default=None, help="caché de HF (hub); por defecto la de model.datos")
    ap.add_argument("--max-filas", type=int, default=500)
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--solo", default="", help="pares separados por comas")
    ap.add_argument("--max-tok", type=int, default=0)
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args(argv)
    from model.datos.comun import HF_HUB
    from model.l2.modelo import niveles_score
    from model.l2.robustez import ModeloL2
    hf = a.hf or str(HF_HUB)
    pares, no_medido = cargar_pares(hf, a.max_filas, set(filter(None, a.solo.split(","))) or None)
    solo_es = cargar_solo_es(hf, a.max_filas, no_medido, set(filter(None, a.solo.split(","))) or None)
    if not pares and not solo_es:
        print("ningún par es/en disponible: %s" % no_medido, file=sys.stderr)
        return 1
    l2 = ModeloL2(a.ckpt, a.device, a.max_tok)
    tareas = {}
    for nombre, p in pares.items():
        es, en = [x for x, _ in p], [y for _, y in p]
        clases = niveles_score(es[0]["opciones"]) if es[0]["tipo"] == "score" else sorted(es[0]["opciones"])
        y = [f["etiqueta"] for f in es]
        assert y == [f["etiqueta"] for f in en] and len(es) == len(en)
        tareas[nombre] = (y, l2.decidir(es, None), l2.decidir(en, None), clases)
        print(nombre, len(es), flush=True)
    res_es = {}
    for nombre, es in solo_es.items():
        y = [f["etiqueta"] for f in es]
        acc, f1 = acierto_y_f1(y, l2.decidir(es, None), sorted(es[0]["opciones"]))
        res_es[nombre] = {"n": len(es), "acc_es": acc, "f1_es": f1, "nota": "sin pareja en inglés"}
        print(nombre, len(es), "solo es", flush=True)
    res = {"ckpt": a.ckpt, "max_tok": l2.enc.max_tok, "boot": a.boot, "no_medido": no_medido, "tareas": bootstrap(tareas, a.boot) if tareas else {},
           "solo_es": res_es}
    res["brecha"] = any(abs(100 * r[c]) > UMBRAL_PUNTOS for r in res["tareas"].values() for c in ("d_acc", "d_f1"))
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    (sal / "espanol.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    md = informe_md(res)
    (sal / "espanol.md").write_text(md)
    if res["brecha"]:
        (sal / "plan.md").write_text(plan_md(res, hf))
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
