"""Corpus para ampliar la poda del vocabulario móvil, y el conjunto de comprobación que NO se usa para ampliar.

    python -m model.bench.torre.corpus_poda SALIDA [--fuentes a,b…] [--fixtures] [--jevbench RUTA] [--maximo N]

Escribe:
  SALIDA/ampliar/<fuente>.jsonl      filas `train` en español de los conversores de `model.datos` (texto, pregunta, opciones,
                                     descripciones), lo que recibe `exportar --vocab-ampliar SALIDA/ampliar`
  SALIDA/comprobacion/massive-test.jsonl y jevbench.jsonl   split `test` de massive-es y los casos de JevBench; ni un texto de aquí
                                     está en `ampliar/` (se quitan de la comprobación los que coinciden palabra por palabra)
  SALIDA/resumen.json                filas y textos por fuente, fuentes no disponibles y solapes quitados
Las fuentes ausentes de ~/hf se saltan y se anotan en el resumen. Con `--fixtures` convierte los fixtures de `model/datos/fixtures`.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from model.datos import convertir as CV

CAMPOS = ("id", "texto", "pregunta", "opciones", "descripciones")


def _recortar(r):
    return {k: r[k] for k in CAMPOS if k in r}


def _textos(r):
    return [t for t in [r.get("texto"), r.get("pregunta"), *(r.get("opciones") or []), *(r.get("descripciones") or {}).values()]
            if isinstance(t, str) and t.strip()]


def escribir(filas, ruta):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in filas), encoding="utf-8")


def armar(salida, fuentes=CV.FUENTES, fixtures=False, jevbench=None, maximo=None):
    """Arma `salida/ampliar` y `salida/comprobacion`; devuelve el resumen."""
    salida = Path(salida)
    resumen = {"fuentes": {}, "no_disponibles": {}}
    ampliar, test_massive = {}, []
    with tempfile.TemporaryDirectory() as t:
        res = CV.convertir_fuentes(t, fuentes, fixtures)
        for nombre in fuentes:
            r = res.get(nombre, {})
            if r.get("estado") != "convertida":
                resumen["no_disponibles"][nombre] = r.get("detalle") or r.get("error") or r.get("estado")
                continue
            filas = [json.loads(l) for l in (Path(t) / (nombre + ".jsonl")).read_text(encoding="utf-8").splitlines() if l.strip()]
            es = [f for f in filas if f.get("idioma") == "es"]
            train = [_recortar(f) for f in es if f["split"] == "train"]
            if maximo:
                train = train[:maximo]
            ampliar[nombre] = train
            if nombre == "massive":
                test_massive = [_recortar(f) for f in es if f["split"] == "test"]
            resumen["fuentes"][nombre] = {"filas_es": len(es), "train": len(train)}
    jev = []
    if jevbench:
        from model.evaluacion.jevbench import cargar_jevbench
        jev = [_recortar(r) for r in cargar_jevbench(jevbench)]
    en_corpus = {t for filas in ampliar.values() for r in filas for t in _textos(r)}
    quitados = {}
    for nombre, filas in (("massive-test", test_massive), ("jevbench", jev)):
        # una fila se queda si su mensaje (`texto`; si no lo tiene, la pregunta) no está en el corpus: la pregunta de massive es la misma en todas
        sin = [r for r in filas if (r.get("texto") or r.get("pregunta")) not in en_corpus]
        quitados[nombre] = len(filas) - len(sin)
        escribir(sin, salida / "comprobacion" / (nombre + ".jsonl"))
        resumen["fuentes"][nombre] = {"filas": len(sin)}
    for nombre, filas in ampliar.items():
        if filas:   # banking77 o clinc150 no traen español: no dejan ficheros vacíos
            escribir(filas, salida / "ampliar" / (nombre + ".jsonl"))
    resumen["solapes_quitados_de_la_comprobacion"] = quitados
    resumen["textos_ampliar"] = len(en_corpus)
    (salida / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return resumen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("salida")
    ap.add_argument("--fuentes", default=",".join(CV.FUENTES))
    ap.add_argument("--fixtures", action="store_true")
    ap.add_argument("--jevbench", help="clon de JevBench (o su datasets/public) para la comprobación")
    ap.add_argument("--maximo", type=int, help="filas train como mucho por fuente")
    a = ap.parse_args(argv)
    fuentes = [s for s in a.fuentes.split(",") if s]
    mal = [s for s in fuentes if s not in CV.FUENTES]
    if mal:
        ap.error("fuentes desconocidas: %s" % mal)
    print(json.dumps(armar(a.salida, fuentes, a.fixtures, a.jevbench, a.maximo), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
