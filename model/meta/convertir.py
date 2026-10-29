"""Corre los conversores de metaentrenamiento y escribe JSONL.gz en trozos de ~100 MB más `resumen.json`.

    python -m model.meta.convertir SALIDA [--solo tsjev,tsinst,synzs,pawsx,sib200] [--permitir-vacias]

Lee las fuentes de `$HF_HOME/hub` (por defecto ~/hf). `CHISPA_LIMITE=N` topa las filas por fuente (prueba en seco; el
tope queda en el resumen). Sale con 2 si una fuente no tiene datos o no da filas (salvo `--permitir-vacias`).
"""
import argparse
import json
import sys
import time
from pathlib import Path

from . import pawsx_es, sib200_es, synthetic_zeroshot, tasksource_instruct, tasksource_jev
from .comun import FuenteAusente, Salida, limite

FUENTES = {
    "tsjev": tasksource_jev, "tsinst": tasksource_instruct, "synzs": synthetic_zeroshot, "pawsx": pawsx_es, "sib200": sib200_es,
}


def correr(salida, solo=None, tope=None, chunk_bytes=None):
    """Ejecuta los conversores en `salida` y devuelve el resumen (dict)."""
    kw = {} if chunk_bytes is None else {"chunk_bytes": chunk_bytes}
    out = Salida(salida, **kw)
    info, ausentes, t0 = {}, {}, time.time()
    for corto in solo or FUENTES:
        mod = FUENTES[corto]
        info[corto] = {}
        print("== %s %s" % (corto, mod.REPO), flush=True)
        try:
            gen = mod.filas(info=info[corto], **({"tope": tope} if tope else {}))
            for f in gen:
                out.anadir(corto, f)
        except FuenteAusente as e:
            ausentes[corto] = "no está en la caché de Hugging Face: %s" % e
            print("AUSENTE %s: %s" % (corto, e), flush=True)
            continue
        for motivo, n in sorted(info[corto].items()):
            if motivo.startswith("descartadas_") and isinstance(n, int) and n:
                out.descartar(corto, motivo[len("descartadas_"):], n)
        n = out.resumen()["filas_por_fuente"].get(corto, 0)
        print("   %d filas; %s" % (n, {k: v for k, v in info[corto].items()
                                         if k.startswith("descartadas_") or k == "sin_datos"}), flush=True)
    out.cerrar()
    res = out.resumen()
    por = res["filas_por_fuente"]
    res.update(
        info=info, ausentes=ausentes, tope_filas_por_fuente=tope, segundos=round(time.time() - t0, 1),
        fuentes_vacias=[c for c in (solo or FUENTES) if por.get(c, 0) == 0])
    Path(salida).mkdir(parents=True, exist_ok=True)
    (Path(salida) / "resumen.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                                               encoding="utf-8")
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("salida")
    ap.add_argument("--solo", default="")
    ap.add_argument("--permitir-vacias", action="store_true")
    a = ap.parse_args(argv)
    solo = [s for s in a.solo.split(",") if s] or None
    for s in solo or ():
        if s not in FUENTES:
            ap.error("fuente desconocida: %s (hay %s)" % (s, ", ".join(FUENTES)))
    res = correr(a.salida, solo, limite())
    print(json.dumps({k: v for k, v in res.items() if k not in ("ficheros", "info", "filas_por_fuente_tipo_split")},
                     ensure_ascii=False, indent=1, sort_keys=True))
    if (res["fuentes_vacias"] or res["ausentes"]) and not a.permitir_vacias:
        print("FALLO: fuentes sin filas: %s" % ", ".join(res["fuentes_vacias"] or res["ausentes"]), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
