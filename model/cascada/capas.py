"""T2.7: predicciones `{id, probs, ms}` por capa y tarea (formato de `model/esquema.md`) sobre test.

    python -m model.cascada.capas --datos DIR --salida DIR [--tareas massive,...] [--l0-pred DIR]

Capas que se calculan aquí (las de L2 se leen ya hechas, con `leer_l2`):
- `L0`: TF-IDF de caracteres + regresión logística de `model.lineas_base.correr`. Se reusan las predicciones de
  `model/lineas_base/pred/<tarea>__l0_tfidf_lr.jsonl[.gz]` si traen `probs` para todo el test; si no, se recalcula con
  el mismo código (`correr_l0`, soporte de 32 por clase, semilla 0).
- `L1-zs`: lo que hace `server/decide/l1.go`: coseno de potion-multilingual-128M entre el mensaje y
  «pregunta · opción · descripción». choice: softmax(coseno / T), T = 0,05 (tDefecto); noul: σ(4·coseno_true − 2) con θ = 0,5
  (A, B y θ por defecto de `paramsDe`); score: sin opinión (confianza 0), como en el servidor.
- `L1-proto` (candidata, **no** es la capa del servidor): potion con un prototipo por clase = media normalizada de los
  vectores normalizados de todo el train de esa clase, y softmax(coseno / T). Una clase sin train (p. ej. `escalate` en
  CLINC) usa el vector de su texto «pregunta · opción · descripción», como L1-zs.
"""
import argparse
import gzip
import json
import math
import os
import time
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
TAREAS = ("massive", "clinc150", "herramientas", "hatecheck", "inyecciones")
POTION = "minishlab/potion-multilingual-128M"
T_DEFECTO = 0.05          # server/decide/l1.go: tDefecto
NOUL_A, NOUL_B, NOUL_THETA = 4.0, -2.0, 0.5   # server/decide/l1.go: paramsDe sin calibración


def abrir(ruta, modo="rt"):
    return gzip.open(ruta, modo, encoding="utf-8") if str(ruta).endswith(".gz") else open(ruta, modo, encoding="utf-8")


def leer_pred(ruta):
    """-> {id: {"probs": {...}, "ms": float?, ...}}; vacío si el fichero no existe."""
    ruta = Path(ruta)
    if not ruta.exists():
        return {}
    with abrir(ruta) as f:
        out = {}
        for l in f:
            if l.strip():
                d = json.loads(l)
                out[d["id"]] = d
        return out


def guardar_pred(ruta, filas):
    """filas: iterable de dicts {id, probs, ms, ...}."""
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        for d in filas:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def cargar_tarea(tarea, datos):
    """-> train, dev, test (como `model.lineas_base.correr.cargar`)."""
    from model.lineas_base.correr import cargar
    return cargar(tarea, datos)


# --- L0 -----------------------------------------------------------------------------------------------------------
def buscar_pred_l0(pred_dir, tarea):
    for suf in (".jsonl", ".jsonl.gz"):
        r = Path(pred_dir) / ("%s__l0_tfidf_lr%s" % (tarea, suf))
        if r.exists():
            return leer_pred(r)
    return {}


def l0(tarea, train, test, pred_dir=None):
    """-> ({id: pred}, origen). Reusa las predicciones guardadas si cubren el test con `probs`."""
    if pred_dir:
        p = buscar_pred_l0(pred_dir, tarea)
        if p and all(r["id"] in p and p[r["id"]].get("probs") for r in test):
            return {r["id"]: {"id": r["id"], "probs": p[r["id"]]["probs"], "ms": p[r["id"]].get("ms")} for r in test}, "reusadas"
    from model.lineas_base.correr import correr_l0, soporte
    probs, ms = correr_l0(soporte(train), test, test[0]["opciones"])
    return {r["id"]: {"id": r["id"], "probs": dict(zip(r["opciones"], map(float, p))), "ms": round(float(t), 3)}
            for r, p, t in zip(test, probs, ms)}, "recalculadas"


# --- L1 (potion) ---------------------------------------------------------------------------------------------------
def resolver_potion(nombre=POTION):
    """Ruta local del snapshot en $HF_HOME si está completo en lo que importa (la copia de ~/hf no trae README.md y
    `from_pretrained` con red apagada se queja); si no, el nombre tal cual (baja de Hugging Face)."""
    if Path(nombre).is_dir():
        return str(nombre)
    hf = Path(os.environ.get("HF_HOME", Path.home() / "hf")) / "hub" / ("models--" + nombre.replace("/", "--")) / "snapshots"
    for d in sorted(hf.glob("*")):
        if (d / "model.safetensors").exists() and (d / "tokenizer.json").exists():
            return str(d)
    return nombre


def cargar_potion(nombre=POTION):
    from model2vec import StaticModel
    return StaticModel.from_pretrained(resolver_potion(nombre))


def embeber(m, textos):
    """Vectores unitarios float32 (cero si el texto no tiene piezas)."""
    x = np.asarray(m.encode(list(textos)), dtype=np.float32)
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return np.where(n > 0, x / np.where(n > 0, n, 1), 0).astype(np.float32)


def texto_opcion(r, o):
    """«pregunta · opción · descripción», como `textoOpcion` de l1.go."""
    s = [r["pregunta"], o]
    d = (r.get("descripciones") or {}).get(o, "")
    if d:
        s.append(d)
    return " · ".join(s)


def softmax(s, T):
    z = (np.asarray(s, float) - np.max(s)) / T
    e = np.exp(z)
    return e / e.sum()


def _pred(r, probs, ms, **extra):
    d = {"id": r["id"], "probs": {o: float(p) for o, p in zip(r["opciones"], probs)}, "ms": round(float(ms), 3)}
    d.update(extra)
    return d


def _vec_opciones(m, r, cache):
    falta = [texto_opcion(r, o) for o in r["opciones"] if texto_opcion(r, o) not in cache]
    if falta:
        for t, v in zip(falta, embeber(m, falta)):
            cache[t] = v
    return np.stack([cache[texto_opcion(r, o)] for o in r["opciones"]])


def l1_zs(m, test, T=T_DEFECTO):
    """Misma cuenta que `L1.Decidir` (l1.go). -> {id: pred}."""
    cache, out = {}, {}
    for r in test:
        t0 = time.perf_counter()
        if r["tipo"] == "score":   # el servidor no opina: confianza 0 y la cascada pasa a la siguiente capa
            n = len(r["opciones"])
            out[r["id"]] = _pred(r, [1 / n] * n, 0, sin_opinion=True)
            continue
        msg = embeber(m, [r["texto"]])[0]
        ops = _vec_opciones(m, r, cache)
        sims = ops @ msg
        if r["tipo"] == "noul":
            s = float(sims[r["opciones"].index("true")])
            pt = 1 / (1 + math.exp(-(NOUL_A * s + NOUL_B)))
            probs = [pt if o == "true" else 1 - pt for o in r["opciones"]]
        else:
            probs = softmax(sims, T)
        out[r["id"]] = _pred(r, probs, (time.perf_counter() - t0) * 1000)
    return out


def prototipos(m, train):
    """{clase: vector unitario} = media normalizada de los vectores normalizados del train de la clase."""
    x = embeber(m, [r["texto"] for r in train])
    por = {}
    for r, v in zip(train, x):
        por.setdefault(r["etiqueta"], []).append(v)
    out = {}
    for c, vs in por.items():
        mu = np.mean(vs, axis=0)
        n = np.linalg.norm(mu)
        out[c] = (mu / n).astype(np.float32) if n > 0 else mu
    return out


def l1_proto(m, train, test, T=T_DEFECTO):
    protos = prototipos(m, train)
    cache, out = {}, {}
    for r in test:
        t0 = time.perf_counter()
        msg = embeber(m, [r["texto"]])[0]
        zs = None
        mat = []
        for i, o in enumerate(r["opciones"]):
            if o in protos:
                mat.append(protos[o])
            else:
                zs = _vec_opciones(m, r, cache) if zs is None else zs
                mat.append(zs[i])
        out[r["id"]] = _pred(r, softmax(np.stack(mat) @ msg, T), (time.perf_counter() - t0) * 1000)
    return out


# --- L2 (predicciones ya hechas) ------------------------------------------------------------------------------------
def leer_l2(raiz, tarea, soporte):
    """`raiz/pred_soporte/<tarea>.jsonl` (con soporte) o `raiz/pred/<tarea>.jsonl` (sin). Vacío si no está."""
    d = "pred_soporte" if soporte else "pred"
    for suf in (".jsonl", ".jsonl.gz"):
        p = Path(raiz) / d / (tarea + suf)
        if p.exists():
            return leer_pred(p)
    return {}


# --- CLI -------------------------------------------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True, help="salida de model.datos.convertir")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--tareas", default=",".join(TAREAS))
    ap.add_argument("--l0-pred", default=str(RAIZ / "model" / "lineas_base" / "pred"))
    ap.add_argument("--potion", default=POTION, help="repo de Hugging Face o ruta local")
    ap.add_argument("--max-test", type=int, default=0, help="(pruebas) recorta el test")
    a = ap.parse_args(argv)
    m = cargar_potion(a.potion)
    salida = Path(a.salida)
    for tarea in a.tareas.split(","):
        train, _, test = cargar_tarea(tarea, a.datos)
        if a.max_test:
            test = test[:a.max_test]
        p0, origen = l0(tarea, train, test, a.l0_pred)
        print("==", tarea, "train", len(train), "test", len(test), "L0", origen, flush=True)
        guardar_pred(salida / "L0" / (tarea + ".jsonl"), (p0[r["id"]] for r in test))
        z = l1_zs(m, test)
        guardar_pred(salida / "L1-zs" / (tarea + ".jsonl"), (z[r["id"]] for r in test))
        p = l1_proto(m, train, test)
        guardar_pred(salida / "L1-proto" / (tarea + ".jsonl"), (p[r["id"]] for r in test))


if __name__ == "__main__":
    main()
