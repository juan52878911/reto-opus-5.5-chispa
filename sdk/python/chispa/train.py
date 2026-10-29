"""`chispa train`: de un CSV/JSONL de ejemplos y un esquema a un `.chispa` v3 (META, L0, L1, CALIB, y L2/ESQUEMAS si hay L2).

El entrenamiento (L0 lineal, calibración de L1) lo hace `entrenador_go/` con `go run`; este módulo prepara el plan,
lo ejecuta y, sin Go, deja el fichero sin L0 y lo dice."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from . import formato
from .cliente import ChispaError
from .datos import cargar_ejemplos, cargar_esquema, validar

GO_DIR = Path(__file__).resolve().parent / "entrenador_go"


def encontrar_repo(repo=None) -> Optional[Path]:
    """Raíz del repositorio (donde están `format/chispa3` y `runtime/l1`): argumento, `CHISPA_REPO` o los padres."""
    cands = [repo, os.environ.get("CHISPA_REPO"), *Path(__file__).resolve().parents]
    for c in cands:
        if c and (Path(c) / "format/chispa3/go.mod").is_file() and (Path(c) / "runtime/l1/go.mod").is_file():
            return Path(c).resolve()
    return None


def encontrar_go() -> Optional[str]:
    g = shutil.which("go")
    if g:
        return g
    for c in (Path.home() / "go-sdk/bin/go", Path("/usr/local/go/bin/go")):
        if c.is_file():
            return str(c)
    return None


def preparar_go(trabajo: Path, repo: Path) -> Path:
    """Copia el entrenador a `trabajo` con los `replace` apuntando a `repo` (sirve también instalado con pip)."""
    d = trabajo / "entrenador_go"
    d.mkdir()
    for f in GO_DIR.glob("*.go"):
        if not f.name.endswith("_test.go"):
            shutil.copy(f, d / f.name)
    shutil.copy(GO_DIR / "go.sum", d / "go.sum")
    mod = (GO_DIR / "go.mod").read_text()
    mod = mod[: mod.index("replace (")] + (f"replace (\n\tchispa/format/chispa3 => {repo}/format/chispa3\n"
                                           f"\tchispa/runtime/l1 => {repo}/runtime/l1\n)\n")
    (d / "go.mod").write_text(mod)
    return d


def comandos_l2(ckpt: str, filas: Path, trabajo: Path, python=sys.executable) -> List[List[str]]:
    """calibrar → exportar de `model/l2` (necesitan el repo en el cwd y torch/transformers)."""
    calib, salida = trabajo / "calib_l2.json", trabajo / "l2.chispa"
    return [[python, "-m", "model.l2.calibrar", "--ckpt", ckpt, "--dev", str(filas), "--salida", str(calib), "--device", "cpu"],
            [python, "-m", "model.l2.exportar", "--ckpt", ckpt, "--calib", str(calib), "--esquemas", str(filas),
             "--salida", str(salida)]]


def _filas_l2(q, ejemplos, ruta: Path):
    desc = {o.id: o.description for o in q.options}
    with open(ruta, "w", encoding="utf-8") as f:
        for i, (t, e) in enumerate(ejemplos):
            f.write(json.dumps({"id": f"sdk:dev:{i}", "tarea": q.id, "tipo": q.kind, "pregunta": q.question, "texto": t,
                                "opciones": [o.id for o in q.options], "descripciones": desc, "etiqueta": e, "idioma": "es",
                                "split": "dev", "fuente": "chispa train", "licencia": "propia", "uso_comercial": True},
                               ensure_ascii=False) + "\n")


def entrenar(ejemplos, esquema, salida, *, l1=None, ckpt=None, l2=None, repo=None, pregunta=None, semilla=1,
             frac_valid=0.2, l0_max_mb=48.0, usar_go=True, conjunta=False, modelo_l2=None, l0tf_f16=False, l0tf_max_mb=48.0, precision_objetivo=0.95,
             validacion=None, margen=0.02, suelo=0.05, log=print) -> dict:
    """Entrena y escribe `salida`. Devuelve el informe (secciones, omitidas, validación, tiempos y `reloj_s` total).

    `l0_max_mb` topa la tabla de pesos de L0 (el lector de kindling rechaza más de 64 MiB): se reducen los buckets de hashing
    (potencias de dos) hasta que cabe; con muchas clases, más colisiones. `conjunta` añade la sección CONJ (cabeza L0 + L2): necesita L2 (`l2` o `ckpt`) y el checkpoint `ckpt` para las
    características. `conjunta` también escribe L0TF (el L0 tfidf que alimenta a la cabeza; `l0tf_max_mb` topa su tabla de coeficientes podando el
    vocabulario por frecuencia, `l0tf_f16` los guarda en media precisión). `validacion` (JSONL/CSV de texto y etiqueta, fuera de `ejemplos`) fija el τ de L2c sobre esas filas; sin ella, `margen` y `suelo` (H2 de T4.6c). `modelo_l2` = (ModeloL2, Codificador) ya cargados, en vez de leer `ckpt` (tests)."""
    t0 = time.time()
    q, extra = cargar_esquema(esquema, pregunta)
    ex = cargar_ejemplos(ejemplos, q.id)
    cuenta = validar(ex, q)
    log(f"{len(ex)} ejemplos, {len(cuenta)} clases (mín {min(cuenta.values())}, máx {max(cuenta.values())})")
    if l1 and not Path(l1).is_file():
        raise ChispaError(f"--l1: no existe {l1}")
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    repo, go = encontrar_repo(repo), encontrar_go()
    if ckpt and not repo:
        raise ChispaError("--ckpt necesita el repositorio (model/l2): usa --repo o CHISPA_REPO")
    if conjunta:
        if not (ckpt or modelo_l2):
            raise ChispaError("--conjunta necesita --ckpt: las características salen del modelo de L2, no del ONNX")
        if not (l2 or ckpt):
            raise ChispaError("--conjunta necesita L2 y ESQUEMAS: pasa --l2 o --ckpt")
        if not repo:
            raise ChispaError("--conjunta necesita el repositorio (model/l2): usa --repo o CHISPA_REPO")
    with tempfile.TemporaryDirectory(prefix="chispa-train-") as tmp:
        tmp = Path(tmp)
        if not (usar_go and repo and go):
            if conjunta:
                raise ChispaError("--conjunta necesita el entrenador de Go y el repositorio (CHISPA_REPO)")
            motivo = "desactivado" if not usar_go else "no hay Go" if not go else "no se encuentra el repositorio (CHISPA_REPO)"
            return _sin_go(q, extra, l1, salida, t0, motivo, log)
        l2_ch = l2 or ""
        tiempo_l2 = None
        conj_inf = None
        conj_ruta = ""
        l0tf_ruta = ""
        if ckpt and not (conjunta and l2):  # con --conjunta, el --l2 dado manda y el checkpoint solo da las características
            filas = tmp / "filas.jsonl"
            _filas_l2(q, ex, filas)
            t = time.time()
            for cmd in comandos_l2(ckpt, filas, tmp):
                log("L2: " + " ".join(cmd[1:4]))
                r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
                if r.returncode:
                    raise ChispaError(f"{cmd[2]} falló:\n{r.stderr[-2000:]}")
            l2_ch, tiempo_l2 = str(tmp / "l2.chispa"), time.time() - t
        if conjunta:
            t = time.time()
            from . import conjunta as cj
            modelo, enc = modelo_l2 or cj.cargar_ckpt(ckpt, repo)
            b, b_l0, conj_inf = cj.seccion_conj(q, ex, modelo, enc, repo, log, l0tf_f16, l0tf_max_mb, precision_objetivo,
                                               cargar_ejemplos(validacion, q.id) if validacion else None, margen, suelo)
            conj_inf["s"] = time.time() - t
            conj_ruta, l0tf_ruta = str(tmp / "conj.bin"), str(tmp / "l0tf.bin")
            Path(conj_ruta).write_bytes(b)
            Path(l0tf_ruta).write_bytes(b_l0)
        with open(tmp / "ej.jsonl", "w", encoding="utf-8") as f:
            for t_, e in ex:
                f.write(json.dumps({"text": t_, "label": e}, ensure_ascii=False) + "\n")
        plan = {"ejemplos": str(tmp / "ej.jsonl"), "salida": str(salida.resolve()), "semilla": semilla,
                "frac_valid": frac_valid, "l0_max_mb": l0_max_mb, "l1": str(Path(l1).resolve()) if l1 else "", "l2_chispa": str(l2_ch),
                "conj": conj_ruta, "l0tf": l0tf_ruta, "tau_l2c": (conj_inf or {}).get("tau_l2c"),
                "pregunta": {"id": q.id, "texto": q.question, "kind": q.kind,
                             "opciones": [{"id": o.id, "description": o.description} for o in q.options]},
                "meta": {"version": 1, "tareas": [q.id], "licencias": extra["licencias"], "dorado": extra["dorado"]}}
        (tmp / "plan.json").write_text(json.dumps(plan, ensure_ascii=False))
        d = preparar_go(tmp, repo)
        env = dict(os.environ, GOFLAGS=os.environ.get("GOFLAGS", "-mod=mod"), GOPROXY=os.environ.get("GOPROXY", "off"))
        t = time.time()
        b = subprocess.run([go, "build", "-o", str(tmp / "entrenador"), "."], cwd=d, env=env, capture_output=True, text=True)
        if b.returncode:
            raise ChispaError(f"go build falló:\n{b.stderr[-2000:]}")
        t_build = time.time() - t
        r = subprocess.run([str(tmp / "entrenador"), "entrenar", str(tmp / "plan.json")], capture_output=True, text=True)
        if r.returncode:
            raise ChispaError(f"entrenador falló:\n{r.stderr[-2000:]}")
        inf = json.loads(r.stdout)
    inf["tiempos_s"]["go_build"] = t_build
    if tiempo_l2 is not None:
        inf["tiempos_s"]["l2"] = tiempo_l2
    if conj_inf:
        inf["conjunta"] = conj_inf
    inf["reloj_s"] = time.time() - t0
    if conj_inf and conj_inf.get("tau_l2c") is not None:
        log(f"τ de L2c {conj_inf['tau_l2c']:.4f} en CALIB, método {conj_inf['metodo_tau']} (precisión esperada "
            f"{conj_inf['precision_esperada']:.3f}, cobertura esperada {conj_inf['cobertura_esperada']:.3f})")
    inf["omitidas"] = inf.get("omitidas") or {}
    for k, v in inf["omitidas"].items():
        log(f"AVISO: sin {k}: {v}")
    log(f"{salida}: {'+'.join(inf['secciones'])}, {inf['bytes']} bytes, L0 validación {inf['l0_valid_acc']:.3f}, "
        f"{inf['reloj_s']:.1f} s")
    return inf


def _sin_go(q, extra, l1, salida: Path, t0, motivo, log) -> dict:
    """Sin entrenador: META, L1 (si hay) y CALIB sin calibrar. L0 queda fuera."""
    log(f"AVISO: sin L0 ({motivo}); CALIB con valores por defecto, sin calibrar")
    secs = {formato.META: formato.meta([q.id], extra["licencias"], extra["dorado"]),
            formato.CALIB: formato.calib({}, 1.0)}
    omitidas = {"L0": motivo, "L2": "sin checkpoint de L2", "ESQUEMAS": "sin checkpoint de L2", "CALIB": "sin calibrar"}
    if l1:
        secs[formato.L1] = Path(l1).read_bytes()
    else:
        omitidas["L1"] = "sin --l1"
    salida.write_bytes(formato.escribir(secs))
    nombres = {1: "META", 3: "L1", 6: "CALIB"}
    return {"salida": str(salida), "secciones": [nombres[t] for t in sorted(secs)], "omitidas": omitidas,
            "bytes": salida.stat().st_size, "tiempos_s": {}, "reloj_s": time.time() - t0, "l0_valid_acc": 0.0}
