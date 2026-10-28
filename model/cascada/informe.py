"""T2.7: informe de la cascada L0 → L1 → L2 frente al listón.

    python -m model.cascada.informe --datos DIR --pred DIR [--l2b DIR --l2c DIR] [--fecha AAAA-MM-DD] [--salida DIR]

`--pred`: salida de `model.cascada.capas` (L0/, L1-zs/, L1-proto/). `--l2b`, `--l2c`: carpetas con `pred/<tarea>.jsonl`
y `pred_soporte/<tarea>.jsonl` de las rondas T2.1b (`l2-20261028b`) y T2.2 (`l2-20261028c`). Sin ellas es la prueba en seco:
solo las cascadas L0 → L1-zs y L0 → L1-proto (la última capa, L1, responde siempre).
Escribe `<salida>/<fecha>/informe.md` y `resultados.json`.
"""
import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np

from . import capas as C
from . import cascada as K

RAIZ = C.RAIZ
TAREAS = C.TAREAS
# Latencia esperada por consulta en el i7 (ms) y de dónde sale cada cifra.
COSTOS = {"L0": 0.006, "L0c": 0.006, "conjunta": 30.7, "L1-zs": 0.166, "L1-proto": 0.166, "L2": 30.6}
FUENTES = {
    "L0": "≈ 6 µs/op, `go test -bench L0` sin HTTP, 1 hilo (`server/README.md`)",
    "L1": "166 µs, p99 a 64 tokens (66 reales), potion en Go, 1 hilo (`model/bench/i7/resultados.md`); L1-proto cuesta lo mismo: "
          "una multiplicación por prototipos precalculados en lugar de por los vectores de opción",
    "L2": "30,6 ms, mediana de los p99 a 64 tokens, e5-small int8 podado, 1 hilo (`model/bench/i7/resultados.md`)",
}
FACTOR_LISTON = 0.95   # criterio de T2.2: ≥ 0,95 × la mejor referencia
FORMAS_L2 = [["L0", "L2"], ["L0", "L1-zs", "L2"], ["L0", "L1-proto", "L2"], ["L1-proto", "L2"]]
FORMAS_COMPLETO = [["L0c", "conjunta"], ["conjunta"]]   # con L0 completo; L0c → L2b-sop se añade según haya L2
FORMAS_SECO = [["L0", "L1-zs"], ["L0", "L1-proto"]]
MODOS = ("calidad", "rapida")


def costo(nombre):
    if nombre == "conjunta":
        return COSTOS["conjunta"]   # L0 + L2 + la cabeza: la conjunta calcula las dos capas siempre
    return COSTOS["L2" if nombre.startswith("L2") else nombre]


def referencias(tarea, ruta, maestro):
    """L0, kNN-32 de `model/lineas_base/resultados.json` (los de `informe.md`) y el maestro si se da."""
    d = json.load(open(ruta)).get(tarea, {})
    r = {"L0": d.get("l0_tfidf_lr", {}).get("macro_f1"), "e5_knn32": d.get("e5_knn32", {}).get("macro_f1"),
         "maestro": (maestro or {}).get(tarea)}
    vals = [v for v in r.values() if v is not None]
    r["mejor"] = max(vals) if vals else None
    r["liston"] = FACTOR_LISTON * r["mejor"] if vals else None
    return r


def variantes_l2(l2dirs, tarea):
    """{nombre: preds} de las rondas dadas: «L2b-sop» (con soporte), «L2b» (sin soporte), «L2c-sop», «L2c»."""
    out = {}
    for ronda, d in l2dirs.items():
        for sop in (True, False):
            p = C.leer_l2(d, tarea, sop)
            if p:
                out["L2%s%s" % (ronda, "-sop" if sop else "")] = p
    return out


def evaluar_tarea(tarea, datos, pred, l2dirs, maestro, resultados_base, completo=None):
    train, _, test = C.cargar_tarea(tarea, datos)
    base = {n: C.leer_pred(Path(pred) / n / (tarea + ".jsonl")) for n in ("L0", "L1-zs", "L1-proto")} if pred else {}
    base = {n: p for n, p in base.items() if p}
    if completo:   # L0 con todo train (pred_l0/) y la conjunta (pred/) de `model.l2.conjunta`, mismo test
        base.update({n: C.leer_pred(Path(completo) / d / (tarea + ".jsonl")) for n, d in (("L0c", "pred_l0"), ("conjunta", "pred"))})
        base = {n: p for n, p in base.items() if p}
    l2 = variantes_l2(l2dirs, tarea)
    todas = {**base, **l2}
    clases = K.clases_de(test, todas.values())
    ref = referencias(tarea, resultados_base, maestro)
    res = {"n_test": len(test), "n_clases": len({r["etiqueta"] for r in test}), "referencias": ref,
           "capas_solas": {}, "cascadas": {}}

    def filas_de(nombres):
        return [r for r in test if all(r["id"] in todas[n] for n in nombres)]
    for n in todas:
        f = filas_de([n])
        s = K.sola(K.Capa(n, todas[n], f, clases), f, clases)
        s.update(n=len(f), ms=costo(n))
        res["capas_solas"][n] = s
    formas = []
    if l2:
        for v in l2:
            formas += [[v if x == "L2" else x for x in forma] for forma in FORMAS_L2]
    elif not completo:
        formas = FORMAS_SECO
    if completo:
        formas += FORMAS_COMPLETO + [["L0c", v] for v in l2 if v.endswith("-sop")]
    for forma in formas:
        if any(n not in todas for n in forma):
            continue
        f = filas_de(forma)
        if not f:
            continue
        cs = [K.Capa(n, todas[n], f, clases) for n in forma]
        costos = {n: costo(n) for n in forma}
        solas = {c.nombre: K.sola(c, f, clases)["macro_f1"] for c in cs}
        r = {"n": len(f), "solas": solas, "mejor_sola": max(solas.values()), "oraculo": K.oraculo(cs, f, clases)}
        for modo in MODOS:
            v = K.validar(cs, f, clases, costos, modo)
            v["pasa"] = bool(ref["liston"] is not None and v["macro_f1"] >= ref["liston"])
            v["delta_vs_mejor_sola"] = v["macro_f1"] - r["mejor_sola"]
            r[modo] = v
        res["cascadas"][" → ".join(forma)] = r
    return res


def resumen(tareas):
    """Por cascada y punto de operación: tareas que pasan el listón, que superan a la mejor capa sola y que pierden > 1 punto."""
    nombres = []
    for t in tareas.values():
        nombres += [n for n in t["cascadas"] if n not in nombres]
    out = {}
    for n in nombres:
        for modo in MODOS:
            vs = [t["cascadas"][n][modo] for t in tareas.values() if n in t["cascadas"]]
            if not vs:
                continue
            out["%s — %s" % (n, modo)] = {
                "tareas": len(vs), "pasan": sum(v["pasa"] for v in vs),
                "superan_mejor_capa": sum(v["delta_vs_mejor_sola"] > 0 for v in vs),
                "pierden_mas_de_1_punto": sum(v["delta_vs_mejor_sola"] < -0.01 for v in vs),
            }
    for k, v in out.items():
        refuta = v["superan_mejor_capa"] == 0 or v["pierden_mas_de_1_punto"] >= 2
        v["hipotesis"] = "refutada" if refuta else ("cumple" if v["pasan"] >= 4 else "no cumple")
    return out


def h3(tareas):
    """H3 (T2.2d): la cascada L0c → L2-sop (punto «calidad») queda por debajo de la conjunta sola en ≥ 3 tareas."""
    out = {}
    for n in {n for t in tareas.values() for n in t["cascadas"] if n.startswith("L0c → L2")}:
        filas = {}
        for tn, t in tareas.items():
            if n in t["cascadas"] and "conjunta" in t["cascadas"]:
                c, j = t["cascadas"][n]["calidad"]["macro_f1"], t["cascadas"]["conjunta"]["mejor_sola"]
                filas[tn] = {"cascada": c, "conjunta": j, "por_debajo": bool(c < j)}
        k = sum(f["por_debajo"] for f in filas.values())
        out[n] = {"tareas": filas, "por_debajo": k, "n": len(filas), "cumple": k >= 3}
    return out


def f3(x):
    return "n/d" if x is None else ("%.3f" % x).replace(".", ",")


def frac(v):
    return " / ".join("%d %%" % round(100 * x) for x in v["fraccion"].values())


def escribir_md(res, ruta, cabecera):
    L = list(cabecera)
    for tarea, t in res["tareas"].items():
        ref = t["referencias"]
        L += ["", "## %s (n = %d, %d clases)" % (tarea, t["n_test"], t["n_clases"]), "",
              "Listón: 0,95 × máx(L0 %s, kNN-32 %s, maestro %s) = **%s**." % (
                  f3(ref["L0"]), f3(ref["e5_knn32"]), f3(ref["maestro"]), f3(ref["liston"])), "",
              "| capa sola | n | macro-F1 | exactitud | ms/consulta |", "|---|---|---|---|---|"]
        for n, s in t["capas_solas"].items():
            L.append("| %s | %d | %s | %s | %s |" % (n, s["n"], f3(s["macro_f1"]), f3(s["exactitud"]), str(s["ms"]).replace(".", ",")))
        L += ["", "| cascada | n | mejor capa | oráculo | calidad F1 | pasa | % por capa | ms medio | p99 ms | rápida F1 | pasa | % por capa | ms medio | p99 ms |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for n, r in t["cascadas"].items():
            c, q = r["calidad"], r["rapida"]
            L.append("| %s | %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                n, r["n"], f3(r["mejor_sola"]), f3(r["oraculo"]["macro_f1"]), f3(c["macro_f1"]), "sí" if c["pasa"] else "no", frac(c),
                f3(c["ms_medio"]), f3(c["ms_p99"]), f3(q["macro_f1"]), "sí" if q["pasa"] else "no", frac(q), f3(q["ms_medio"]), f3(q["ms_p99"])))
    L += ["", "## Resumen por cascada", "",
          "| cascada — punto | pasan el listón | superan a su mejor capa | pierden > 1 punto | hipótesis |", "|---|---|---|---|---|"]
    for k, v in res["resumen"].items():
        L.append("| %s | %d/%d | %d/%d | %d/%d | %s |" % (k, v["pasan"], v["tareas"], v["superan_mejor_capa"], v["tareas"],
                                                        v["pierden_mas_de_1_punto"], v["tareas"], v["hipotesis"]))
    for n, h in res.get("h3", {}).items():
        L += ["", "H3 (%s por debajo de la conjunta en ≥ 3 tareas, punto calidad): %d/%d → %s. %s" % (
            n, h["por_debajo"], h["n"], "NO EVALUABLE (menos de 5 tareas)" if h["n"] < 5 else ("CUMPLE" if h["cumple"] else "REFUTADA"),
            "; ".join("%s %s vs %s" % (t, f3(f["cascada"]), f3(f["conjunta"])) for t, f in h["tareas"].items()))]
    Path(ruta).write_text("\n".join(L) + "\n", encoding="utf-8")


def cabecera(a, seco):
    L = ["# T2.7 Cascada L0 → L1 → L2 frente al listón (%s)" % a.fecha, "",
         "Reproducir: `python -m model.cascada.capas …` y `python -m model.cascada.informe …` (ver `model/cascada/aws/arranque.sh`).", ""]
    if seco:
        L += ["**Prueba en seco, sin L2**: no hay predicciones de L2 en esta máquina (están en S3). Solo L0 → L1-zs y L0 → L1-proto, "
              "con L1 como última capa (responde siempre). Las cifras de las cascadas con L2 se miden en la instancia de AWS.", ""]
    if a.completo:
        L += ["**L0c = L0 con todo train** (`pred_l0/` de `model.l2.conjunta`), no la línea base de 32 por clase; «conjunta» = `pred/` de la "
              "misma ejecución. Las cascadas L0c → L2-sop, L0c → conjunta y la conjunta sola se comparan con el mismo L0. La conjunta "
              "cuesta L0 + L2 (%s ms: calcula las dos siempre)." % COSTOS["conjunta"], ""]
    L += ["## Cómo se midió",
          "- Test de `model.datos.convertir` (MASSIVE es, CLINC150 con `oos`→`escalate`, HateCheck-ES, deepset) y `model/herramientas/test.jsonl`. "
          "Los conjuntos del listón humano (ALIA, GoEmotions, MultiPICo, toxicidad Constitución/protestas) **quedan fuera**: no tienen train para L0.",
          "- Capas: L0 = TF-IDF de caracteres + regresión logística (32 por clase, `model/lineas_base`); L1-zs = lo que hace `server/decide/l1.go` "
          "(coseno de potion con «pregunta · opción · descripción», T = 0,05; noul σ(4·cos−2), θ = 0,5); "
          "**L1-proto = capa candidata, no la del servidor**: prototipos por clase (media normalizada del train completo), softmax(coseno/0,05); "
          "L2 = predicciones ya hechas de T2.1b (`b`) y T2.2 (`c`), con soporte (`-sop`) y sin él.",
          "- Cascada: una capa responde si su confianza top-1 es > 0 y ≥ τ; si no pasa a la siguiente; la última responde siempre.",
          "- τ por capa y tarea, **sin mirar el fragmento que se evalúa**: validación cruzada a 2 pliegues sobre test (hash del `id`, semilla %d); "
          "se ajusta en un pliegue y se evalúa en el otro. Las cifras de cascada son la unión de los dos pliegues evaluados." % K.SEMILLA,
          "- Puntos de operación: **calidad** (τ que maximiza el macro-F1 en el pliegue de ajuste) y **rápida** (mayor cobertura de las capas "
          "tempranas con precisión ≥ 0,95 sobre lo que aceptan, ≥ %d aceptadas)." % K.MIN_ACEPTADAS,
          "- Listón = 0,95 × máx(L0, e5 kNN-32, maestro Qwen). L0 y kNN-32 salen de `model/lineas_base/resultados.json` (las cifras de "
          "`informe.md`; coinciden con `model/l2/resultados/ronda3-t22/delta.md`). **Las cifras del maestro Qwen por tarea no están en el repo**: "
          "se da `maestro n/d` y el listón sale de L0 y kNN-32; en `ronda3-t22/LEEME.md` el listón coincide con 0,95 × L0 en massive, CLINC y herramientas.",
          "- Latencia esperada en el i7 (no medida aquí): coste fijo por capa, suma de las capas recorridas. Fuentes: "
          "L0 %s; L1 %s; L2 %s." % (FUENTES["L0"], FUENTES["L1"], FUENTES["L2"]),
          "- Oráculo = la mejor capa por fila (acierta si alguna capa de la cascada acierta): techo, no alcanzable.",
          "- Hipótesis (T2.7): cumple si pasa el listón en ≥ 4 de 5 tareas; se refuta si la cascada no supera a su mejor capa sola en ninguna tarea "
          "o pierde más de 1 punto frente a ella en ≥ 2."]
    return L


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", required=True)
    ap.add_argument("--pred", help="salida de model.cascada.capas (sin ella, solo las capas de --completo y las de L2)")
    ap.add_argument("--completo", help="salida de model.l2.conjunta (pred_l0/ = L0 con todo train, pred/ = conjunta): añade L0c → L2-sop, L0c → conjunta y conjunta sola")
    ap.add_argument("--l2b", help="carpeta con pred/ y pred_soporte/ de T2.1b (l2-20261028b)")
    ap.add_argument("--l2c", help="ídem de T2.2 (l2-20261028c)")
    ap.add_argument("--tareas", default=",".join(TAREAS))
    ap.add_argument("--fecha", default=str(date.today()))
    ap.add_argument("--salida", default=str(C.AQUI / "resultados"))
    ap.add_argument("--base", default=str(RAIZ / "model" / "lineas_base" / "resultados.json"))
    ap.add_argument("--maestro", help="JSON {tarea: macro-F1} del maestro Qwen, si se tiene")
    a = ap.parse_args(argv)
    l2dirs = {r: d for r, d in (("b", a.l2b), ("c", a.l2c)) if d}
    maestro = json.load(open(a.maestro)) if a.maestro else None
    res = {"fecha": a.fecha, "costos_ms": COSTOS, "fuentes": FUENTES, "semilla": K.SEMILLA, "tareas": {}}
    for tarea in a.tareas.split(","):
        res["tareas"][tarea] = evaluar_tarea(tarea, a.datos, a.pred, l2dirs, maestro, a.base, a.completo)
    res["resumen"] = resumen(res["tareas"])
    res["h3"] = h3(res["tareas"])
    out = Path(a.salida) / a.fecha
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "resultados.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    escribir_md(res, out / "informe.md", cabecera(a, not l2dirs and not a.completo))
    print("escrito", out)


if __name__ == "__main__":
    main()
