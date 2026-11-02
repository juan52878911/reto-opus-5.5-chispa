"""Cálculo PURO del panel derecho del vídeo (sin Pillow ni ffmpeg): de un turno de la traza a datos listos para dibujar."""
from __future__ import annotations

from typing import List, Optional

from . import api

ETIQUETA_BAJO_TAU = "bajo τ: el servidor escalaría"
CAPAS = ("L0", "L1", "L2", "escalar")


def acumulado_inicial() -> dict:
    return {"decisiones": 0, "ms_total": 0.0, "escudo": 0, "bajo_tau": 0}


def acumular(ac: dict, turno: dict) -> dict:
    """Nuevo acumulado tras el turno (no muta). Las jugadas forzadas no cuentan como decisión."""
    if turno.get("forzada") or turno.get("ms_cliente") is None and not turno.get("escudo"):
        return dict(ac)
    return {"decisiones": ac["decisiones"] + 1, "ms_total": ac["ms_total"] + (turno.get("ms_cliente") or 0.0),
            "escudo": ac["escudo"] + (1 if turno.get("escudo") else 0),
            "bajo_tau": ac.get("bajo_tau", 0) + (1 if turno.get("decidio") == "chispa_bajo_tau" else 0)}


def _p(d: dict, k: str) -> float:
    try:
        return float(d.get(k, 0.0))
    except (TypeError, ValueError):
        return 0.0


def calcular_panel(turno: dict, ac: dict, modo: str = "tau") -> dict:
    """`ac` es el acumulado INCLUYENDO este turno (ver `acumular`)."""
    q = turno.get("preguntas", {})
    ch, rs, nu = q.get(api.ID_COLOCACION, {}), q.get(api.ID_RIESGO, {}), q.get(api.ID_COMPLETA, {})
    chprobs = ch.get("probs") or {}
    elegida = turno.get("elegida")
    barras = [{"id": o["id"], "prob": _p(chprobs, o["id"]), "descripcion": o["descripcion"],
               "elegida": o["id"] == elegida} for o in turno.get("opciones", [])]
    bajo_tau = turno.get("decidio") == "chispa_bajo_tau"
    if turno.get("forzada"):
        jugada = "jugada forzada (una sola colocación)"
    elif turno.get("escudo"):
        jugada = f"escudo: juega el profesor (columna {turno['col']}, giro {turno['rot']})"
    else:
        d = next((o["descripcion"] for o in turno.get("opciones", []) if o["id"] == elegida), "")
        jugada = f"{'argmax' if bajo_tau else 'opción'} {elegida}: columna {turno['col']}, giro {turno['rot']} — {d}"
    niveles = [str(i) for i in range(1, len(api.NIVELES_RIESGO) + 1)]
    rprobs = rs.get("probs") or {}
    try:
        riesgo = int(rs.get("answer")) if rs.get("answer") and not rs.get("escalate") else None
    except ValueError:
        riesgo = None
    p_si = _p(nu.get("probs") or {}, "true")
    if nu.get("escalate") or not nu.get("answer"):
        si_no = None
    else:
        si_no = nu["answer"] == "true"
    capa = "escalar" if ch.get("escalate") else (ch.get("layer") or "—")
    seg = ac["ms_total"] / 1000.0
    return {
        "jugada": jugada,
        "barras": barras,
        "riesgo": {"nivel": riesgo, "niveles": [{"id": n, "prob": _p(rprobs, n)} for n in niveles]},
        "completa": {"si": si_no, "p_si": p_si if (nu.get("probs")) else None,
                     "texto": "—" if si_no is None else ("sí" if si_no else "no")},
        "capa": capa,
        "capas": [{"id": c, "activa": c == capa} for c in CAPAS],
        "latencia_ms": turno.get("ms_cliente"),
        "decisiones_por_s": (ac["decisiones"] / seg) if seg > 0 else None,
        "escudo": ac["escudo"],
        "bajo_tau": ac.get("bajo_tau", 0),
        "etiqueta_bajo_tau": ETIQUETA_BAJO_TAU if bajo_tau else None,
        "modo": modo,
        "decisiones": ac["decisiones"],
        "puntos": turno.get("puntos", 0),
        "filas": turno.get("filas_total", 0),
        "turno": turno.get("turno"),
    }


def paneles(turnos: List[dict], modo: str = "tau") -> List[dict]:
    """Un panel por turno con su acumulado."""
    ac, out = acumulado_inicial(), []
    for t in turnos:
        ac = acumular(ac, t)
        out.append(calcular_panel(t, ac, modo))
    return out
