"""M6, L1 frente a L2: macro-F1 de L1 (potion con prototipos, el de producción) y de L2 (el checkpoint) sobre las mismas tareas y
las mismas particiones de test que `model.l1.evaluar` (`model.lineas_base.correr.cargar`).

    python -m model.l1.frente_l2 --potion /tmp/potion.chispa-l1 --ckpt mejor.pt --datos /tmp/lb_datos --salida DIR [--k 32] [--max-filas N]

L1 = sistema `proto` de `evaluar.tarea_modelo` (soporte de 32 por clase del train, coseno contra el prototipo, softmax con T = 0,02).
L2 = el checkpoint con prototipos del mismo soporte (`SoporteEval`, k = 32, el de T1.7a) y, aparte, sin soporte (k = 0). La razón
de la fase 3 es L1/L2 con el mismo soporte (k = 32): por tarea y su media, criterio ≥ 0,90. La macro-F1 de los dos sale de `chispa_eval`
sobre las mismas filas (la misma función que usa `correr.evaluar`). Con `--max-filas` las dos usan las primeras N filas de cada test.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import comun
from . import evaluar as ev

CRITERIO = 0.90


def razon(f1_l1, f1_l2):
    """None si L2 saca 0 (la razón no está definida: se cuenta aparte y no entra en la media)."""
    return f1_l1 / f1_l2 if f1_l2 > 0 else None


def resumen(por_tarea, clave="k"):
    """Media de las razones definidas, cuántas son y si cumple el criterio; aparte, las tareas por debajo y las sin razón."""
    rs = [t[clave]["razon"] for t in por_tarea.values() if t[clave]["razon"] is not None]
    media = sum(rs) / len(rs) if rs else None
    return {"media": media, "n_tareas": len(rs), "cumple": bool(rs) and media >= CRITERIO,
            "tareas_bajo_criterio": sorted(t for t, v in por_tarea.items() if v[clave]["razon"] is not None and v[clave]["razon"] < CRITERIO),
            "tareas_sin_razon": sorted(t for t, v in por_tarea.items() if v[clave]["razon"] is None)}


def informe_md(res, k):
    lin = ["# M6 L1 frente a L2", "", "L1 = potion con prototipos (32 por clase). L2 = checkpoint con k = %d y sin soporte. Mismo test por tarea." % k, "",
           "| tarea | n test | L1 | L2 k=%d | L1/L2 | L2 k=0 | L1/L2(k=0) |" % k, "|" + "---|" * 7]
    for t, v in res["tareas"].items():
        r = lambda x: "-" if x is None else "%.3f" % x
        lin.append("| %s | %d | %.3f | %.3f | %s | %.3f | %s |" % (t, v["n"], v["l1"], v["k"]["l2"], r(v["k"]["razon"]), v["k0"]["l2"], r(v["k0"]["razon"])))
    for nombre, clave in (("k = %d (criterio de la fase 3)" % k, "k"), ("k = 0", "k0")):
        r = res["resumen_" + clave]
        lin.append("")
        lin.append("Media L1/L2 con L2 %s: **%s** (%d tareas) → %s el criterio ≥ %.2f%s%s" % (
            nombre, "-" if r["media"] is None else "%.3f" % r["media"], r["n_tareas"], "cumple" if r["cumple"] else "NO cumple", CRITERIO,
            "" if not r["tareas_bajo_criterio"] else "; por debajo: %s" % ", ".join(r["tareas_bajo_criterio"]),
            "" if not r["tareas_sin_razon"] else "; sin razón (L2 = 0): %s" % ", ".join(r["tareas_sin_razon"])))
    return "\n".join(lin) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--potion", required=True)
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--datos", default=comun.DATOS)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--tareas", default=",".join(comun.TAREAS))
    ap.add_argument("--k", type=int, default=32)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--max-tok", type=int, default=0)
    ap.add_argument("--max-filas", type=int, default=0, help="tope de filas por test (0 = todas); solo para pruebas en seco")
    a = ap.parse_args(argv)
    from model.evaluacion import chispa_eval as CE
    from model.l2.evaluar import cargar_modelo, predecir, train_por_conjunto
    from model.l2.modelo import MAX_TOK, Codificador, SoporteEval
    from model.lineas_base import correr
    modelo, ck = cargar_modelo(a.ckpt, a.device)
    enc = Codificador(device=a.device, max_tok=a.max_tok or ck.get("max_tok", MAX_TOK))
    enc.cargar_enc(ck.get("enc"))
    sop2 = SoporteEval(train_por_conjunto(a.datos), a.k)
    tmp = Path(tempfile.mkdtemp(prefix="frente_l2_"))
    res = {"k": a.k, "max_tok": enc.max_tok, "tareas": {}}
    for tarea in a.tareas.split(","):
        train, _, test = correr.cargar(tarea, a.datos)
        if a.max_filas:
            test = test[:a.max_filas]
        ops, sop = test[0]["opciones"], correr.soporte(train)
        f1_l1 = ev.tarea_modelo("potion", a.potion, 256, tarea, train, test, sop, ops, None, False, tmp)["proto"]
        f1 = {}
        for clave, so in (("k", sop2), ("k0", None)):
            f1[clave] = CE.evaluar(test, predecir(modelo, enc, test, soporte=so))["global"]["macro_f1"]
        res["tareas"][tarea] = {"n": len(test), "l1": f1_l1, **{c: {"l2": f1[c], "razon": razon(f1_l1, f1[c])} for c in f1}}
        print(tarea, json.dumps(res["tareas"][tarea]), flush=True)
    for c in ("k", "k0"):
        res["resumen_" + c] = resumen(res["tareas"], c)
    sal = Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    (sal / "frente_l2.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    md = informe_md(res, a.k)
    (sal / "frente_l2.md").write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
