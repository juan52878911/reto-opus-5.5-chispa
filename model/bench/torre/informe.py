"""informe.md de la verificación de la torre: lee RES/estado.tsv (paso, OK|FALLO, detalle) y, por variante V, RES/paridad-V/paridad.json y RES/servidor-V/servidor.json.
    python -m model.bench.torre.informe RES
"""
import json
import sys
from pathlib import Path


def f(x):
    return ("%.4f" % x).replace(".", ",")


def cargar(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


OBJETIVO_COSENO = {"ninguna": 0.999, "dinamico": 0.999, "estatico": 0.995}   # estatico: la hipótesis de G.7; el objetivo general es 0,999
MAX_MB = {"ninguna": None, "dinamico": 50, "estatico": 50}


def leer_estado(res):
    estado = {}
    for l in (res / "estado.tsv").read_text().splitlines() if (res / "estado.tsv").exists() else []:
        k, _, v = l.partition("\t")
        estado[k] = v
    return estado


def variantes(res, estado):
    vs = [d.name[len("paridad-"):] for d in sorted(res.glob("paridad-*")) if d.is_dir()]
    vs += [k[len("metadata_"):] for k in estado if k.startswith("metadata_") and k[len("metadata_"):] not in vs]
    orden = list(OBJETIVO_COSENO)
    return sorted(vs, key=lambda v: (orden.index(v) if v in orden else len(orden), v))


def fila_estado(filas, estado, k, txt):
    v = estado.get(k)
    ok = None if v is None or v.startswith("OMITIDO") else v.startswith("OK")
    filas.append("| %s | %s | %s |" % (txt, "OK" if ok else "FALLO" if ok is not None else "NO MEDIDO",
                                       v if v and v.startswith("OMITIDO") else v.partition(" ")[2] if v else "no llegó"))


def fila_torres(fila, srv, sufijo):
    """Comprobación obligatoria: /metrics tras las peticiones. Sin torres calculadas o sin L2 en las capas, FALLO."""
    m = srv.get("metricas")
    if m is None:
        return fila("`/metrics` leído tras las peticiones" + sufijo, False, "no se leyó")
    capas = (srv.get("todos") or {}).get("capas") or {}
    fila("`chispa_torres_calculadas_total` > 0 y L2 entre las capas" + sufijo, bool(srv.get("torres_ok")),
         "torres calculadas %d (errores %d); capas por caso %s; decididas %s" % (m.get("chispa_torres_calculadas_total", 0), m.get("chispa_torres_errores_total", 0),
         capas or [c["layer"] for c in srv.get("cinco", [])], {k.split('"')[1]: int(x) for k, x in m.items() if k.startswith("chispa_decididas_total")}))


def tabla_variante(res, estado, v):
    """Tabla de una variante: lo que mide exportar.py --medir-torre (paridad-V/paridad.json) y servidor.py (servidor-V/servidor.json)."""
    par, srv = cargar(res / ("paridad-" + v) / "paridad.json"), cargar(res / ("servidor-" + v) / "servidor.json")
    filas = []

    def fila(txt, ok, cifra):
        filas.append("| %s | %s | %s |" % (txt, "OK" if ok else "FALLO" if ok is not None else "NO MEDIDO", cifra))
    if par:
        h, sp, t, u, lat = par["h"], par.get("h_sin_poda"), par["top1_choice"], par.get("top1_choice_sin_unk"), par.get("latencia_torre")
        obj = OBJETIVO_COSENO.get(v, 0.999)
        fila("coseno medio de `h` ONNX (con poda) vs PyTorch, %d textos (objetivo ≥ %s)" % (h["n"], f(obj)), h["coseno_medio"] >= obj,
             "%s (mín %s); %.1f %% de tokens a `<unk>`" % (f(h["coseno_medio"]), f(h["coseno_min"]), 100 * par.get("tokens_unk", 0)))
        fila("coseno medio de `h` sin `<unk>` (solo cuantización; objetivo ≥ %s)" % f(obj), None if not sp else sp["coseno_medio"] >= obj,
             "%s (mín %s)" % (f(sp["coseno_medio"]), f(sp["coseno_min"])) if sp else "—")
        fila("top-1 de choice, torres ONNX (poda) vs PyTorch, %d filas (objetivo ≥ 0,98)" % t["n"], t["acuerdo"] >= 0.98,
             "%s (margen medio %s)" % (f(t["acuerdo"]), f(t["margen_medio"])))
        fila("top-1 de choice sin `<unk>` (objetivo ≥ 0,98)", None if not u else u["acuerdo"] >= 0.98, f(u["acuerdo"]) if u else "—")
        mx = MAX_MB.get(v)
        fila("tamaño del ONNX de la torre" + (" (≤ %d MB)" % mx if mx else ""), None if mx is None else par["mb"] <= mx,
             "%.1f MB (fp32: %.1f)" % (par["mb"], par["fp32_mb"]))
        fila("latencia de la torre, ORT 1 hilo, lote 1, por texto", None if not lat else True,
             "p50 %.1f ms, p99 %.1f ms (%d textos)" % (lat["p50_ms"], lat["p99_ms"], lat["n"]) if lat else "—")
        fila("`max_len` / textos de calibración", None, "%s / %s" % (par.get("max_len", "—"), par.get("n_calib", 0)))
    else:
        fila("paridad de la torre", None, "sin paridad-%s/paridad.json" % v)
    fila_estado(filas, estado, "metadata_" + v, "`metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX")
    fila_estado(filas, estado, "train_torre_" + v, "`chispa train --torre` y `chispa-server -tags ort` con la torre")
    if srv:
        fila("5 esquemas de JevBench fuera del .chispa decididos por L2 en /v1/decide", bool(srv.get("cinco_l2")),
             "capas %s; aciertos %d/%d" % ([c["layer"] for c in srv.get("cinco", [])], srv.get("cinco_aciertos", 0), len(srv.get("cinco", []))))
        t = srv.get("todos")
        if t:
            py = t.get("exactitud_python_k0")
            fila("JevBench por el servidor, %d/%d casos (exactitud a ≤ 0,01 de Python k=0)" % (t["casos"], t["de"]),
                 None if py is None else abs(t["exactitud_servidor"] - py) <= 0.01,
                 "exactitud servidor %s; Python k=0 sobre los mismos casos %s; capas %s" % (f(t["exactitud_servidor"]), f(py) if py is not None else "—", t["capas"]))
        fila_torres(fila, srv, "")
    else:
        fila("servidor con torres al vuelo", None, "sin servidor-%s/servidor.json" % v)
    tau = cargar(res / ("servidor-" + v + "-tau") / "servidor.json")
    if tau:
        t = tau.get("todos")
        fila_torres(fila, tau, " [tau_l2_esquema_nuevo=%s]" % tau.get("tau_l2_esquema_nuevo"))
        if t:
            fila("pasada con tau_l2_esquema_nuevo=%s: %d/%d casos, contesta L2 en" % (tau.get("tau_l2_esquema_nuevo"), t["casos"], t["de"]), None,
                 "%s de %d (%.1f %%); exactitud servidor %s" % (t["capas"].get("L2", 0), t["casos"], 100 * t["capas"].get("L2", 0) / max(t["casos"], 1), f(t["exactitud_servidor"])))
    return "\n".join(filas)


def tabla(res):
    res = Path(res)
    estado = leer_estado(res)
    cab = "| punto | resultado | cifra |\n|---|---|---|\n"
    out = ""
    for v in variantes(res, estado):
        out += "## Torre %s\n\n%s%s\n\n" % (v, cab, tabla_variante(res, estado, v))
    comunes = []
    for k, txt in (("go_test_ort", "`go test -tags ort ./server/torre/...` (con CHISPA_TOK)"), ("go_test_tok", "`TestIgualdadTransformersPasaje` (CHISPA_TOK)"),
                   ("build_server", "`chispa-server -tags ort` compila")):
        fila_estado(comunes, estado, k, txt)
    out += "## Comunes\n\n%s%s\n\n" % (cab, "\n".join(comunes))
    claves = cargar(res / "calib-score-claves.json")
    fila_estado(comunes := [], estado, "chispa_score", "`.chispa` con score K ≥ 3 subido a `$CHISPA_S3/score/l2-score.chispa`")
    out += "## `.chispa` con score K ≥ 3\n\n%s%s\n\nClaves `scoreK` de CALIB: %s\n" % (cab, comunes[0], ", ".join("`%s`" % k for k in claves) if claves else "—")
    return out


def main(res):
    fallos = (Path(res) / "FALLO").read_text().strip() if (Path(res) / "FALLO").exists() else ""
    txt = "# Verificación de punta a punta de la torre de L2 (checkpoint real): variantes\n\n%s\n" % tabla(res)
    txt += "Fallo del script: %s\n" % (fallos or "ninguno")
    (Path(res) / "informe.md").write_text(txt)
    print(txt)


if __name__ == "__main__":
    main(sys.argv[1])
