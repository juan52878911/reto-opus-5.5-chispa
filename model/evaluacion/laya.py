"""W12: mide Laya (zero-shot, CPU) con la batería de Chispa y en M4 (español).

Adaptador de nuestra fila (`model/esquema.md`, `chispa.bateria.Fila`) a la pregunta de `laya.Router.predict`:
  choice  criteria = {id: descripción}                     (sin descripción, el id)
  noul    pregunta noul; true si p ≥ 0,5
  score   criteria = descripciones de los niveles 1..K ordenadas por int; el nivel elegido se mapea a su id
  instructions = pregunta
Las métricas son las de `chispa.bateria` (`agregar`: exactitud por argmax, F1 macro, ECE, p50/p99), no una copia.

Fases (cada una escribe su JSON en --salida):
  velocidad  50 preguntas de massive con el primer modelo; proyecta el total y fija el tope de filas por conjunto (o dice que no cabe)
  bateria    los conjuntos del manifiesto (JevBench, massive, clinc150, hatecheck, spam, inyecciones, herramientas; split test)
  m4         MASSIVE-es y MMMLU ES_LA con su pareja inglesa (model.l2.espanol)
  licencia   `license` y datos de entrenamiento de la tarjeta de HF de cada checkpoint
  tabla      laya-frente-chispa.md con las cifras de Laya y las de los linea-base*.json de Chispa
`--falso` usa un Laya de mentira (misma interfaz, devuelve la primera opción) para la prueba en seco.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
try:
    from chispa import bateria as B
except ModuleNotFoundError:   # sin PYTHONPATH=sdk/python
    sys.path.insert(0, str(RAIZ / "sdk" / "python"))
    from chispa import bateria as B

MODELOS = ("multilingual", "typed-decisions")
REPO_LAYA = "convaiinnovations/laya"
CHECKPOINTS = ("english", "multilingual", "typed-decisions")
HILOS = 4
N_VELOCIDAD = 50
MAX_MIN = 70.0
MARGEN = 1.5           # la velocidad se mide en massive; clinc150, JevBench y MMMLU llevan más texto
CARGA_S = 120.0        # carga de cada checkpoint
TOPES = (None, 2000, 1500, 1000, 750, 500, 300, 200, 100, 50)
PREGUNTA = "q"


# ------------------------------------------------------------------ adaptador
def _niveles(f):
    """Ids de score ordenados por int (ascendente)."""
    return sorted((o.id for o in f.q.options), key=int)


def pregunta_laya(f):
    """-> (pregunta de Laya, ids en el orden de sus criteria). `f` es un `chispa.bateria.Fila`."""
    desc = {o.id: o.description for o in f.q.options}
    if f.tipo == "noul":
        return {"type": "noul", "instructions": f.q.question}, ["false", "true"]
    if f.tipo == "choice":
        ids = [o.id for o in f.q.options]
        return {"type": "choice", "instructions": f.q.question, "criteria": {i: desc[i] or i for i in ids}}, ids
    if f.tipo == "score":
        ids = _niveles(f)
        return {"type": "score", "instructions": f.q.question, "criteria": [desc[i] or "nivel " + i for i in ids]}, ids
    raise ValueError("tipo %r sin equivalente en Laya" % f.tipo)


def _a_id(v, ids, descs, tipo):
    """Un valor que Laya devuelve para una opción -> nuestro id (o None). score: el nivel 1..K es el índice + 1 de `ids` (ya ordenados)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, str) and v in ids:
        return v
    if isinstance(v, str) and v in descs:
        return ids[descs.index(v)]
    if tipo == "score":
        try:
            n = int(float(v))
        except (TypeError, ValueError):
            return None
        return ids[n - 1] if 1 <= n <= len(ids) else None
    return None


def _probs(a, ids, descs, tipo):
    """Distribución de la respuesta de choice/score: `probs` o `distribution` (dict por id/descripción/nivel, o lista en el orden de los criteria)."""
    for k in ("probs", "distribution", "probabilities"):
        d = a.get(k)
        if isinstance(d, dict):
            out = {_a_id(c, ids, descs, tipo): float(p) for c, p in d.items() if isinstance(p, (int, float))}
            out.pop(None, None)
            if out:
                return out
        elif isinstance(d, (list, tuple)) and len(d) == len(ids) and all(isinstance(p, (int, float)) for p in d):
            return {i: float(p) for i, p in zip(ids, d)}
    return {}


def leer_respuesta(f, resp, ids):
    """-> (id elegido o '', probs por id de nuestra fila). `resp` = r["answers"][PREGUNTA]. Falla con ValueError si no la entiende."""
    if f.tipo == "noul":
        p = float(resp["noul"])
        return ("true" if p >= 0.5 else "false"), {"false": 1.0 - p, "true": p}
    q, _ = pregunta_laya(f)
    descs = list(q["criteria"].values() if f.tipo == "choice" else q["criteria"])
    elegido = None
    for k in ("choice", "score", "level", "value"):
        if k in resp:
            elegido = _a_id(resp[k], ids, descs, f.tipo)
            break
    probs = _probs(resp, ids, descs, f.tipo)
    if elegido is None and probs:
        elegido = max(probs, key=probs.get)
    if elegido is None:
        raise ValueError("respuesta no interpretable: %s" % json.dumps(resp, default=str)[:200])
    if not probs:   # solo el id: la confianza que traiga o 1,0
        c = next((resp[k] for k in ("confidence", "prob", "probability", "score_prob") if isinstance(resp.get(k), (int, float)) and not isinstance(resp.get(k), bool)), 1.0)
        probs = {elegido: float(c)}
    return elegido, probs


# ------------------------------------------------------------------ Laya (real y de mentira)
class RouterFalso:
    """La misma interfaz que `laya.Router.predict`; devuelve la primera opción de cada pregunta."""

    def predict(self, state, questions, model="multilingual", max_len=None):
        out = {}
        for nombre, q in questions.items():
            if q["type"] == "noul":
                out[nombre] = {"noul": 0.0}
            elif q["type"] == "choice":
                out[nombre] = {"choice": next(iter(q["criteria"]))}
            else:
                out[nombre] = {"score": 1}
        return {"answers": out, "routing": {"model": model}}


def crear_router(falso):
    if falso:
        return RouterFalso()
    from laya import Router
    return Router()


def decidir(router, f, modelo, vistas=None, max_len=None, reloj=time.perf_counter):
    """Una fila -> el dict que espera `chispa.bateria.agregar` (como `_decidir`)."""
    q, ids = pregunta_laya(f)
    r = {"id": f.id, "tipo": f.tipo, "esquema": f.esquema, "etiqueta": f.etiqueta, "opciones": ids, "answer": "", "answers": None, "probs": {}, "layer": "laya:" + modelo,
         "escalate": False, "escalate_reason": "", "ms": None, "cliente_ms": None, "error": "", "error_codigo": ""}
    kw = {"model": modelo}
    if max_len:
        kw["max_len"] = max_len
    t0 = reloj()
    try:
        x = router.predict(f.texto, {PREGUNTA: q}, **kw)
        ms = (reloj() - t0) * 1000
        resp = x["answers"][PREGUNTA]
        if vistas is not None and (modelo, f.tipo) not in vistas:   # la forma exacta de la respuesta no está documentada: se vuelca la primera de cada tipo
            vistas[(modelo, f.tipo)] = {"pregunta": q, "respuesta": x}
            print("PRIMERA RESPUESTA %s %s: %s" % (modelo, f.tipo, json.dumps(vistas[(modelo, f.tipo)], ensure_ascii=False, default=str)), flush=True)
        r["answer"], r["probs"] = leer_respuesta(f, resp, ids)
        r["ms"] = r["cliente_ms"] = ms
    except Exception as e:   # una fila rara no tira la medida: cuenta como error
        r.update(error="%s: %s" % (type(e).__name__, e), error_codigo=type(e).__name__)
    return r


# ------------------------------------------------------------------ datos
def reducir(filas, tope):
    """Submuestra determinista: `tope` filas a intervalos regulares (conserva el orden)."""
    n = len(filas)
    return list(filas) if not tope or n <= tope else [filas[i * n // tope] for i in range(tope)]


def cargar_conjuntos(manifiesto):
    """[(spec, filas)] de los conjuntos del manifiesto con grupo != no_visto (los mismos que la batería, split test)."""
    man = B.leer_manifiesto(manifiesto)
    out = []
    for c in man["conjuntos"]:
        if c.get("grupo") == "no_visto":
            continue
        ruta = B.resolver_ruta(c["ruta"], man["_dir"])
        if ruta is None:
            raise B.ErrorBateria("conjunto %r: no encuentro %r (¿variable de entorno sin definir?)" % (c["nombre"], c["ruta"]))
        fs = B.cargar_filas(ruta, c.get("formato", "auto"), c.get("tipo"), c.get("limite"), c.get("split", "test"))
        if not fs:
            raise B.ErrorBateria("conjunto %r: %s no tiene filas" % (c["nombre"], ruta))
        out.append((c, fs))
    return out


# ------------------------------------------------------------------ velocidad
def proyectar(seg_pregunta, n_filas, n_modelos, n_m4, margen=MARGEN):
    """Minutos del total: filas de la batería + preguntas de M4, por modelo, más la carga de cada checkpoint."""
    return (margen * seg_pregunta * (sum(n_filas) + n_m4) * n_modelos + CARGA_S * n_modelos) / 60.0


def elegir_tope(seg_pregunta, tamanos, n_modelos, n_m4, max_min=MAX_MIN):
    """-> (tope de filas por conjunto o None si cabe entero, minutos proyectados). Tope None-que-no-cabe: (False, min) si ni 50 filas caben."""
    for t in TOPES:
        n = [min(x, t) if t else x for x in tamanos]
        m = proyectar(seg_pregunta, n, n_modelos, n_m4)
        if m <= max_min:
            return t, m
    return False, proyectar(seg_pregunta, [min(x, TOPES[-1]) for x in tamanos], n_modelos, n_m4)


def fase_velocidad(a):
    conjuntos = cargar_conjuntos(a.manifiesto)
    massive = next((fs for c, fs in conjuntos if c["nombre"] == "massive"), None)
    if massive is None:
        raise B.ErrorBateria("la prueba de velocidad necesita el conjunto massive en el manifiesto")
    router = crear_router(a.falso)
    modelo = a.modelos[0]
    muestra = reducir(massive, N_VELOCIDAD + 3)
    for f in muestra[:3]:   # calentamiento (carga del checkpoint): no cuenta
        decidir(router, f, modelo)
    ms = []
    for f in muestra[3:3 + N_VELOCIDAD]:
        r = decidir(router, f, modelo)
        if r["error"]:
            raise B.ErrorBateria("velocidad: %s" % r["error"])
        ms.append(r["cliente_ms"])
    seg = sum(ms) / len(ms) / 1000.0
    tamanos = [len(fs) for _, fs in conjuntos]
    n_m4 = 4 * a.m4_filas
    tope, minutos = elegir_tope(seg, tamanos, len(a.modelos), n_m4, a.max_minutos)
    res = {"modelo": modelo, "n": len(ms), "seg_por_pregunta": seg, "p50_ms": B._pct(ms, 0.5), "p99_ms": B._pct(ms, 0.99), "hilos": HILOS, "max_minutos": a.max_minutos,
           "filas_por_conjunto": dict(zip([c["nombre"] for c, _ in conjuntos], tamanos)), "preguntas_m4": n_m4, "margen": MARGEN,
           "proyeccion_min_sin_tope": proyectar(seg, tamanos, len(a.modelos), n_m4), "cabe": tope is not False, "tope_filas": tope or None,
           "proyeccion_min": minutos}
    res["nota"] = ("cabe entera" if tope is None else "recortada a %s filas por conjunto (submuestra regular y determinista)" % tope if tope else
                   "NO CABE ni con 50 filas por conjunto: no se sigue")
    Path(a.salida, "velocidad.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(res["nota"], "| %.2f s/pregunta, proyección %.1f min (sin tope %.1f)" % (seg, minutos, res["proyeccion_min_sin_tope"]), flush=True)
    return 0 if res["cabe"] else 3


# ------------------------------------------------------------------ batería
def _agregados(rs):
    return B.agregar(rs)


def fase_bateria(a):
    tope = a.tope_filas
    vel = Path(a.salida, "velocidad.json")
    if tope is None and vel.exists():
        v = json.loads(vel.read_text())
        if not v["cabe"]:
            print("la prueba de velocidad dijo que no cabe: no se sigue", file=sys.stderr)
            return 3
        tope = v["tope_filas"]
    conjuntos = cargar_conjuntos(a.manifiesto)
    router = crear_router(a.falso)
    vistas, res = {}, {m: {} for m in a.modelos}
    todas = {m: [] for m in a.modelos}
    t0, incompleto = time.time(), None
    for c, fs in conjuntos:
        sub = reducir(fs, tope)
        rs = {m: [] for m in a.modelos}
        for f in sub:
            if time.time() - t0 > a.max_minutos * 60:
                incompleto = "tiempo agotado (%.0f min) en %s tras %d de %d filas" % (a.max_minutos, c["nombre"], len(rs[a.modelos[0]]), len(sub))
                break
            for m in a.modelos:
                rs[m].append(decidir(router, f, m, vistas, a.max_len))
        for m in a.modelos:
            if rs[m]:
                res[m][c["nombre"]] = dict(_agregados(rs[m]), tipo=c.get("tipo", "mixto"), n_total=len(fs), n_medido=len(rs[m]))
                todas[m] += rs[m]
        print("%s: %d/%d filas, %.1f min" % (c["nombre"], len(sub) if not incompleto else len(rs[a.modelos[0]]), len(fs), (time.time() - t0) / 60), flush=True)
        if incompleto:
            break
    salida = {"modelos": {m: {"conjuntos": res[m], "global": _agregados(todas[m]) if todas[m] else {}} for m in a.modelos}, "tope_filas": tope, "hilos": HILOS,
              "incompleto": incompleto, "minutos": (time.time() - t0) / 60, "primeras_respuestas": {"%s/%s" % k: v for k, v in vistas.items()}}
    errores = {m: sum(1 for r in todas[m] if r["error"]) for m in a.modelos}
    salida["errores"] = errores
    Path(a.salida, "bateria.json").write_text(json.dumps(salida, indent=1, ensure_ascii=False, default=str))
    if incompleto:
        print("INCOMPLETO:", incompleto, file=sys.stderr)
        return 3
    return 0


# ------------------------------------------------------------------ M4
def fase_m4(a):
    from model.datos.comun import HF_HUB
    from model.l2 import espanol as E
    hf = a.hf or str(HF_HUB)
    solo = {"massive", "mmmlu"}
    pares, no_medido = E.cargar_pares(hf, a.m4_filas, solo)
    solo_es = E.cargar_solo_es(hf, a.m4_filas, no_medido, solo)
    if not pares and not solo_es:
        print("ni MASSIVE ni MMMLU disponibles: %s" % no_medido, file=sys.stderr)
        return 1
    router = crear_router(a.falso)
    vistas = {}

    def medir(filas, m):
        rs = [decidir(router, B._a_fila(x), m, vistas, a.max_len) for x in filas]
        return B.agregar(rs)

    res = {"no_medido": no_medido, "modelos": {}, "n_filas_max": a.m4_filas, "hilos": HILOS}
    for m in a.modelos:
        out = {}
        for nombre, p in pares.items():
            es, en = [x for x, _ in p], [y for _, y in p]
            ames, amen = medir(es, m), medir(en, m)
            out[nombre] = {"n": len(p), "acc_es": ames["exactitud"], "acc_en": amen["exactitud"], "f1_es": ames["f1_macro"], "f1_en": amen["f1_macro"],
                           "d_acc": (ames["exactitud"] or 0) - (amen["exactitud"] or 0), "p50_ms_es": ames["p50_ms"], "errores": ames["errores"] + amen["errores"]}
        for nombre, es in solo_es.items():
            ames = medir(es, m)
            out[nombre] = {"n": len(es), "acc_es": ames["exactitud"], "f1_es": ames["f1_macro"], "acc_en": None, "d_acc": None, "p50_ms_es": ames["p50_ms"],
                           "errores": ames["errores"], "nota": "sin pareja en inglés"}
        res["modelos"][m] = out
        print("M4", m, {k: round(v["acc_es"] or 0, 3) for k, v in out.items()}, flush=True)
    Path(a.salida, "m4.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


# ------------------------------------------------------------------ licencia
def _frontal(texto):
    m = re.match(r"\s*---\s*\n(.*?)\n---", texto, re.S)
    return m.group(1) if m else ""


def leer_tarjeta(texto):
    """-> {license, datasets (del frontal), datos (secciones sobre datos/entrenamiento)}."""
    fr = _frontal(texto)
    m = re.search(r"^license:\s*\n?((?:\s*-\s*\S+\n?)+)|^license:\s*(\S+)", fr, re.M)
    lic = (m.group(2) or " ".join(re.findall(r"-\s*(\S+)", m.group(1)))).strip() if m else None
    ds = re.search(r"^datasets:\s*\n((?:\s*-\s*\S+\n?)+)", fr, re.M)
    datasets = re.findall(r"-\s*(\S+)", ds.group(1)) if ds else []
    cuerpo = re.sub(r"\A\s*---\s*\n.*?\n---", "", texto, count=1, flags=re.S)
    secciones = []
    for h, t in re.findall(r"^#+\s*(.+?)\s*\n(.*?)(?=^#+\s|\Z)", cuerpo, re.S | re.M):
        if re.search(r"train|data|dataset|corpus|datos|entrena", h, re.I) and t.strip():
            secciones.append({"seccion": h, "texto": t.strip()[:1500]})
    return {"license": lic, "datasets": datasets, "datos": secciones}


def buscar_tarjetas(raiz):
    """[(ruta relativa, Path)] de los README.md bajo `raiz` (la caché de HF del repo de Laya, o un directorio de fixtures)."""
    raiz = Path(raiz)
    return sorted((str(p.relative_to(raiz)), p) for p in raiz.glob("**/README*.md")) if raiz.is_dir() else []


def descargar_tarjetas():
    """Baja las tarjetas (solo .md) del repo de Laya a la caché de HF y devuelve su directorio; None si no se puede."""
    try:
        from huggingface_hub import snapshot_download
        return snapshot_download(REPO_LAYA, allow_patterns=["README*.md", "**/README*.md", "*.md"])
    except Exception as e:
        print("aviso: no se pudieron bajar las tarjetas de %s: %s" % (REPO_LAYA, e), file=sys.stderr)
        return None


def fase_licencia(a):
    raiz = a.tarjetas or (None if a.falso else descargar_tarjetas())
    tarjetas = buscar_tarjetas(raiz) if raiz else []
    res = {"repo": REPO_LAYA, "checkpoints": {}, "paquete": None}
    try:
        from importlib import metadata
        md = metadata.metadata("laya")
        res["paquete"] = {"version": md.get("Version"), "license": md.get("License") or md.get("License-Expression")}
    except Exception:
        res["paquete"] = None
    for ck in CHECKPOINTS:
        propia = [t for t in tarjetas if ck in t[0].lower()]   # tarjeta de la subcarpeta del checkpoint, si la hay; si no, la del repo
        raiz_t = [t for t in tarjetas if "/" not in t[0]]
        ruta, p = (propia or raiz_t or [(None, None)])[0]
        if p is None:
            res["checkpoints"][ck] = {"tarjeta": None, "license": None, "datos_entrenamiento": None, "nota": "no hay tarjeta"}
            continue
        t = leer_tarjeta(p.read_text(encoding="utf-8", errors="replace"))
        res["checkpoints"][ck] = {"tarjeta": ruta, "license": t["license"], "datasets": t["datasets"],
                                  "datos_entrenamiento": t["datos"] or "la tarjeta no dice nada sobre los datos de entrenamiento"}
    Path(a.salida, "laya-licencia.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    sin = [k for k, v in res["checkpoints"].items() if not v.get("license")]
    if sin:
        print("sin license en la tarjeta de: %s" % ", ".join(sin), file=sys.stderr)
        return 3
    return 0


# ------------------------------------------------------------------ tabla
def _n(x, d=3):
    return "-" if x is None else ("%.*f" % (d, x))


def _celda(m):
    return "-" if not m or m.get("exactitud") is None else "%s · F1 %s · ECE %s" % (_n(m["exactitud"]), _n(m.get("f1_macro")), _n(m.get("ece")))


def _lat(m):
    return "-" if not m or m.get("p50_ms") is None else "%.0f/%.0f" % (m["p50_ms"], m["p99_ms"])


def tabla_md(bat, m4, bases, vel=None):
    """bases = [(nombre, linea-base JSON)]. Una fila por conjunto + global; las latencias son p50/p99 en ms."""
    modelos = list(bat["modelos"])
    cab = ["conjunto", "n"] + ["Laya " + m for m in modelos] + ["Chispa " + n for n, _ in bases] + ["latencia ms p50/p99 (Laya %s · Chispa %s)" % (" / ".join(modelos), " / ".join(n for n, _ in bases))]
    L = ["# Laya frente a Chispa (zero-shot, CPU, %d hilos)" % bat.get("hilos", HILOS), "",
         "Cada celda: exactitud (argmax) · F1 macro · ECE sin calibrar. Mismas filas de la batería (split test); Chispa de los linea-base*.json del repo.", ""]
    if bat.get("tope_filas"):
        L += ["**Recorte:** Laya midió como mucho %d filas por conjunto (submuestra regular y determinista, por la prueba de velocidad); con `n` Laya/total. "
              "Chispa midió todas, así que las cifras no son del mismo subconjunto." % bat["tope_filas"], ""]
    if bat.get("incompleto"):
        L += ["**INCOMPLETO:** %s" % bat["incompleto"], ""]
    L += ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    ref = bat["modelos"][modelos[0]]
    filas = list(ref["conjuntos"]) + ["global"]
    for k in filas:
        g = k == "global"
        mm = [(bat["modelos"][m]["global"] if g else bat["modelos"][m]["conjuntos"].get(k)) for m in modelos]
        bb = [(b["global"] if g else b["conjuntos"].get(k)) for _, b in bases]
        n = (mm[0] or {}).get("n", "-") if g else "%s/%s" % (ref["conjuntos"][k]["n_medido"], ref["conjuntos"][k]["n_total"])
        lat = " · ".join(_lat(x) for x in mm) + " | " + " · ".join(_lat(x) for x in bb)
        L.append("| " + " | ".join([k, str(n)] + [_celda(x) for x in mm] + [_celda(x) for x in bb] + [lat.replace(" | ", " vs ")]) + " |")
    if m4:
        L += ["", "## M4: español frente a inglés (exactitud)", "", "| par | n | " + " | ".join("Laya %s es · en · Δ" % m for m in m4["modelos"]) + " |", "|---|---|" + "---|" * len(m4["modelos"])]
        nombres = sorted({k for v in m4["modelos"].values() for k in v})
        for k in nombres:
            cel = []
            for m in m4["modelos"]:
                x = m4["modelos"][m].get(k)
                cel.append("-" if not x else "%s · %s · %s" % (_n(x["acc_es"]), _n(x["acc_en"]), "%+.3f" % x["d_acc"] if x["d_acc"] is not None else "sin pareja"))
            n = next(v[k]["n"] for v in m4["modelos"].values() if k in v)
            L.append("| %s | %s | %s |" % (k, n, " | ".join(cel)))
        if m4.get("no_medido"):
            L += ["", "No medido: " + "; ".join(m4["no_medido"].values())]
    if vel:
        L += ["", "Velocidad (%d preguntas de massive, %s): %.2f s/pregunta; %s." % (vel["n"], vel["modelo"], vel["seg_por_pregunta"], vel["nota"])]
    return "\n".join(L) + "\n"


def fase_tabla(a):
    sal = Path(a.salida)
    bat = json.loads((sal / "bateria.json").read_text())
    m4 = json.loads((sal / "m4.json").read_text()) if (sal / "m4.json").exists() else None
    vel = json.loads((sal / "velocidad.json").read_text()) if (sal / "velocidad.json").exists() else None
    bases = []
    for r in a.chispa or []:
        nombre, _, ruta = r.partition("=")
        bases.append((nombre, json.loads(Path(ruta).read_text())))
    (sal / "laya-frente-chispa.md").write_text(tabla_md(bat, m4, bases, vel))
    return 0


# ------------------------------------------------------------------ CLI
FASES = {"velocidad": fase_velocidad, "bateria": fase_bateria, "m4": fase_m4, "licencia": fase_licencia, "tabla": fase_tabla}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("fase", choices=sorted(FASES))
    ap.add_argument("--manifiesto", default=str(RAIZ / "sdk" / "python" / "ejemplos" / "bateria.json"))
    ap.add_argument("--salida", required=True)
    ap.add_argument("--modelos", default=",".join(MODELOS))
    ap.add_argument("--falso", action="store_true", help="Laya de mentira (prueba en seco)")
    ap.add_argument("--max-minutos", type=float, default=MAX_MIN)
    ap.add_argument("--tope-filas", type=int, default=None, help="filas por conjunto (por defecto, el que fijó la prueba de velocidad)")
    ap.add_argument("--m4-filas", type=int, default=200, help="pares por conjunto de M4")
    ap.add_argument("--max-len", type=int, default=None)
    ap.add_argument("--hf", default=None, help="caché de HF (hub) de los datos de M4")
    ap.add_argument("--tarjetas", default=None, help="directorio con las tarjetas (por defecto se bajan de HF)")
    ap.add_argument("--chispa", action="append", metavar="NOMBRE=linea-base.json")
    a = ap.parse_args(argv)
    a.modelos = [m for m in a.modelos.split(",") if m]
    Path(a.salida).mkdir(parents=True, exist_ok=True)
    try:
        import torch
        torch.set_num_threads(HILOS)
    except ModuleNotFoundError:
        pass
    try:
        return FASES[a.fase](a)
    except B.ErrorBateria as e:
        print("laya: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
