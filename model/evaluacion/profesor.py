"""Profesor zero-shot por NLI (G.9): bge-m3-zeroshot-v2.0(-c) sobre las filas del esquema, medido con `chispa_eval`.

    python -m model.evaluacion.profesor preparar --datos D --meta M --fuera fuera.json --salida S [--max-filas 300]
    python -m model.evaluacion.profesor medir --modelo nombre=ruta [--modelo ...] --jevbench J --salida R [--conjuntos DIR]
    python -m model.evaluacion.profesor falso DIR --tokenizador RUTA        # NLI diminuto aleatorio, solo para la prueba en seco

Cada opción es una hipótesis (plantilla con la pregunta, la opción y su descripción) y el texto es la premisa; truncado a 512 tokens.
- choice: P(entailment) de cada opción, normalizada entre las opciones (suman 1).
- noul: una sola hipótesis, la de la opción «true»; P(true) = softmax(entailment, contradicción) de esa hipótesis (en un modelo de
  dos clases, «not_entailment» hace de contradicción).
- score: los niveles 1..K son las opciones, normalizadas como en choice. La etiqueta predicha NO se elige aquí: `chispa_eval`
  (`metricas.top1`) toma la mediana CORAL de esa distribución para `tipo == "score"` y el argmax para choice y noul.
La plantilla («card» en inglés, «es» en español) se elige por modelo en dev (macro-F1 medio de los conjuntos dev) y nunca en test ni en JevBench.
Escribe `R/<modelo>/pred/<conjunto>.jsonl` (`{id, probs, ms}`, `ms` = ms por caso en CPU, lotes incluidos) y `R/<modelo>/resultados.json`.
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from . import chispa_eval as CE

MAX_TOK = 512
LOTE = 32
EPS = 1e-9
PLANTILLAS = {   # {p} = pregunta, {x} = opción (con su descripción)
    "card": "{p} This text is about {x}",   # la del model card de bge-m3-zeroshot: «This text is about {}»
    "es": "{p} El texto trata de {x}",
}
DEV_POR_CONJUNTO = 30


def opcion_texto(fila, o):
    d = (fila.get("descripciones") or {}).get(o) or ""
    if fila["tipo"] == "noul":
        return d or "sí"
    return f"{o}: {d}" if d else str(o)


def hipotesis(fila, o, plantilla):
    p = (fila.get("pregunta") or "").strip()
    return PLANTILLAS[plantilla].format(p=p, x=opcion_texto(fila, o)).strip()[:1500]


def pares_fila(fila, plantilla):
    """[(opción, premisa, hipótesis)]: noul solo trae «true»."""
    ops = ["true"] if fila["tipo"] == "noul" else fila["opciones"]
    return [(o, fila["texto"], hipotesis(fila, o, plantilla)) for o in ops]


def probs_fila(fila, logits):
    """logits: (n_pares, 2) con columnas (entailment, contradicción), en el orden de `pares_fila`."""
    lg = np.asarray(logits, dtype=float)
    if fila["tipo"] == "noul":
        p = 1.0 / (1.0 + np.exp(lg[0, 1] - lg[0, 0]))
        return {"false": float(1 - p), "true": float(p)}
    pe = 1.0 / (1.0 + np.exp(lg[:, 1] - lg[:, 0])) + EPS   # P(entailment) de cada par; luego se normaliza entre opciones
    pe = pe / pe.sum()
    return dict(zip(fila["opciones"], pe.tolist()))


class NLIHF:
    """Modelo NLI de HF en CPU. `logits(pares)` -> (n, 2): (entailment, contradicción o not_entailment)."""

    def __init__(self, ruta, device="cpu"):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(ruta)
        self.modelo = AutoModelForSequenceClassification.from_pretrained(ruta).eval().to(device)
        self.device = device
        etq = {int(i): str(n).lower() for i, n in self.modelo.config.id2label.items()}
        self.i_ent = next((i for i, n in etq.items() if n.startswith("entail")), None)
        self.i_con = next((i for i, n in etq.items() if n.startswith("contradic")), None)
        if self.i_con is None:
            self.i_con = next((i for i, n in etq.items() if n.startswith(("not_entail", "not entail", "neutral"))), None)
        if self.i_ent is None or self.i_con is None:
            raise ValueError(f"{ruta}: id2label sin entailment/contradicción: {etq}")

    def logits(self, pares):
        out = []
        for i in range(0, len(pares), LOTE):
            lote = pares[i:i + LOTE]
            enc = self.tok([p for p, _ in lote], [h for _, h in lote], truncation=True, max_length=MAX_TOK, padding=True, return_tensors="pt")
            with self.torch.no_grad():
                lg = self.modelo(**{k: v.to(self.device) for k, v in enc.items()}).logits.float().cpu().numpy()
            out.append(lg[:, [self.i_ent, self.i_con]])
        return np.concatenate(out) if out else np.zeros((0, 2))


def predecir(nli, filas, plantilla, pares_por_tanda=LOTE):
    """[{id, probs, ms}] en el orden de `filas`. Las filas se agrupan en tandas de ~`pares_por_tanda` pares; ms = tiempo de la tanda / filas."""
    out, i = [], 0
    while i < len(filas):
        tanda, n = [], 0
        while i < len(filas) and (not tanda or n + len(pares_fila(filas[i], plantilla)) <= pares_por_tanda):
            tanda.append((filas[i], pares_fila(filas[i], plantilla)))
            n += len(tanda[-1][1])
            i += 1
        t0 = time.perf_counter()
        lg = nli.logits([(p, h) for _, ps in tanda for _, p, h in ps])
        ms = (time.perf_counter() - t0) * 1000 / len(tanda)
        k = 0
        for f, ps in tanda:
            out.append({"id": f["id"], "probs": probs_fila(f, lg[k:k + len(ps)]), "ms": round(ms, 3)})
            k += len(ps)
    return out


def elegir_plantilla(nli, dev):
    """(mejor, {plantilla: macro-F1 medio en dev}); empate -> «card». `dev`: {conjunto: filas}."""
    pts = {}
    for pl in PLANTILLAS:
        fs = [CE.evaluar(f, predecir(nli, f, pl))["global"]["macro_f1"] for f in dev.values() if f]
        pts[pl] = float(np.mean(fs)) if fs else float("nan")
    mejor = max(PLANTILLAS, key=lambda pl: (pts[pl] if pts[pl] == pts[pl] else -1, pl == "card"))
    return mejor, pts


def escribir(ruta, filas):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        for r in filas:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def medir_modelo(nli, test, dev, salida, plantilla=None, log=print):
    """test/dev: {conjunto: filas}. Escribe pred/ y resultados.json en `salida` y devuelve el resultado."""
    pts = {}
    if plantilla is None:
        plantilla, pts = elegir_plantilla(nli, dev) if any(dev.values()) else ("card", {})
        log(f"plantilla elegida en dev: {plantilla} {pts}")
    res = {"plantilla": plantilla, "dev_macro_f1": pts, "conjuntos": {}}
    for nombre, filas in test.items():
        t0 = time.time()
        preds = predecir(nli, filas, plantilla)
        escribir(Path(salida) / "pred" / f"{nombre}.jsonl", preds)
        ev = CE.evaluar(filas, preds)
        ms = sorted(p["ms"] for p in preds)
        res["conjuntos"][nombre] = {"n": len(filas), "exactitud": ev["global"]["exactitud"], "macro_f1": ev["global"]["macro_f1"],
                                    "ece": ev["global"]["ece"], "ms_medio": float(np.mean(ms)) if ms else None,
                                    "ms_p50": ms[len(ms) // 2] if ms else None}
        log(f"== {nombre}: n={len(filas)} exactitud {ev['global']['exactitud']:.4f} macro-F1 {ev['global']['macro_f1']:.4f} "
            f"{res['conjuntos'][nombre]['ms_medio']:.0f} ms/caso, {time.time() - t0:.0f} s")
        # tras cada conjunto: si el tope de tiempo corta el proceso, lo medido no se pierde
        Path(salida).mkdir(parents=True, exist_ok=True)
        (Path(salida) / "resultados.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    Path(salida).mkdir(parents=True, exist_ok=True)
    (Path(salida) / "resultados.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    return res


# --- datos --------------------------------------------------------------------------------------------------------------

def recortar(filas, n):
    """Como mucho `n` filas, estable (hash del id) y repartidas a partes iguales entre las tareas."""
    from model.l2.datos import _u
    por = defaultdict(list)
    for r in filas:
        por[r["tarea"]].append(r)
    cola = [sorted(rs, key=lambda r: _u(r["id"], 0)) for _, rs in sorted(por.items())]
    out = []
    while len(out) < n and any(cola):
        for c in cola:
            if c and len(out) < n:
                out.append(c.pop(0))
    return out


def filas_fuera_lista(meta, tareas, splits):
    """Filas de tasksource (`tsjev`) de las tareas de `tareas` (nombres base, como en fuera.json) en esos splits."""
    from model.l2 import datos as D
    from model.meta.muestreo import es_tasksource, tarea_base
    lista = set(tareas)
    return [r for f in D.ficheros(meta) for r in D.iterar(f) if r["split"] in splits and es_tasksource(r) and tarea_base(r["tarea"]) in lista]


def preparar(datos, meta, fuera, salida, nombres=("massive", "hatecheck", "inyecciones"), max_filas=300, log=print):
    """Escribe `salida/test-<n>.jsonl` (≤ max_filas) y `salida/dev-<n>.jsonl` (≤ DEV_POR_CONJUNTO) de cada conjunto no visto."""
    from model.l2 import datos as D
    conj = {}
    for n in nombres:
        ruta = Path(datos) / (n + ".jsonl")
        if ruta.exists():
            conj[n] = (D.leer(str(ruta), split="test"), D.leer(str(ruta), split="dev"))
        else:
            log(f"aviso: sin {ruta}")
    if fuera and meta:
        lista = json.loads(Path(fuera).read_text(encoding="utf-8"))["tareas_fuera"]
        te, de = filas_fuera_lista(meta, lista, ("test",)), filas_fuera_lista(meta, lista, ("dev",))
        conj["tasksource_fuera"] = (te or de, de)
        log(f"tasksource_fuera: {len(lista)} tareas en la lista, {len(te)} filas test, {len(de)} dev")
    for n, (te, de) in conj.items():
        te, de = recortar(te, max_filas), recortar(de, DEV_POR_CONJUNTO)
        escribir(Path(salida) / f"test-{n}.jsonl", CE.asignar_ids(te, n) if any("id" not in r for r in te) else te)
        escribir(Path(salida) / f"dev-{n}.jsonl", CE.asignar_ids(de, n + "-dev") if any("id" not in r for r in de) else de)
        log(f"{n}: {len(te)} test, {len(de)} dev")
    return sorted(conj)


def leer_conjuntos(dir_, prefijo):
    return {p.stem[len(prefijo) + 1:]: CE.leer_jsonl(str(p)) for p in sorted(Path(dir_).glob(prefijo + "-*.jsonl"))}


def falso(dir_, tokenizador):
    """NLI diminuto con pesos aleatorios (id2label entailment / not_entailment) y el tokenizador dado: solo para la prueba en seco."""
    import torch
    from transformers import AutoTokenizer, BertConfig, BertForSequenceClassification
    tok = AutoTokenizer.from_pretrained(tokenizador)
    torch.manual_seed(0)
    cfg = BertConfig(vocab_size=len(tok), hidden_size=16, num_hidden_layers=1, num_attention_heads=2, intermediate_size=32,
                     max_position_embeddings=MAX_TOK + 2, num_labels=2, id2label={0: "entailment", 1: "not_entailment"},
                     label2id={"entailment": 0, "not_entailment": 1})
    BertForSequenceClassification(cfg).save_pretrained(dir_)
    tok.save_pretrained(dir_)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("preparar")
    a.add_argument("--datos", required=True)
    a.add_argument("--meta")
    a.add_argument("--fuera")
    a.add_argument("--salida", required=True)
    a.add_argument("--max-filas", type=int, default=300)
    a.add_argument("--conjuntos", default="massive,hatecheck,inyecciones")
    m = sp.add_parser("medir")
    m.add_argument("--modelo", action="append", required=True, help="nombre=ruta")
    m.add_argument("--jevbench")
    m.add_argument("--conjuntos", help="salida de `preparar`")
    m.add_argument("--salida", required=True)
    m.add_argument("--plantilla", choices=sorted(PLANTILLAS), help="fija la plantilla (por defecto, la mejor en dev)")
    m.add_argument("--max-jev", type=int, default=0, help="solo para la prueba en seco")
    f = sp.add_parser("falso")
    f.add_argument("dir")
    f.add_argument("--tokenizador", required=True)
    x = ap.parse_args(argv)
    if x.cmd == "preparar":
        preparar(x.datos, x.meta, x.fuera, x.salida, [n for n in x.conjuntos.split(",") if n], x.max_filas)
    elif x.cmd == "falso":
        falso(x.dir, x.tokenizador)
    else:
        test = leer_conjuntos(x.conjuntos, "test") if x.conjuntos else {}
        dev = leer_conjuntos(x.conjuntos, "dev") if x.conjuntos else {}
        if x.jevbench:
            from .jevbench import cargar_jevbench
            jev = cargar_jevbench(x.jevbench)
            test["jevbench"] = jev[:x.max_jev] if x.max_jev else jev
        orden = ["jevbench", "massive", "hatecheck", "inyecciones"]   # prioridad si el tiempo no da para todo
        test = {k: test[k] for k in sorted(test, key=lambda k: (orden.index(k) if k in orden else len(orden), k))}
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        fallos = 0
        for e in x.modelo:
            nombre, _, ruta = e.partition("=")
            try:
                medir_modelo(NLIHF(ruta, device), test, dev, Path(x.salida) / nombre, x.plantilla)
            except Exception as ex:   # un modelo que falla no tumba al otro
                print(f"FALLO {nombre}: {type(ex).__name__}: {ex}", file=sys.stderr)
                fallos += 1
        return 1 if fallos else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
