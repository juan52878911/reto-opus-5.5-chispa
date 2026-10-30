"""Umbrales propuestos para el manifiesto de la batería de regresión, a partir de dos corridas del mismo modelo (M1).

    python -m model.l2.umbrales_bateria --corridas bateria-g8-1.json bateria-g8-2.json [--manifiesto bateria.json] --salida umbrales-propuestos.json

Cada corrida es el `.json` que escribe `chispa evaluar --bateria … --salida PREFIJO` (secciones `global` y `conjuntos`). Para cada
métrica y cada conjunto se mira:
  - el IC95 de la métrica (fracciones: semiancho de Wilson con el `n` del conjunto; es conservador para F1, ECE y cobertura);
  - el ruido entre corridas |m1 − m2| (el servidor es determinista, así que en las métricas de calidad suele ser 0; la latencia no).
El umbral propuesto es el mayor de «semiancho del IC95» y «2 × ruido entre corridas», redondeado hacia arriba a 0,005 (absolutas) o a
0,05 (latencias, relativas: 2 × ruido relativo con suelo en el valor actual del manifiesto). `errores` queda en 0 si ninguna corrida
tuvo errores; `estabilidad` y `delta_conf` solo si las corridas se hicieron con `--robustez` (con el IC95 de la fracción).
El manifiesto no se cambia: la salida tiene la forma del campo `umbrales` (sirve para `--umbrales`) más `detalle` con los números.
"""
import argparse
import json
import math
import sys
from pathlib import Path

FRACCIONES = ("exactitud", "f1_macro", "cobertura", "ece", "escalado", "estabilidad")
ABSOLUTAS = FRACCIONES + ("errores", "mae", "delta_conf")
RELATIVAS = ("p50_ms", "p99_ms")
PASO = 0.005
PASO_REL = 0.05
SUELO_REL = {"p50_ms": 0.5, "p99_ms": 1.0}
SUELO_ABS = {"mae": 0.02, "delta_conf": 0.02}


def semiancho_wilson(p, n, z=1.96):
    if not n:
        return 0.0
    d = 1 + z * z / n
    return z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d


def arriba(x, paso):
    return round(math.ceil(x / paso - 1e-9) * paso, 6)


def proponer(metrica, a, b, n, actual=None):
    """-> dict con los valores de las dos corridas, ic95, ruido y umbral propuesto (None si no hay dato en alguna corrida)."""
    if a is None or b is None:
        return None
    media = (a + b) / 2
    d = {"corrida_1": a, "corrida_2": b, "media": media, "n": n}
    if metrica in RELATIVAS:
        ruido = abs(a - b) / media if media > 0 else 0.0
        d["ruido_rel"] = ruido
        d["umbral"] = arriba(max(2 * ruido, SUELO_REL[metrica], actual or 0.0), PASO_REL)
        return d
    ruido = abs(a - b)
    if metrica in FRACCIONES:
        h = semiancho_wilson(min(max(media, 0.0), 1.0), n)
    elif metrica == "errores":
        h = 0.0 if media == 0 else semiancho_wilson(min(media, 1.0), n)
    else:   # mae, delta_conf: sin varianza por fila en el informe; solo el ruido entre corridas
        h = 0.0
    d.update(ic95_semiancho=h, ruido=ruido)
    if metrica == "errores" and media == 0:
        d["umbral"] = 0.0
    else:
        d["umbral"] = arriba(max(h, 2 * ruido, SUELO_ABS.get(metrica, PASO)), PASO)
    return d


def proponer_umbrales(c1, c2, manifiesto=None):
    """c1, c2: reportes de dos corridas. -> {'umbrales': {...}, 'detalle': {...}, 'avisos': [...]}"""
    avisos = []
    if c1.get("manifiesto") != c2.get("manifiesto"):
        avisos.append("las dos corridas son de manifiestos distintos: %r y %r" % (c1.get("manifiesto"), c2.get("manifiesto")))
    actuales = (manifiesto or {}).get("umbrales", {})
    detalle, umbrales = {}, {}
    secciones = {"global": (c1.get("global", {}), c2.get("global", {}))}
    for nombre in sorted(set(c1.get("conjuntos", {})) & set(c2.get("conjuntos", {}))):
        secciones["conjuntos/" + nombre] = (c1["conjuntos"][nombre], c2["conjuntos"][nombre])
    for nombre in sorted(set(c1.get("conjuntos", {})) ^ set(c2.get("conjuntos", {}))):
        avisos.append("conjunto %r solo está en una de las dos corridas: se ignora" % nombre)
    for sec, (m1, m2) in secciones.items():
        if m1.get("n") != m2.get("n"):
            avisos.append("%s: n = %s y %s: no es la misma muestra" % (sec, m1.get("n"), m2.get("n")))
        n = min(m1.get("n") or 0, m2.get("n") or 0)
        det = {}
        for met in ABSOLUTAS + RELATIVAS:
            actual = (actuales.get("por_conjunto", {}).get(sec.partition("/")[2], {}) if sec != "global" else {}).get(met, actuales.get(met))
            p = proponer(met, m1.get(met), m2.get(met), n, actual if met in RELATIVAS else None)
            if p is not None:
                p["actual"] = actual
                det[met] = p
        detalle[sec] = det
    for met, p in detalle["global"].items():
        umbrales[met] = p["umbral"]
    por_conjunto = {}
    for sec, det in detalle.items():
        if sec == "global":
            continue
        nombre = sec.partition("/")[2]
        dif = {met: p["umbral"] for met, p in det.items() if p["umbral"] != umbrales.get(met)}
        if dif:
            por_conjunto[nombre] = dif
    if por_conjunto:
        umbrales["por_conjunto"] = por_conjunto
    for sec, det in detalle.items():
        for met, p in det.items():
            if p.get("actual") is not None and p["umbral"] > p["actual"] and met in ABSOLUTAS:
                avisos.append("%s/%s: el IC95/ruido pide %.3f y el manifiesto tiene %.3f (una regresión de ese tamaño no se distingue del ruido)"
                              % (sec, met, p["umbral"], p["actual"]))
    return {"version": 1, "origen": [c1.get("fuente"), c2.get("fuente")], "manifiesto": c1.get("manifiesto"),
            "criterio": "máx(semiancho IC95 de Wilson, 2 × |corrida_1 − corrida_2|), redondeado hacia arriba a 0,005; latencias relativas a 0,05",
            "umbrales": umbrales, "avisos": avisos, "detalle": detalle}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--corridas", nargs=2, required=True, metavar="JSON")
    ap.add_argument("--manifiesto", help="bateria.json, solo para comparar con los umbrales actuales (no se modifica)")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    c1, c2 = (json.loads(Path(p).read_text(encoding="utf-8")) for p in a.corridas)
    man = json.loads(Path(a.manifiesto).read_text(encoding="utf-8")) if a.manifiesto else None
    res = proponer_umbrales(c1, c2, man)
    Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(a.salida).write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print("umbrales propuestos en %s: %s" % (a.salida, json.dumps(res["umbrales"], ensure_ascii=False)))
    for av in res["avisos"]:
        print("aviso:", av)
    return 0


if __name__ == "__main__":
    sys.exit(main())
