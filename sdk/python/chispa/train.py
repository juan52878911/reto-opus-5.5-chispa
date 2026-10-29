"""`chispa train`: de un esquema y, opcionalmente, un CSV/JSONL de ejemplos a un `.chispa` v3 (META, L0, L1, CALIB, y L2/ESQUEMAS si hay L2).

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

# Tres modos según los datos: sin ejemplos (zero-shot), pocos por opción (few-shot) y suficientes (con datos del cliente).
MIN_L0_POR_OPCION = 10     # con menos ejemplos en alguna opción no se entrena L0 (few-shot: L1 se calibra con todos)
MIN_CONJ_POR_OPCION = 20   # --conjunta con menos en alguna opción avisa y cae a few-shot
TAU_ZERO_SHOT = 0.6        # τ de escalado sin calibrar (CALIB sin tipos: L1 usa T = 0,05 por defecto)


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


def fuentes_go(repo: Optional[Path] = None) -> Optional[tuple]:
    """(format/chispa3, runtime/l1) que compila el entrenador: los del repositorio si se encuentra y, si no, las copias que el
    wheel lleva en `entrenador_go/vendor/` (las pone `setup.py` al construir). None si no hay ni una cosa ni otra."""
    if repo:
        return Path(repo) / "format/chispa3", Path(repo) / "runtime/l1"
    v = GO_DIR / "vendor"
    if (v / "chispa3/go.mod").is_file() and (v / "l1/go.mod").is_file():
        return v / "chispa3", v / "l1"
    return None


def preparar_go(trabajo: Path, fuentes) -> Path:
    """Copia el entrenador a `trabajo` con los `replace` apuntando a `fuentes` (de `fuentes_go`; un Path se toma como raíz del repo)."""
    if not isinstance(fuentes, tuple):
        fuentes = fuentes_go(fuentes)
    chispa3, l1 = fuentes
    d = trabajo / "entrenador_go"
    d.mkdir()
    for f in GO_DIR.glob("*.go"):
        if not f.name.endswith("_test.go"):
            shutil.copy(f, d / f.name)
    shutil.copy(GO_DIR / "go.sum", d / "go.sum")
    mod = (GO_DIR / "go.mod").read_text()
    mod = mod[: mod.index("replace (")] + (f"replace (\n\tchispa/format/chispa3 => {Path(chispa3).resolve()}\n"
                                           f"\tchispa/runtime/l1 => {Path(l1).resolve()}\n)\n")
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


def _zero_shot(q, extra, l1, l2, ckpt, repo, salida: Path, t0, log) -> dict:
    """Sin ejemplos: META, CALIB sin calibrar, L1 (los prototipos de las opciones salen de «pregunta · opción · descripción»
    y los calcula el servidor al cargar) y, con `l2` o `ckpt`, L2 y ESQUEMAS (con `ckpt` no hay validación: no se calibra)."""
    if not (l1 or l2 or ckpt):
        raise ChispaError("sin --ejemplos hace falta --l1 o --l2/--ckpt: un .chispa zero-shot sin ninguna capa no decide nada")
    secs = {formato.META: formato.meta([q.id], extra["licencias"], extra["dorado"]),
            formato.CALIB: formato.calib({}, TAU_ZERO_SHOT)}
    omitidas = {"L0": "zero-shot: sin ejemplos", "CALIB": f"zero-shot: sin calibrar (τ {TAU_ZERO_SHOT})"}
    tiempos = {}
    if l1:
        secs[formato.L1] = Path(l1).read_bytes()
    else:
        omitidas["L1"] = "sin --l1"
    l2_ch = l2
    if ckpt and not l2:
        if not repo:
            raise ChispaError("--ckpt necesita el repositorio (model/l2): usa --repo o CHISPA_REPO")
        with tempfile.TemporaryDirectory(prefix="chispa-train-") as tmp:
            tmp = Path(tmp)
            filas = tmp / "filas.jsonl"
            _filas_l2(q, [(q.question, q.options[0].id)], filas)  # solo el esquema cuenta: las torres no usan la etiqueta
            (tmp / "calib_l2.json").write_text(json.dumps({"chispa": {"tipos": {}, "tau_escalate": TAU_ZERO_SHOT}}))
            t = time.time()
            cmd = comandos_l2(ckpt, filas, tmp)[1]
            log("L2: " + " ".join(cmd[1:4]))
            r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True)
            if r.returncode:
                raise ChispaError(f"{cmd[2]} falló:\n{r.stderr[-2000:]}")
            tiempos["l2"] = time.time() - t
            l2_ch = str(tmp / "l2.chispa")
            sec = formato.leer(Path(l2_ch).read_bytes())
    elif l2:
        sec = formato.leer(Path(l2).read_bytes())
    if l2_ch:
        for t_, n in ((formato.L2, "L2"), (formato.ESQUEMAS, "ESQUEMAS")):
            if t_ not in sec:
                raise ChispaError(f"--l2: falta la sección {n}")
            secs[t_] = sec[t_]
    else:
        omitidas["L2"] = omitidas["ESQUEMAS"] = "sin --l2/--ckpt"
    salida.write_bytes(formato.escribir(secs))
    nombres = {formato.META: "META", formato.L1: "L1", formato.L2: "L2", formato.ESQUEMAS: "ESQUEMAS", formato.CALIB: "CALIB"}
    inf = {"salida": str(salida), "modo": "zero-shot", "secciones": [nombres[t_] for t_ in sorted(secs)], "omitidas": omitidas,
           "bytes": salida.stat().st_size, "tiempos_s": tiempos, "reloj_s": time.time() - t0, "l0_valid_acc": 0.0}
    for k, v in omitidas.items():
        log(f"AVISO: sin {k}: {v}")
    log(f"{salida}: zero-shot, {'+'.join(inf['secciones'])}, {inf['bytes']} bytes")
    return inf


def entrenar(ejemplos, esquema, salida, *, l1=None, ckpt=None, l2=None, repo=None, pregunta=None, semilla=1,
             frac_valid=0.2, l0_max_mb=48.0, usar_go=True, conjunta=False, modelo_l2=None, l0tf_f16=False, l0tf_max_mb=48.0, precision_objetivo=0.95,
             validacion=None, margen=0.02, suelo=0.05, tope_tau=0.9, torre=None, torre_dim=None, torre_max_len=None, torre_prefijo=None,
             log=print) -> dict:
    """Entrena y escribe `salida`. Sin `ejemplos`: zero-shot (L1 de las descripciones, y L2/ESQUEMAS con `l2`/`ckpt`). Con pocos
    (< MIN_L0_POR_OPCION por opción): few-shot, sin L0. `conjunta` con < MIN_CONJ_POR_OPCION por opción avisa y cae a few-shot. Devuelve el informe (secciones, omitidas, validación, tiempos y `reloj_s` total).

    `l0_max_mb` topa la tabla de pesos de L0 (el lector de kindling rechaza más de 64 MiB): se reducen los buckets de hashing
    (potencias de dos) hasta que cabe; con muchas clases, más colisiones. `conjunta` añade la sección CONJ (cabeza L0 + L2): necesita L2 (`l2` o `ckpt`) y el checkpoint `ckpt` para las
    características. `conjunta` también escribe L0TF (el L0 tfidf que alimenta a la cabeza; `l0tf_max_mb` topa su tabla de coeficientes podando el
    vocabulario por frecuencia, `l0tf_f16` los guarda en media precisión). `validacion` (JSONL/CSV de texto y etiqueta, fuera de `ejemplos`) fija el τ de L2c sobre esas filas; sin ella, `margen` y `suelo` (H2 de T4.6c). `modelo_l2` = (ModeloL2, Codificador) ya cargados, en vez de leer `ckpt` (tests)."""
    if torre:  # valida antes de entrenar nada: un ONNX malo falla en segundos
        from .torre import validar_torre
        torre = validar_torre(torre, torre_dim, torre_max_len, torre_prefijo, log)
        if l2 and Path(l2).is_file():  # con --l2 se sabe ya: falla antes de entrenar
            from .torre import comprobar_dim_l2
            comprobar_dim_l2(formato.leer(Path(l2).read_bytes()), torre["dim"])
    inf = _entrenar(ejemplos, esquema, salida, l1=l1, ckpt=ckpt, l2=l2, repo=repo, pregunta=pregunta, semilla=semilla,
                    frac_valid=frac_valid, l0_max_mb=l0_max_mb, usar_go=usar_go, conjunta=conjunta, modelo_l2=modelo_l2,
                    l0tf_f16=l0tf_f16, l0tf_max_mb=l0tf_max_mb, precision_objetivo=precision_objetivo, validacion=validacion,
                    margen=margen, suelo=suelo, tope_tau=tope_tau, log=log)
    if torre:
        from .torre import anadir_torr
        anadir_torr(salida, torre, inf)
        log(f"TORR: dim {torre['dim']}, max_len {torre['max_len']}, prefijo {torre['prefijo']!r}, {len(torre['onnx'])} bytes de ONNX")
    return inf


def _entrenar(ejemplos, esquema, salida, *, l1, ckpt, l2, repo, pregunta, semilla, frac_valid, l0_max_mb, usar_go, conjunta,
              modelo_l2, l0tf_f16, l0tf_max_mb, precision_objetivo, validacion, margen, suelo, tope_tau, log) -> dict:
    t0 = time.time()
    q, extra = cargar_esquema(esquema, pregunta)
    if l1 and not Path(l1).is_file():
        raise ChispaError(f"--l1: no existe {l1}")
    salida = Path(salida)
    if not ejemplos:
        if conjunta:
            raise ChispaError("--conjunta es el modo «con datos del cliente»: necesita --ejemplos (train etiquetado)")
        salida.parent.mkdir(parents=True, exist_ok=True)
        return _zero_shot(q, extra, l1, l2, ckpt, encontrar_repo(repo), salida, t0, log)
    ex = cargar_ejemplos(ejemplos, q.id)
    cuenta = validar(ex, q)
    log(f"{len(ex)} ejemplos, {len(cuenta)} clases (mín {min(cuenta.values())}, máx {max(cuenta.values())})")
    if conjunta and min(cuenta.values()) < MIN_CONJ_POR_OPCION:
        log(f"AVISO: --conjunta necesita al menos {MIN_CONJ_POR_OPCION} ejemplos por opción (mín {min(cuenta.values())}): "
            "sin cabeza conjunta ni L0TF, se entrena en few-shot")
        conjunta = False
    sin_l0 = min(cuenta.values()) < MIN_L0_POR_OPCION
    if sin_l0:
        log(f"few-shot: {min(cuenta.values())} ejemplos en la opción con menos (< {MIN_L0_POR_OPCION}): sin L0, "
            "L1 se calibra con todos los ejemplos")
    salida.parent.mkdir(parents=True, exist_ok=True)
    repo, go = encontrar_repo(repo), encontrar_go()
    fuentes = fuentes_go(repo)
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
        if not (usar_go and fuentes and go):
            if conjunta:
                raise ChispaError("--conjunta necesita el entrenador de Go (instala Go) y el repositorio (--repo o CHISPA_REPO)")
            motivo = ("desactivado" if not usar_go else "no hay Go en el PATH (instala Go ≥ 1.27 para entrenar L0)" if not go
                      else "el wheel no trae las fuentes de Go y no se encuentra el repositorio (--repo o CHISPA_REPO)")
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
                                               cargar_ejemplos(validacion, q.id) if validacion else None, margen, suelo, tope_tau)
            conj_inf["s"] = time.time() - t
            conj_ruta, l0tf_ruta = str(tmp / "conj.bin"), str(tmp / "l0tf.bin")
            Path(conj_ruta).write_bytes(b)
            Path(l0tf_ruta).write_bytes(b_l0)
        with open(tmp / "ej.jsonl", "w", encoding="utf-8") as f:
            for t_, e in ex:
                f.write(json.dumps({"text": t_, "label": e}, ensure_ascii=False) + "\n")
        plan = {"ejemplos": str(tmp / "ej.jsonl"), "salida": str(salida.resolve()), "semilla": semilla,
                "frac_valid": frac_valid, "l0_max_mb": l0_max_mb, "sin_l0": sin_l0, "l1": str(Path(l1).resolve()) if l1 else "", "l2_chispa": str(l2_ch),
                "conj": conj_ruta, "l0tf": l0tf_ruta, "tau_l2c": (conj_inf or {}).get("tau_l2c"),
                "pregunta": {"id": q.id, "texto": q.question, "kind": q.kind,
                             "opciones": [{"id": o.id, "description": o.description} for o in q.options]},
                "meta": {"version": 1, "tareas": [q.id], "licencias": extra["licencias"], "dorado": extra["dorado"]}}
        (tmp / "plan.json").write_text(json.dumps(plan, ensure_ascii=False))
        d = preparar_go(tmp, fuentes)
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
            f"{conj_inf['precision_esperada']:.3f}, cobertura esperada {conj_inf['cobertura_esperada']:.3f})"
            + (f"; tope de τ {conj_inf['tope_tau']} aplicado" if conj_inf.get("tope_tau_aplicado") else ""))
    inf["omitidas"] = inf.get("omitidas") or {}
    for k, v in inf["omitidas"].items():
        log(f"AVISO: sin {k}: {v}")
    inf["modo"] = "con datos del cliente" if conj_inf else "few-shot"
    log(f"{salida}: {'+'.join(inf['secciones'])}, {inf['bytes']} bytes, "
        + ("" if sin_l0 else f"L0 validación {inf['l0_valid_acc']:.3f}, ") + f"{inf['reloj_s']:.1f} s")
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
    return {"salida": str(salida), "modo": "few-shot", "secciones": [nombres[t] for t in sorted(secs)], "omitidas": omitidas,
            "bytes": salida.stat().st_size, "tiempos_s": {}, "reloj_s": time.time() - t0, "l0_valid_acc": 0.0}
