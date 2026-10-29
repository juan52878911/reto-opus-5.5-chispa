"""informe.md de la verificación de la torre: lee RES/estado.tsv (paso, OK|FALLO, detalle), RES/torre-paridad/paridad.json y RES/servidor.json.
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


def tabla(res):
    res = Path(res)
    estado = {}
    for l in (res / "estado.tsv").read_text().splitlines() if (res / "estado.tsv").exists() else []:
        k, _, v = l.partition("\t")
        estado[k] = v
    par, srv = cargar(res / "torre-paridad" / "paridad.json"), cargar(res / "servidor.json")
    filas = []

    def fila(txt, ok, cifra):
        filas.append("| %s | %s | %s |" % (txt, "OK" if ok else "FALLO" if ok is not None else "NO MEDIDO", cifra))
    if par:
        h, sp, t, u = par["h"], par.get("h_sin_poda"), par["top1_choice"], par.get("top1_choice_sin_unk")
        fila("coseno medio de `h` ONNX (con poda) vs PyTorch, %d textos" % h["n"], h["coseno_medio"] >= 0.999,
             "%s (mín %s); %.1f %% de tokens a `<unk>`" % (f(h["coseno_medio"]), f(h["coseno_min"]), 100 * par.get("tokens_unk", 0)))
        fila("coseno medio de `h` sin `<unk>` (solo cuantización)", None if not sp else sp["coseno_medio"] >= 0.999, f(sp["coseno_medio"]) if sp else "—")
        fila("top-1 de choice, torres ONNX (poda) vs PyTorch, %d filas" % t["n"], t["acuerdo"] >= 0.98, "%s (margen medio %s)" % (f(t["acuerdo"]), f(t["margen_medio"])))
        fila("top-1 de choice sin `<unk>`", None if not u else u["acuerdo"] >= 0.98, f(u["acuerdo"]) if u else "—")
        fila("tamaño del ONNX de la torre", par["mb"] <= 50, "%.1f MB" % par["mb"])
    else:
        fila("paridad de la torre", None, "sin torre-paridad/paridad.json")
    for k, txt in (("metadata", "`metadata_props` chispa.torre.{dim,max_len,prefijo} en el ONNX"), ("go_test_ort", "`go test -tags ort ./server/torre/...`"),
                   ("go_test_tok", "`TestIgualdadTransformersPasaje` (CHISPA_TOK)"), ("train_torre", "`chispa train --torre`"),
                   ("build_server", "`chispa-server -tags ort` compila")):
        v = estado.get(k)
        fila(txt, None if v is None else v.startswith("OK"), v.partition(" ")[2] if v else "no llegó")
    if srv:
        fila("5 esquemas de JevBench fuera del .chispa decididos por L2 en /v1/decide", bool(srv.get("cinco_l2")),
             "capas %s; aciertos %d/%d" % ([c["layer"] for c in srv.get("cinco", [])], srv.get("cinco_aciertos", 0), len(srv.get("cinco", []))))
        t = srv.get("todos")
        if t:
            py = t.get("exactitud_python_k0")
            fila("JevBench por el servidor, %d/%d casos" % (t["casos"], t["de"]), None,
                 "exactitud servidor %s; Python k=0 sobre los mismos casos %s; capas %s" % (f(t["exactitud_servidor"]), f(py) if py is not None else "—", t["capas"]))
    else:
        fila("servidor con torres al vuelo", None, "sin servidor.json")
    return "\n".join(filas), par, estado


def main(res):
    cuerpo, par, estado = tabla(res)
    fallos = (Path(res) / "FALLO").read_text().strip() if (Path(res) / "FALLO").exists() else ""
    txt = "# Verificación de punta a punta de la torre de L2 (checkpoint real)\n\n| punto | resultado | cifra |\n|---|---|---|\n%s\n\n" % cuerpo
    txt += "Fallo del script: %s\n" % (fallos or "ninguno")
    (Path(res) / "informe.md").write_text(txt)
    print(txt)


if __name__ == "__main__":
    main(sys.argv[1])
