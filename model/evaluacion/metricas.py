"""Métricas de `chispa eval` con numpy puro. Cada función recibe arreglos ya unidos por id."""
import numpy as np

N_CUBOS = 15


def exactitud(y, p):
    return float(np.mean([a == b for a, b in zip(y, p)])) if len(y) else float("nan")


def macro_f1(y, p):
    """Media del F1 por clase sobre las clases que aparecen en y o en p (F1 = 0 si no hay aciertos)."""
    clases = sorted(set(y) | set(p))
    fs = []
    for c in clases:
        tp = sum(1 for a, b in zip(y, p) if a == c and b == c)
        fp = sum(1 for a, b in zip(y, p) if a != c and b == c)
        fn = sum(1 for a, b in zip(y, p) if a == c and b != c)
        d = 2 * tp + fp + fn
        fs.append(2 * tp / d if d else 0.0)
    return float(np.mean(fs)) if fs else float("nan")


def ece(conf, acierto, cubos=N_CUBOS):
    """ECE con `cubos` de igual ancho sobre (0,1], cubo = (k/cubos, (k+1)/cubos]; conf=0 va al primero."""
    conf = np.asarray(conf, float)
    ok = np.asarray(acierto, float)
    if len(conf) == 0:
        return float("nan")
    idx = np.clip(np.ceil(conf * cubos - 1e-12).astype(int) - 1, 0, cubos - 1)
    total = 0.0
    for k in range(cubos):
        m = idx == k
        if m.any():
            total += m.sum() / len(conf) * abs(ok[m].mean() - conf[m].mean())
    return float(total)


def brier(P, Y):
    """Brier multiclase: media de sum_k (p_k - y_k)^2. P y Y son matrices n x K (Y one-hot)."""
    P, Y = np.asarray(P, float), np.asarray(Y, float)
    return float(np.mean(np.sum((P - Y) ** 2, axis=1))) if len(P) else float("nan")


def cobertura_a_precision(conf, acierto, objetivo):
    """Mayor cobertura con umbral sobre la confianza (se acepta conf >= umbral) y precisión >= objetivo.

    Devuelve {"cobertura", "umbral"}; cobertura 0 y umbral None si ningún umbral llega al objetivo."""
    conf = np.asarray(conf, float)
    ok = np.asarray(acierto, float)
    n = len(conf)
    mejor = {"cobertura": 0.0, "umbral": None}
    for t in np.unique(conf):
        m = conf >= t
        if ok[m].mean() >= objetivo - 1e-12 and m.sum() / n > mejor["cobertura"]:
            mejor = {"cobertura": float(m.sum() / n), "umbral": float(t)}
    return mejor


def auroc(positivo, puntuacion):
    """AUROC por rangos (Mann-Whitney, empates a medio punto). None si falta una de las dos clases."""
    pos = np.asarray(positivo, bool)
    s = np.asarray(puntuacion, float)
    n1, n0 = int(pos.sum()), int((~pos).sum())
    if n1 == 0 or n0 == 0:
        return None
    gt = (s[pos][:, None] > s[~pos][None, :]).sum()
    eq = (s[pos][:, None] == s[~pos][None, :]).sum()
    return float((gt + 0.5 * eq) / (n1 * n0))


def latencia(ms):
    ms = [m for m in ms if m is not None]
    if not ms:
        return None
    return {"p50_ms": float(np.percentile(ms, 50)), "p99_ms": float(np.percentile(ms, 99))}


def deriva(pa, pb):
    """pa, pb: listas de dicts de probs por id. Tasa de cambio del top-1 y variación total media."""
    cambios, tv = [], []
    for a, b in zip(pa, pb):
        cambios.append(top1(a)[0] != top1(b)[0])
        claves = set(a) | set(b)
        tv.append(0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in claves))
    return {"tasa_cambio_top1": float(np.mean(cambios)), "variacion_total_media": float(np.mean(tv))}


def top1(probs):
    """(opción, confianza); empates por orden de aparición en el dict."""
    k = max(probs, key=lambda c: probs[c])
    return k, probs[k]
