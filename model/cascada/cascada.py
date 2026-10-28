"""T2.7: la cascada del servidor (`server/decide/cascada.go`) sobre predicciones ya hechas.

Cada capa responde si su confianza top-1 es > 0 y ≥ τ; si no, pasa a la siguiente, y la última responde siempre
(en el servidor la última escala; aquí se juzga su respuesta). El coste de una fila es la suma de los ms de las capas que
recorrió, con un coste fijo por capa (`costos`): la latencia esperada en el i7, no la medida en esta máquina.

τ se elige **sin mirar el fragmento que se evalúa**: validación cruzada de 2 pliegues sobre test, partiendo por hash del
`id` con semilla fija; τ se ajusta en un pliegue y se evalúa en el otro, y al revés (`validar`).
Dos puntos de operación (`elegir`):
- `calidad`: τ que maximiza el macro-F1 en el pliegue de ajuste (empate: el de menor coste medio);
- `rapida`: por capa temprana, en orden, el τ de mayor cobertura cuya precisión sobre lo que acepta (de las filas que
  llegan a esa capa) sea ≥ 0,95, con al menos MIN_ACEPTADAS filas aceptadas; si ninguno, esa capa no responde (τ = ∞).
"""
import hashlib
import itertools

import numpy as np

SEMILLA = 0
PRECISION_RAPIDA = 0.95
MIN_ACEPTADAS = 5
CUANTILES = 41
MAX_REJILLA = 5000     # tamaño máximo de la búsqueda conjunta de `calidad`; por encima, descenso por coordenadas


def pliegue(id_, semilla=SEMILLA, k=2):
    """Pliegue (0..k-1) de una fila por hash de su id."""
    return int(hashlib.sha256(("%s:%s" % (semilla, id_)).encode()).hexdigest()[:8], 16) % k


class Capa:
    """Top-1 y confianza de una capa para una lista de filas. `preds`: {id: {"probs": {...}, "sin_opinion"?: bool}}."""

    def __init__(self, nombre, preds, filas, clases):
        self.nombre = nombre
        idx = {c: i for i, c in enumerate(clases)}
        self.top = np.zeros(len(filas), int)
        self.conf = np.zeros(len(filas))
        for j, r in enumerate(filas):
            p = preds[r["id"]]
            if p.get("sin_opinion") or not p.get("probs"):
                continue
            c, v = max(p["probs"].items(), key=lambda kv: kv[1])   # primer máximo, como metricas.top1
            self.top[j], self.conf[j] = idx[c], v


def clases_de(filas, capas_preds):
    cs = {r["etiqueta"] for r in filas}
    for preds in capas_preds:
        for p in preds.values():
            cs.update(p.get("probs") or {})
    return sorted(cs)


def macro_f1(y, p, k):
    """Macro-F1 sobre las clases que aparecen en y o en p (misma definición que `model.evaluacion.metricas`)."""
    tc, pc = np.bincount(y, minlength=k), np.bincount(p, minlength=k)
    tp = np.bincount(y[y == p], minlength=k)
    d = tc + pc
    m = d > 0
    return float(np.mean(2 * tp[m] / d[m])) if m.any() else float("nan")


def decidir(capas, taus, costos, filas=None):
    """Recorre las capas en orden. -> (decision[int], capa[int, índice de la que respondió], coste[ms]).
    `taus`: un valor por capa salvo la última (que responde siempre)."""
    n = len(capas[0].top)
    dec, resp, coste = np.zeros(n, int), np.full(n, len(capas) - 1), np.zeros(n)
    vivo = np.ones(n, bool)
    for i, c in enumerate(capas):
        coste[vivo] += costos[c.nombre]
        acepta = vivo.copy() if i == len(capas) - 1 else vivo & (c.conf > 0) & (c.conf >= taus[i])
        dec[acepta], resp[acepta] = c.top[acepta], i
        vivo &= ~acepta
    return dec, resp, coste


def candidatos(conf):
    """Rejilla de τ: cuantiles de la confianza, 0 (acepta todo lo que opine) e ∞ (no acepta nada)."""
    q = np.unique(np.quantile(conf[conf > 0], np.linspace(0, 1, CUANTILES))) if (conf > 0).any() else np.array([])
    return list(np.unique(np.concatenate([[0.0], q]))) + [np.inf]


def _sub(capas, m):
    out = []
    for c in capas:
        s = Capa.__new__(Capa)
        s.nombre, s.top, s.conf = c.nombre, c.top[m], c.conf[m]
        out.append(s)
    return out


def elegir(capas, y, k, costos, modo):
    """τ por capa (salvo la última) en las filas dadas. modo: «calidad» o «rapida»."""
    n_t = len(capas) - 1
    if n_t == 0:
        return []
    cands = [candidatos(c.conf) for c in capas[:n_t]]
    if modo == "rapida":
        taus, vivo = [], np.ones(len(y), bool)
        for i in range(n_t):
            c, mejor, cob = capas[i], np.inf, 0
            for t in cands[i]:
                a = vivo & (c.conf > 0) & (c.conf >= t)
                na = int(a.sum())
                if na >= MIN_ACEPTADAS and (c.top[a] == y[a]).mean() >= PRECISION_RAPIDA and na > cob:
                    mejor, cob = t, na
            taus.append(mejor)
            vivo &= ~((c.conf > 0) & (c.conf >= mejor))
        return taus
    if modo != "calidad":
        raise ValueError("modo: calidad o rapida, no %r" % modo)

    def valor(taus):
        d, _, co = decidir(capas, taus, costos)
        return (macro_f1(y, d, k), -float(co.mean()))
    tam = int(np.prod([len(c) for c in cands]))
    if tam <= MAX_REJILLA:
        return list(max(itertools.product(*cands), key=valor))
    taus = [c[-1] for c in cands]   # descenso por coordenadas desde «ninguna temprana responde»
    for _ in range(3):
        for i in range(n_t):
            taus[i] = max(cands[i], key=lambda t: valor(taus[:i] + [t] + taus[i + 1:]))
    return taus


def validar(capas, filas, clases, costos, modo, semilla=SEMILLA):
    """Validación cruzada a 2 pliegues sobre `filas` (test). -> dict con las métricas de la cascada y los τ de cada pliegue."""
    k = len(clases)
    idx = {c: i for i, c in enumerate(clases)}
    y = np.array([idx[r["etiqueta"]] for r in filas])
    pl = np.array([pliegue(r["id"], semilla) for r in filas])
    dec, resp, coste = np.zeros(len(y), int), np.zeros(len(y), int), np.zeros(len(y))
    taus = []
    for f in (0, 1):
        aj, ev = pl != f, pl == f   # ajusta en el otro pliegue, evalúa en éste
        t = elegir(_sub(capas, aj), y[aj], k, costos, modo)
        taus.append([None if np.isinf(v) else float(v) for v in t])
        d, r, c = decidir(_sub(capas, ev), t, costos)
        dec[ev], resp[ev], coste[ev] = d, r, c
    return {
        "macro_f1": macro_f1(y, dec, k), "exactitud": float((dec == y).mean()), "n": int(len(y)),
        "fraccion": {c.nombre: float((resp == i).mean()) for i, c in enumerate(capas)},
        "ms_medio": float(coste.mean()), "ms_p99": float(np.percentile(coste, 99, method="higher")),
        "taus": taus, "pliegues": [int((pl == 0).sum()), int((pl == 1).sum())],
    }


def sola(capa, filas, clases):
    """Macro-F1 y exactitud de una capa sola."""
    idx = {c: i for i, c in enumerate(clases)}
    y = np.array([idx[r["etiqueta"]] for r in filas])
    return {"macro_f1": macro_f1(y, capa.top, len(clases)), "exactitud": float((capa.top == y).mean())}


def oraculo(capas, filas, clases):
    """Techo: la mejor capa por fila (si alguna acierta, acierta; si no, la respuesta de la primera capa)."""
    idx = {c: i for i, c in enumerate(clases)}
    y = np.array([idx[r["etiqueta"]] for r in filas])
    ok = np.any([c.top == y for c in capas], axis=0)
    dec = np.where(ok, y, capas[0].top)
    return {"macro_f1": macro_f1(y, dec, len(clases)), "exactitud": float(ok.mean())}
