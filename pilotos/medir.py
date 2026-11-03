#!/usr/bin/env python3
"""Mide un `chispa-server` con casos etiquetados y saca las métricas de `pilotos/metrica.md`.

Solo biblioteca estándar. Entrada: un JSONL, un caso por línea:

    {"id": "c1", "state": "me cobraron dos veces", "question": "¿Qué tipo de mensaje es?",
     "kind": "choice", "options": ["peticion", "queja", {"id": "reclamo", "description": "exige corregir"}],
     "gold": "reclamo"}

`id` y `kind` (por defecto `choice`) son opcionales; `question` y `options` también si se dan `--pregunta` y `--opciones`.
`gold` es el id de la opción correcta (noul: true/false; score: 1..K). Cada caso es una petición a `POST /v1/decide`.

Salida: JSON (`--salida PREFIJO` escribe PREFIJO.json y PREFIJO.md; sin él, el JSON va a stdout) y una tabla Markdown
para pegar en `pilotos/plantilla-informe.md`. La clave de API, si el servidor la pide, se lee de una variable de entorno
(`--clave-env`, por defecto CHISPA_CLAVE): no se pasa por la línea de comandos.

    python3 pilotos/medir.py --url http://127.0.0.1:8090 --casos casos.jsonl --salida informe-humo
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

PRECISION_OBJETIVO = 0.95


class ErrorDeCaso(Exception):
    """Un caso que el servidor rechazó o no contestó; `fatal` si es del contrato (4xx salvo 429)."""

    def __init__(self, msg, codigo=None, fatal=False):
        super().__init__(msg)
        self.codigo, self.fatal = codigo, fatal


# --- entrada ---

def _id_opcion(o):
    return str(o["id"] if isinstance(o, dict) else o)


def leer_casos(ruta, pregunta=None, opciones=None, tipo="choice"):
    casos = []
    with open(ruta, encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            if not linea.strip():
                continue
            try:
                r = json.loads(linea)
            except ValueError as e:
                raise ValueError(f"{ruta}:{n}: JSON inválido: {e}")
            for campo in ("state", "gold"):
                if campo not in r:
                    raise ValueError(f"{ruta}:{n}: falta «{campo}»")
            ops = r.get("options") if r.get("options") is not None else opciones
            preg = r.get("question") or pregunta
            if not ops or not preg:
                raise ValueError(f"{ruta}:{n}: faltan «options» o «question» (y no hay --opciones/--pregunta)")
            ops = [o if isinstance(o, dict) else {"id": str(o)} for o in ops]
            gold = r["gold"]
            gold = str(gold).lower() if isinstance(gold, bool) else str(gold)
            if (r.get("kind") or tipo) == "choice" and gold not in {_id_opcion(o) for o in ops}:
                raise ValueError(f"{ruta}:{n}: gold «{gold}» no es una de las opciones")
            casos.append({"id": str(r.get("id", n)), "state": r["state"], "question": preg,
                          "kind": r.get("kind") or tipo, "options": ops, "gold": gold})
    if not casos:
        raise ValueError(f"{ruta}: sin casos")
    return casos


# --- llamada al servidor ---

def decidir(url, caso, clave=None, timeout=30.0, reintentos=2):
    """Una petición a /v1/decide con el caso. Devuelve {answer, probs, layer, escalate, reason, ms, cliente_ms}."""
    cuerpo = json.dumps({"state": caso["state"], "questions": [
        {"id": "q", "question": caso["question"], "kind": caso["kind"], "options": caso["options"]}]}).encode()
    cab = {"Content-Type": "application/json"}
    if clave:
        cab["Authorization"] = "Bearer " + clave
    ultimo = None
    for intento in range(reintentos + 1):
        t0 = time.perf_counter()
        req = urllib.request.Request(url.rstrip("/") + "/v1/decide", data=cuerpo, headers=cab, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                datos = json.loads(r.read())
            cliente_ms = (time.perf_counter() - t0) * 1000
            res = datos["results"][0]
            return {"answer": str(res.get("answer", "")), "probs": res.get("probs") or {}, "layer": res.get("layer", ""),
                    "escalate": bool(res.get("escalate")), "reason": res.get("escalate_reason", ""),
                    "ms": res.get("ms"), "cliente_ms": cliente_ms}
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read()).get("error", {})
            except Exception:
                err = {}
            finally:
                e.close()
            codigo = err.get("code") or str(e.code)
            ultimo = ErrorDeCaso(f"HTTP {e.code} {codigo}: {err.get('message', '')}".strip(), codigo=codigo,
                                 fatal=400 <= e.code < 500 and e.code != 429)
            # 503 timeout y 504 no se reintentan (docs/operacion.md); 429 y el resto de 503 sí, con la espera pedida.
            if ultimo.fatal or e.code == 504 or codigo == "timeout" or intento == reintentos:
                raise ultimo
            time.sleep(min(float(e.headers.get("Retry-After") or 0.2 * (intento + 1)), 5.0))
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError) as e:
            ultimo = ErrorDeCaso(f"{type(e).__name__}: {e}")
            if intento == reintentos:
                raise ultimo
            time.sleep(0.2 * (intento + 1))
    raise ultimo  # pragma: no cover


def correr(url, casos, clave=None, concurrencia=4, timeout=30.0, reintentos=2):
    """Lista de (caso, predicción | None, error | None) en el orden de `casos`. El primer caso va solo: si el contrato
    lo rechaza (esquema o clave mal), se detiene toda la medición con ErrorDeCaso."""
    def uno(c):
        try:
            return c, decidir(url, c, clave, timeout, reintentos), None
        except ErrorDeCaso as e:
            return c, None, e
    primero = uno(casos[0])
    if primero[2] is not None and primero[2].fatal:
        raise primero[2]
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, concurrencia)) as ex:
        resto = list(ex.map(uno, casos[1:]))
    return [primero] + resto, time.perf_counter() - t0


# --- métricas ---

def percentil(valores, p):
    """Rango más cercano: sin interpolar. None si no hay valores."""
    if not valores:
        return None
    v = sorted(valores)
    return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def f1_macro(gold, pred):
    """Media del F1 de cada clase que aparece en `gold`. Una predicción "" no es de ninguna clase (cuenta como fallo)."""
    clases = sorted(set(gold))
    fs = []
    for c in clases:
        tp = sum(1 for g, p in zip(gold, pred) if g == c and p == c)
        fp = sum(1 for g, p in zip(gold, pred) if g != c and p == c)
        fn = sum(1 for g, p in zip(gold, pred) if g == c and p != c)
        fs.append(0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return sum(fs) / len(fs) if fs else None


def cobertura_a_precision(conf, acierto, objetivo):
    """Mayor fracción de filas, tomadas de la más a la menos confiada, cuya precisión llega al objetivo (umbral único).
    Devuelve (cobertura, umbral). (0.0, None) si ni la fila más confiada llega."""
    orden = sorted(range(len(conf)), key=lambda i: -conf[i])
    mejor, ok = (0.0, None), 0
    for k, i in enumerate(orden, 1):
        ok += acierto[i]
        # solo se corta entre confianzas distintas: un umbral no separa empates
        if (k == len(orden) or conf[orden[k]] < conf[i]) and ok / k >= objetivo:
            mejor = (k / len(orden), conf[i])
    return mejor


def resumen_lat(v):
    return {"p50": percentil(v, 50), "p95": percentil(v, 95), "p99": percentil(v, 99), "max": max(v) if v else None}


def metricas(resultados, objetivo=PRECISION_OBJETIVO, duracion_s=None, precio_hora=None):
    ok = [(c, p) for c, p, e in resultados if p is not None]
    errores = Counter(str(e) for _, p, e in resultados if p is None)
    n = len(ok)
    m = {"n_casos": len(resultados), "n_medidos": n, "errores": sum(errores.values()), "errores_por_causa": dict(errores)}
    if not n:
        return m
    gold = [c["gold"] for c, _ in ok]
    mejor = [p["answer"] for _, p in ok]
    escala = [p["escalate"] for _, p in ok]
    efectiva = ["" if e else a for a, e in zip(mejor, escala)]   # lo que ve la operación: escalar = fallo
    acierto = [int(g == a) for g, a in zip(gold, mejor)]
    aceptadas = [i for i in range(n) if not escala[i]]
    conf = [max(p["probs"].values(), default=0.0) for _, p in ok]
    cob, umbral = cobertura_a_precision(conf, acierto, objetivo)
    m.update({
        "exactitud": sum(acierto) / n,
        "exactitud_escala_es_fallo": sum(int(g == a) for g, a in zip(gold, efectiva)) / n,
        "f1_macro_escala_es_fallo": f1_macro(gold, efectiva),
        "f1_macro_mejor_respuesta": f1_macro(gold, mejor),
        "escalado": sum(escala) / n,
        "precision_de_lo_contestado": (sum(acierto[i] for i in aceptadas) / len(aceptadas)) if aceptadas else None,
        "precision_objetivo": objetivo, "cobertura_a_precision_objetivo": cob, "umbral_de_confianza": umbral,
        "por_opcion": {c: n_c for c, n_c in sorted(Counter(gold).items())},
    })
    capas = Counter(p["layer"] for _, p in ok)
    m["por_capa"] = {c: {"n": k, "pct": k / n,
                         "exactitud": sum(acierto[i] for i in range(n) if ok[i][1]["layer"] == c) / k}
                     for c, k in sorted(capas.items())}
    m["escalados_por_motivo"] = dict(Counter(p["reason"] or "sin_motivo" for _, p in ok if p["escalate"]))
    m["confusiones"] = [{"gold": g, "pred": a or "(escalado)", "n": k} for (g, a), k in Counter(
        (g, a) for g, a in zip(gold, efectiva) if g != a).most_common(5)]
    m["latencia_cliente_ms"] = resumen_lat([p["cliente_ms"] for _, p in ok])
    m["latencia_servidor_ms"] = resumen_lat([p["ms"] for _, p in ok if isinstance(p["ms"], (int, float))])
    if duracion_s and duracion_s > 0:
        m["decisiones_por_s"] = n / duracion_s
        if precio_hora is not None:
            m["coste_por_1000"] = precio_hora / (n / duracion_s * 3600) * 1000
    return m


# --- salida ---

def _pct(x):
    return "sin medir" if x is None else f"{100 * x:.1f} %".replace(".", ",")


def _f(x, d=3):
    return "sin medir" if x is None else f"{x:.{d}f}".replace(".", ",")


def _ms(x):
    return "sin medir" if x is None else f"{x:.1f}".replace(".", ",")


def tabla_markdown(m):
    if not m.get("n_medidos"):
        return f"Sin casos medidos ({m['errores']} errores).\n"
    L, S = m["latencia_cliente_ms"], m["latencia_servidor_ms"]
    f = [f"| Métrica | Valor |", "|---|---|",
         f"| Casos medidos / con error | {m['n_medidos']} / {m['errores']} |",
         f"| Exactitud (mejor respuesta) | {_f(m['exactitud'])} |",
         f"| Exactitud (escalar = fallo) | {_f(m['exactitud_escala_es_fallo'])} |",
         f"| F1 macro (escala = fallo) | {_f(m['f1_macro_escala_es_fallo'])} |",
         f"| F1 macro (mejor respuesta) | {_f(m['f1_macro_mejor_respuesta'])} |",
         f"| Tasa de escalado | {_pct(m['escalado'])} |",
         f"| Precisión de lo contestado | {_f(m['precision_de_lo_contestado'])} |",
         f"| Cobertura a precisión {str(m['precision_objetivo']).replace('.', ',')} | {_pct(m['cobertura_a_precision_objetivo'])}"
         f" (umbral {_f(m['umbral_de_confianza'])}) |",
         f"| Latencia cliente p50 / p95 / p99 (ms) | {_ms(L['p50'])} / {_ms(L['p95'])} / {_ms(L['p99'])} |",
         f"| Latencia servidor p50 / p95 / p99 (ms) | {_ms(S['p50'])} / {_ms(S['p95'])} / {_ms(S['p99'])} |"]
    if "decisiones_por_s" in m:
        f.append(f"| Decisiones/s de esta corrida (con la concurrencia pedida) | {_f(m['decisiones_por_s'], 1)} |")
    if "coste_por_1000" in m:
        f.append(f"| Coste por 1 000 decisiones (con ese ritmo y el precio dado) | {_f(m['coste_por_1000'], 4)} |")
    f += ["", "| Capa | n | % | Exactitud |", "|---|---|---|---|"]
    f += [f"| {c} | {d['n']} | {_pct(d['pct'])} | {_f(d['exactitud'])} |" for c, d in m["por_capa"].items()]
    if m["escalados_por_motivo"]:
        f += ["", "| Motivo de escalado | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in m["escalados_por_motivo"].items()]
    if m["confusiones"]:
        f += ["", "| Real → predicho | n |", "|---|---|"] + [f"| {c['gold']} → {c['pred']} | {c['n']} |" for c in m["confusiones"]]
    f += ["", "| Opción | casos |", "|---|---|"] + [f"| {k} | {v} |" for k, v in m["por_opcion"].items()]
    if m["errores_por_causa"]:
        f += ["", "| Error | n |", "|---|---|"] + [f"| {k} | {v} |" for k, v in m["errores_por_causa"].items()]
    return "\n".join(f) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", required=True, help="base del servidor, p. ej. http://127.0.0.1:8090")
    ap.add_argument("--casos", required=True, help="JSONL de casos etiquetados")
    ap.add_argument("--pregunta", help="texto de la pregunta para los casos que no traen «question»")
    ap.add_argument("--opciones", nargs="+", help="ids de opción para los casos que no traen «options»")
    ap.add_argument("--tipo", default="choice", choices=["choice", "noul", "score", "multi"])
    ap.add_argument("--clave-env", default="CHISPA_CLAVE", help="variable de entorno con la clave de API (si el servidor la pide)")
    ap.add_argument("--precision-objetivo", type=float, default=PRECISION_OBJETIVO)
    ap.add_argument("--concurrencia", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--reintentos", type=int, default=2)
    ap.add_argument("--precio-hora", type=float, help="precio de la máquina por hora (da el coste por 1 000 con el ritmo de esta corrida)")
    ap.add_argument("--salida", help="prefijo: escribe PREFIJO.json y PREFIJO.md")
    a = ap.parse_args(argv)
    try:
        casos = leer_casos(a.casos, a.pregunta, a.opciones, a.tipo)
        res, dur = correr(a.url, casos, os.environ.get(a.clave_env) or None, a.concurrencia, a.timeout, a.reintentos)
    except (ValueError, OSError) as e:
        print(f"medir: {e}", file=sys.stderr)
        return 2
    except ErrorDeCaso as e:
        print(f"medir: el servidor rechazó el primer caso, se detiene: {e}", file=sys.stderr)
        return 2
    m = metricas(res, a.precision_objetivo, dur, a.precio_hora)
    js, md = json.dumps(m, ensure_ascii=False, indent=2), tabla_markdown(m)
    if a.salida:
        with open(a.salida + ".json", "w", encoding="utf-8") as f:
            f.write(js + "\n")
        with open(a.salida + ".md", "w", encoding="utf-8") as f:
            f.write(md)
        print(md)
    else:
        print(js)
        print(md, file=sys.stderr)
    return 0 if m.get("n_medidos") else 1


if __name__ == "__main__":
    sys.exit(main())
