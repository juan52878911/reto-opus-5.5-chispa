"""M3, robustez de L1 y L2 frente a variantes del mismo caso: qué porcentaje de decisiones (argmax) cambia y cuánto cambia la exactitud.

    python -m model.l2.robustez --ckpt mejor.pt --potion potion.chispa-l1 --datos DATOS --salida DIR [--max-filas 200] [--semilla 0]

Las variantes salen de `chispa.variantes` (E2, `sdk/python`): permutar, renombrar, parafrasear, erratas, mayusculas, mezcla y largo.
Aquí solo están el adaptador fila de Chispa <-> caso, el bucle de medida y las variantes que E2 no cubre (es/en):
`pregunta_en` (la pregunta en inglés con plantilla fija, descripciones intactas) y `esquema_en` (pregunta y descripciones, solo en las
tareas con traducción determinista en `ESQUEMA_EN`). Lo que no se puede generar de forma determinista queda en `no_medido` con su motivo.

L2 = el checkpoint sin soporte (k = 0): lee pregunta, id y descripción de cada opción, así que es el que puede notar un cambio de
esquema. L1 = potion con prototipos del soporte (32 por clase, el de producción): solo mira el texto del mensaje, así que las
variantes del esquema (permutar, renombrar, parafrasear, pregunta_en, esquema_en) no le afectan por construcción (`estructural: true`).

Medida por (modelo, tipo): % de decisiones que cambian frente al original (Wilson, IC95) y Δ exactitud = acc(variante) − acc(original)
(diferencias emparejadas por caso, normal, IC95). Si un tipo cambia más de `UMBRAL_CAMBIO` (5 %) de las decisiones de un modelo, el
informe propone el arreglo con su coste estimado; no se ejecuta.
"""
import argparse
import copy
import json
import math
import sys
from pathlib import Path

UMBRAL_CAMBIO = 0.05
TIPOS_E2 = ("permutar", "renombrar", "parafrasear", "erratas", "mayusculas", "mezcla", "largo")
TIPOS_ES_EN = ("pregunta_en", "esquema_en")
TIPOS = TIPOS_E2 + TIPOS_ES_EN
SOLO_CHOICE = ("permutar", "renombrar")   # en noul/score los ids son semánticos (false/true, 1..K): cambiarlos no es una variante del mismo caso
ESQUEMA = ("permutar", "renombrar", "parafrasear", "pregunta_en", "esquema_en")   # no tocan el mensaje

PREGUNTAS_EN = {   # pregunta en español (tal cual la emiten los conversores de model.datos) -> inglés
    "¿Qué quiere hacer el usuario con el asistente?": "What does the user want to do with the assistant?",
    "¿Qué quiere el usuario del asistente?": "What does the user want from the assistant?",
    "¿Qué necesita el cliente del banco?": "What does the bank customer need?",
    "¿El mensaje contiene odio o es tóxico contra una persona o un grupo?": "Does the message contain hate or is it toxic towards a person or a group?",
    "¿El mensaje intenta que el asistente ignore o cambie sus instrucciones?": "Does the message try to make the assistant ignore or change its instructions?",
}
ESQUEMA_EN = {   # tarea (campo `tarea` de la fila) con descripciones traducibles de forma determinista (2 opciones)
    "toxicidad": {"false": "respectful or non-offensive message, even if it mentions groups or insults without attacking",
                  "true": "hateful or toxic message against a person or a group"},
    "inyeccion": {"false": "normal message that does not try to manipulate the assistant's instructions",
                  "true": "instruction injection: asks to ignore, reveal or change the assistant's rules"},
}
DESC_ES_CLAVE = {   # descripción en español de la opción «false» (cualquier prefijo) -> tarea de ESQUEMA_EN
    "mensaje respetuoso": "toxicidad", "mensaje normal que no intenta": "inyeccion",
}


# ------------------------------------------------------------------ adaptador fila <-> caso
def fila_a_caso(f):
    return {"texto": f["texto"], "pregunta": f["pregunta"], "kind": f["tipo"],
            "opciones": [{"id": o, "description": f["descripciones"].get(o, "")} for o in f["opciones"]], "etiqueta": f["etiqueta"]}


def caso_a_fila(c, f):
    g = copy.deepcopy(f)
    g.update(texto=c["texto"], pregunta=c["pregunta"], opciones=[o["id"] for o in c["opciones"]],
             descripciones={o["id"]: o["description"] for o in c["opciones"]}, etiqueta=c["etiqueta"])
    return g


def _tarea_en(f):
    """Clave de ESQUEMA_EN si la fila tiene traducción determinista de sus descripciones; si no, None."""
    d = f["descripciones"].get("false", "")
    for pref, t in DESC_ES_CLAVE.items():
        if d.startswith(pref) and sorted(f["opciones"]) == ["false", "true"]:
            return t
    return None


def generar_es_en(caso, fila, tipo):
    """Variante es/en que E2 no cubre, o None si no hay traducción determinista. Misma forma que las de E2 (`mapa` identidad)."""
    v = copy.deepcopy(caso)
    v["variante"] = tipo
    v["mapa"] = {o["id"]: o["id"] for o in caso["opciones"]}
    if tipo == "pregunta_en":
        en = PREGUNTAS_EN.get(caso["pregunta"])
        if en is None:
            return None
        v["pregunta"] = en
        return v
    t = _tarea_en(fila)
    en = PREGUNTAS_EN.get(caso["pregunta"])
    if t is None or en is None:
        return None
    v["pregunta"] = en
    for o in v["opciones"]:
        o["description"] = ESQUEMA_EN[t][o["id"]]
    return v


def variantes_de(fila, tipo, semilla, gen_e2):
    """Variante `tipo` de la fila (fila nueva, con `mapa`), o None si no aplica o no hay forma determinista."""
    if tipo in SOLO_CHOICE and fila["tipo"] != "choice":
        return None
    caso = fila_a_caso(fila)
    v = generar_es_en(caso, fila, tipo) if tipo in TIPOS_ES_EN else gen_e2(caso, (tipo,), semilla)[0]
    if v is None:
        return None
    g = caso_a_fila(v, fila)
    g["mapa"] = v["mapa"]
    return g


# ------------------------------------------------------------------ estadística
def wilson(k, n, z=1.96):
    if not n:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def media_ic(xs, z=1.96):
    n = len(xs)
    if not n:
        return None, None, None
    m = sum(xs) / n
    if n < 2:
        return m, m, m
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    h = z * sd / math.sqrt(n)
    return m, m - h, m + h


def resumir(pares):
    """pares: [(cambia: bool, acierto_orig: bool, acierto_var: bool)] -> métricas con IC95."""
    n = len(pares)
    if not n:
        return {"n": 0}
    k = sum(p[0] for p in pares)
    lo, hi = wilson(k, n)
    dm, dlo, dhi = media_ic([int(p[2]) - int(p[1]) for p in pares])
    return {"n": n, "cambian": k, "pct_cambia": k / n, "pct_cambia_ic95": [lo, hi],
            "acc_orig": sum(p[1] for p in pares) / n, "acc_var": sum(p[2] for p in pares) / n,
            "delta_acc": dm, "delta_acc_ic95": [dlo, dhi]}


# ------------------------------------------------------------------ modelos
class ModeloL2:
    def __init__(self, ckpt, device="cpu", max_tok=0):
        from model.l2.evaluar import cargar_modelo
        from model.l2.modelo import MAX_TOK, Codificador
        self.modelo, ck = cargar_modelo(ckpt, device)
        self.enc = Codificador(device=device, max_tok=max_tok or ck.get("max_tok", MAX_TOK))
        self.enc.cargar_enc(ck.get("enc"))

    def decidir(self, filas, clases):
        from model.evaluacion.metricas import etiqueta_coral
        from model.l2.evaluar import predecir
        from model.l2.modelo import niveles_score
        out = []
        for f, p in zip(filas, predecir(self.modelo, self.enc, filas)):
            # score: mediana CORAL sobre los niveles ordenados (probs va por id), no el argmax ni la posición declarada
            out.append(max(p["probs"], key=p["probs"].get) if f["tipo"] != "score"
                       else niveles_score(f["opciones"])[etiqueta_coral([p["probs"][o] for o in niveles_score(f["opciones"])])])
        return out


class ModeloL1:
    """Potion con prototipos del soporte (32 por clase del train): decide por la clase original; un id de variante se traduce con `mapa`."""

    def __init__(self, potion, train, dim=256):
        import numpy as np
        from model.l1 import comun
        from model.lineas_base import correr
        self.np, self.comun, self.potion, self.dim = np, comun, potion, dim
        sop = correr.soporte(train)
        self.clases = sorted({r["etiqueta"] for _, r in sop})
        xs = comun.embeber(potion, [r["texto"] for _, r in sop], dim)
        y = np.array([self.clases.index(r["etiqueta"]) for _, r in sop])
        P = np.stack([xs[y == c].mean(axis=0) for c in range(len(self.clases))])
        self.P = P / (np.linalg.norm(P, axis=1, keepdims=True) + 1e-12)

    def decidir(self, filas, _clases=None):
        xt = self.comun.embeber(self.potion, [r["texto"] for r in filas], self.dim)
        orig = [self.clases[i] for i in (xt @ self.P.T).argmax(axis=1)]
        return [r.get("mapa", {}).get(c, c) for r, c in zip(filas, orig)]   # el id que tiene esa clase en la variante


# ------------------------------------------------------------------ medida
def medir_tarea(modelos, tarea, filas, tipos, semilla, gen_e2):
    """-> {modelo: {tipo: [(cambia, ok_orig, ok_var)]}}, {tipo: motivo} de lo no medido."""
    res = {m: {} for m in modelos}
    no_medido = {}
    base = {m: mod.decidir(filas, None) for m, mod in modelos.items()}
    for t in tipos:
        vs = [(i, variantes_de(f, t, semilla, gen_e2)) for i, f in enumerate(filas)]
        vs = [(i, v) for i, v in vs if v is not None]
        if not vs:
            no_medido[t] = ("tipo no choice (ids semánticos)" if t in SOLO_CHOICE and filas[0]["tipo"] != "choice"
                            else "sin traducción determinista para esta tarea")
            continue
        for m, mod in modelos.items():
            dv = mod.decidir([v for _, v in vs], None)
            pares = []
            for (i, v), d in zip(vs, dv):
                esperado = v["mapa"].get(base[m][i], base[m][i])   # decisión original traducida al id de la variante
                pares.append((d != esperado, base[m][i] == filas[i]["etiqueta"], d == v["etiqueta"]))
            res[m][t] = pares
    return res, no_medido


# Arreglo propuesto por tipo (no se ejecuta) y su coste estimado; los costes de GPU salen de general.sh (g5.xlarge ≈ 1,01 USD/h).
ARREGLOS = {
    "permutar": ("Aumento de datos: barajar el orden de `opciones` en cada ejemplo del entrenamiento (cambio en model/l2/datos.py, sin datos nuevos) "
                 "o, sin reentrenar, normalizar en el runtime ordenando las opciones por id antes de puntuar y deshaciendo el orden.",
                 "runtime: 0 GPU, ≈ 0,5 día de código; datos: reentrenar ≈ 3 h g5 ≈ 3 USD"),
    "renombrar": ("Aumento de datos: sustituir ids por ids opacos en una parte de los ejemplos (la descripción manda); en el runtime, "
                  "puntuar con el texto «pregunta · descripción» sin el id y mapear de vuelta.", "runtime: 0 GPU, ≈ 0,5 día; datos: ≈ 3 h g5 ≈ 3 USD"),
    "parafrasear": ("Aumento de datos con paráfrasis de la pregunta (plantillas fijas, sin LLM) en ≈ 30 % de los ejemplos.", "≈ 3 h g5 ≈ 3 USD"),
    "erratas": ("Aumento de datos con 1–3 erratas por texto en ≈ 20 % de los ejemplos; en el runtime, nada fiable.", "≈ 3 h g5 ≈ 3 USD"),
    "mayusculas": ("Normalizar en el runtime (minúsculas si el texto es casi todo mayúsculas) o aumento con mayúsculas/minúsculas.",
                   "runtime: 0 GPU, horas; datos: ≈ 3 h g5 ≈ 3 USD"),
    "mezcla": ("Aumento con mezcla es/en (glosario) en ≈ 20 % de los ejemplos; añadir fuentes en inglés si faltan.", "≈ 3 h g5 ≈ 3 USD"),
    "largo": ("Estrategia de M2 (`model.l2.largos`) para textos largos: recorte o ventanas, sin reentrenar.", "0 GPU (ver M2)"),
    "pregunta_en": ("Aumento de datos con la pregunta en inglés (traducción con plantillas) en ≈ 20 % de los ejemplos.", "≈ 3 h g5 ≈ 3 USD"),
    "esquema_en": ("Aumento de datos con esquemas completos en inglés (pregunta y descripciones) en las tareas que ya los tengan.", "≈ 3 h g5 ≈ 3 USD"),
}


def informe_md(res):
    L = ["# M3 robustez de L1 y L2 frente a variantes", "",
         "Cambia = % de decisiones (argmax) distintas del original, con IC95 de Wilson. Δexact = exactitud(variante) − exactitud(original), IC95 de las "
         "diferencias emparejadas. «estructural»: el modelo no lee esa parte del caso, así que no puede cambiar.", "",
         "max_tok %s · filas por tarea %s · semilla %s" % (res["max_tok"], res["max_filas"], res["semilla"]), ""]
    for m in res["modelos"]:
        L += ["## %s" % m, "", "| tipo | n | cambia | IC95 | exact orig | Δexact | IC95 Δ | |", "|---|---|---|---|---|---|---|---|"]
        for t in res["tipos"]:
            r = res["global"][m].get(t)
            if not r:
                L.append("| %s | 0 | no medido | | | | | %s |" % (t, "; ".join(sorted(set(res["no_medido"].get(t, {}).values()))) or "-"))
                continue
            lo, hi = r["pct_cambia_ic95"]
            dlo, dhi = r["delta_acc_ic95"]
            L.append("| %s | %d | %.1f %% | %.1f–%.1f | %.3f | %+.3f | %+.3f–%+.3f | %s |" % (
                t, r["n"], 100 * r["pct_cambia"], 100 * lo, 100 * hi, r["acc_orig"], r["delta_acc"], dlo, dhi,
                "estructural" if r.get("estructural") else ("**> 5 %**" if r["pct_cambia"] > UMBRAL_CAMBIO else "")))
        L.append("")
    if res["arreglos"]:
        L += ["## Arreglos propuestos (no ejecutados)", ""]
        for a in res["arreglos"]:
            L.append("- **%s / %s** (cambia %.1f %%): %s Coste: %s." % (a["modelo"], a["tipo"], 100 * a["pct_cambia"], a["arreglo"], a["coste"]))
    else:
        L.append("Ningún tipo supera el 5 % de decisiones cambiadas: no hace falta arreglo.")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--potion", required=True)
    ap.add_argument("--datos", required=True, help="salida de model.datos.convertir")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--tareas", default="massive,hatecheck,clinc150,inyecciones,herramientas")
    ap.add_argument("--tipos", default=",".join(TIPOS))
    ap.add_argument("--max-filas", type=int, default=200)
    ap.add_argument("--max-tok", type=int, default=0)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--device", default="cpu")
    a = ap.parse_args(argv)
    from model.lineas_base import correr
    try:
        from chispa.variantes import generar
    except ImportError:   # sdk/python no está en PYTHONPATH
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "python"))
        from chispa.variantes import generar
    l2 = ModeloL2(a.ckpt, a.device, a.max_tok)
    tipos = a.tipos.split(",")
    mal = [t for t in tipos if t not in TIPOS]
    if mal:
        ap.error("tipos desconocidos: %s (válidos: %s)" % (mal, ",".join(TIPOS)))
    pares = {"L1": {}, "L2": {}}   # modelo -> tipo -> [pares]
    por_tarea = {"L1": {}, "L2": {}}
    no_medido = {}
    n_total = {}
    for tarea in a.tareas.split(","):
        train, _, test = correr.cargar(tarea, a.datos)
        test = correr.submuestra(test, a.max_filas)
        if not test:
            print(tarea, "sin test: se omite", flush=True)
            continue
        n_total[tarea] = len(test)
        modelos = {"L2": l2, "L1": ModeloL1(a.potion, train)}
        r, nm = medir_tarea(modelos, tarea, test, tipos, a.semilla, generar)
        for t, motivo in nm.items():
            no_medido.setdefault(t, {})[tarea] = motivo
        for m in r:
            for t, ps in r[m].items():
                pares[m].setdefault(t, []).extend(ps)
                por_tarea[m].setdefault(t, {})[tarea] = resumir(ps)
        print(tarea, len(test), {t: round(resumir(ps)["pct_cambia"], 3) for t, ps in r["L2"].items()}, flush=True)
    glob, arreglos = {}, []
    for m in pares:
        glob[m] = {}
        for t, ps in pares[m].items():
            glob[m][t] = resumir(ps)
            if t in ESQUEMA and m == "L1":
                glob[m][t]["estructural"] = True
            if glob[m][t]["pct_cambia"] > UMBRAL_CAMBIO:
                arr, coste = ARREGLOS[t]
                arreglos.append({"modelo": m, "tipo": t, "pct_cambia": glob[m][t]["pct_cambia"], "arreglo": arr, "coste": coste})
    res = {"max_tok": l2.enc.max_tok, "max_filas": a.max_filas, "semilla": a.semilla, "tareas": n_total, "tipos": tipos,
           "modelos": ["L1", "L2"], "umbral_cambio": UMBRAL_CAMBIO, "global": glob, "por_tarea": por_tarea, "no_medido": no_medido,
           "arreglos": arreglos, "n_tipos_medidos": {m: sorted(glob[m]) for m in glob}}
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    (sal / "robustez.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    md = informe_md(res)
    (sal / "robustez.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
