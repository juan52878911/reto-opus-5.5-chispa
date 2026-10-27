"""T1.7a: líneas base provisionales sobre los test reales.

    python -m model.lineas_base.correr [--sistemas l0,knn,thx01] [--tareas massive,...] [--datos DIR] [--salida DIR]

Sistemas: `l0` (TF-IDF de caracteres + regresión logística), `knn` (e5-small, kNN-8 y kNN-32) y `thx01`
(solo intención, herramientas y CLINC, ≤ 300 filas por tarea). Escribe en `pred/` las predicciones
`{id, probs, ms}` por tarea y sistema, y `resultados.json` con lo que devuelve `chispa eval`.
Soporte/entrenamiento: 32 ejemplos por clase del train, con semilla fija (SEMILLA); kNN-8 usa los 8 primeros
de esos 32. La temperatura del softmax del kNN se fija en dev (en herramientas, que no tiene dev, con
«dejar uno fuera» sobre el soporte).
"""
import argparse
import glob
import gzip
import json
import os
import random
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_WAIT_POLICY", "passive")
import numpy as np

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
SEMILLA = 0
POR_CLASE = 32
VECINOS = 10
TEMPS = (0.005, 0.01, 0.02, 0.03, 0.05, 0.07, 0.1, 0.2)
MAX_THX = 300
TAREAS = ("massive", "hatecheck", "clinc150", "inyecciones", "herramientas")
THX_TAREAS = ("massive", "clinc150", "herramientas")
FUENTE_PLAN = {"inyecciones": "inyecciones"}


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def cargar(tarea, datos):
    """-> train, dev, test (listas de filas)."""
    if tarea == "herramientas":
        h = RAIZ / "model" / "herramientas"
        return leer(h / "train.jsonl"), [], leer(h / "test.jsonl")
    filas = leer(Path(datos) / (tarea + ".jsonl"))
    por = lambda s: [r for r in filas if r["split"] == s]
    return por("train"), por("dev"), por("test")


def soporte(train):
    """32 por clase, orden barajado con semilla fija; los 8 primeros de cada clase forman el soporte de kNN-8."""
    rng = random.Random(SEMILLA)
    por = {}
    for r in train:
        por.setdefault(r["etiqueta"], []).append(r)
    out = []
    for c in sorted(por):
        g = sorted(por[c], key=lambda r: r["id"])
        rng.shuffle(g)
        for i, r in enumerate(g[:POR_CLASE]):
            out.append((i, r))
    return out


def submuestra(filas, n):
    if len(filas) <= n:
        return filas
    idx = sorted(random.Random(SEMILLA).sample(range(len(filas)), n))
    return [filas[i] for i in idx]


def guardar_pred(ruta, filas, probs, ms):
    with open(ruta, "w", encoding="utf-8") as f:
        for r, p, t in zip(filas, probs, ms):
            f.write(json.dumps({"id": r["id"], "probs": dict(zip(r["opciones"], map(float, p))),
                                "ms": round(float(t), 3)}) + "\n")


def normalizar(p):
    p = np.asarray(p, float)
    return p / p.sum()


# --- L0: TF-IDF de caracteres + regresión logística --------------------------------------------------------
def correr_l0(sop, test, ops):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, lowercase=True)
    x = vec.fit_transform([r["texto"] for _, r in sop])
    clf = LogisticRegression(C=10.0, max_iter=1000).fit(x, [r["etiqueta"] for _, r in sop])
    col = {c: i for i, c in enumerate(clf.classes_)}
    probs, ms = [], []
    for r in test:
        t = time.perf_counter()
        pr = clf.predict_proba(vec.transform([r["texto"]]))[0]
        ms.append((time.perf_counter() - t) * 1000)
        probs.append(normalizar([pr[col[o]] if o in col else 0.0 for o in r["opciones"]]))
    return probs, ms


# --- e5-small + kNN -----------------------------------------------------------------------------------------
def codificador():
    from sentence_transformers import SentenceTransformer
    p = glob.glob(os.path.expanduser("~/hf/hub/models--intfloat--multilingual-e5-small/snapshots/*"))[0]
    return SentenceTransformer(p, device="cpu")


def embeber(m, textos):
    return m.encode(["query: " + t for t in textos], normalize_embeddings=True, batch_size=32)


def vecinos(sims, y, ops, temp):
    idx = np.argsort(-sims)[:VECINOS]
    w = np.exp((sims[idx] - sims[idx].max()) / temp)
    p = dict.fromkeys(ops, 0.0)
    for i, wi in zip(idx, w):
        p[y[i]] += float(wi)
    return normalizar([p[o] for o in ops])


def fijar_temperatura(xs, ys, xd, yd, ops, dejar_uno):
    """Temperatura con menor log-verosimilitud negativa (probabilidad acotada a 1e-4) en dev."""
    mejor = None
    for temp in TEMPS:
        nll = 0.0
        for j, q in enumerate(xd):
            s = xs @ q
            if dejar_uno:
                s = s.copy()
                s[j] = -np.inf
            p = vecinos(s, ys, ops, temp)
            nll -= np.log(max(p[ops.index(yd[j])], 1e-4))
        if mejor is None or nll < mejor[1]:
            mejor = (temp, nll)
    return mejor[0]


def correr_knn(sop, dev, test, ops, m, xte, ms_enc):
    """-> {k: (probs, ms, temperatura)}."""
    res = {}
    for k in (8, 32):
        s = [r for i, r in sop if i < k]
        ys = np.array([r["etiqueta"] for r in s])
        xs = embeber(m, [r["texto"] for r in s])
        if dev:
            dev = submuestra(dev, 1000)
            xd, yd, lo = embeber(m, [r["texto"] for r in dev]), [r["etiqueta"] for r in dev], False
        else:
            xd, yd, lo = xs, list(ys), True
        temp = fijar_temperatura(xs, ys, xd, yd, ops, lo)
        probs, ms = [], []
        for q, t_enc in zip(xte, ms_enc):
            t = time.perf_counter()
            probs.append(vecinos(xs @ q, ys, ops, temp))
            ms.append(t_enc + (time.perf_counter() - t) * 1000)
        res[k] = (probs, ms, temp)
    return res


# --- THX-01 -------------------------------------------------------------------------------------------------
def correr_thx(test, tarea_dec):
    sys.path.insert(0, str(RAIZ / "model" / "eval0"))
    import _decision
    d = _decision.Decision("~/hf/hub/models--doofz--THX-01/snapshots/*", tarea_dec)
    for f in test[:2]:
        d.predecir(f)
    probs, ms = [], []
    for f in test:
        t = time.perf_counter()
        p = d.predecir(f)
        ms.append((time.perf_counter() - t) * 1000)
        probs.append(normalizar(p))
    return probs, ms


def evaluar(datos_ruta, pred_ruta):
    from model.evaluacion import chispa_eval as ce
    salida = pred_ruta.with_suffix(".eval.json")
    ce.main(["--datos", str(datos_ruta), "--pred", str(pred_ruta), "--salida", str(salida)])
    r = json.load(open(salida))
    salida.unlink()
    return r["global"]


def comprimir_si_pasa(ruta):
    if ruta.stat().st_size > 5 * 1024 * 1024:
        with open(ruta, "rb") as a, gzip.open(str(ruta) + ".gz", "wb", 9) as b:
            b.writelines(a)
        ruta.unlink()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sistemas", default="l0,knn,thx01")
    ap.add_argument("--tareas", default=",".join(TAREAS))
    ap.add_argument("--datos", default="/tmp/lb_datos", help="salida de model.datos.convertir (se genera si falta)")
    ap.add_argument("--salida", default=str(AQUI))
    ap.add_argument("--hilos", type=int, default=4)
    ap.add_argument("--max-thx", type=int, default=MAX_THX, help="filas por tarea para THX-01")
    a = ap.parse_args(argv)
    sistemas, tareas = a.sistemas.split(","), a.tareas.split(",")
    import torch
    torch.set_num_threads(a.hilos)
    if not (Path(a.datos) / "resumen.json").exists():
        from model.datos.convertir import convertir_fuentes
        convertir_fuentes(a.datos)
    out = Path(a.salida)
    pred_dir, tmp = out / "pred", Path("/tmp/lb_test")
    pred_dir.mkdir(parents=True, exist_ok=True)
    tmp.mkdir(parents=True, exist_ok=True)
    resf = out / "resultados.json"
    resultados = json.load(open(resf)) if resf.exists() else {}
    m = codificador() if "knn" in sistemas else None
    for tarea in tareas:
        train, dev, test = cargar(tarea, a.datos)
        ops = test[0]["opciones"]
        sop = soporte(train)
        print("==", tarea, "train", len(train), "soporte", len(sop), "dev", len(dev), "test", len(test), flush=True)
        datos_ruta = tmp / (tarea + ".jsonl")
        with open(datos_ruta, "w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in test)
        trabajos = {}
        if "l0" in sistemas:
            trabajos["l0_tfidf_lr"] = correr_l0(sop, test, ops)[:2] + (None,)
        if "knn" in sistemas:
            xte, ms_enc = [], []
            for r in test:
                t = time.perf_counter()
                xte.append(embeber(m, [r["texto"]])[0])
                ms_enc.append((time.perf_counter() - t) * 1000)
            for k, v in correr_knn(sop, dev, test, ops, m, np.array(xte), ms_enc).items():
                trabajos["e5_knn%d" % k] = v
        for nombre, (probs, ms, temp) in trabajos.items():
            ruta = pred_dir / ("%s__%s.jsonl" % (tarea, nombre))
            guardar_pred(ruta, test, probs, ms)
            r = evaluar(datos_ruta, ruta)
            r["temperatura"] = temp
            resultados.setdefault(tarea, {})[nombre] = r
            comprimir_si_pasa(ruta)
        if "thx01" in sistemas and tarea in THX_TAREAS:
            sub = submuestra(test, a.max_thx)
            ruta_d = tmp / (tarea + "_thx.jsonl")
            with open(ruta_d, "w", encoding="utf-8") as f:
                f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in sub)
            probs, ms = correr_thx(sub, "herramientas" if tarea == "herramientas" else "intencion")
            ruta = pred_dir / ("%s__thx01.jsonl" % tarea)
            guardar_pred(ruta, sub, probs, ms)
            r = evaluar(ruta_d, ruta)
            r["temperatura"] = None
            resultados.setdefault(tarea, {})["thx01"] = r
            comprimir_si_pasa(ruta)
        with open(resf, "w", encoding="utf-8") as f:
            json.dump(resultados, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
