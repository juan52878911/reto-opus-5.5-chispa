"""Partida en tiempo real: el motor avanza a TICS_POR_S en su hilo; cada agente, en el suyo, pide decisión con el estado del
momento y su acción se aplica cuando llega (mientras tanto la pala sigue con la última). La latencia cuenta en el juego.

Agentes (interfaz `decidir(estado, opciones) -> Respuesta`):
- `AgenteChispa(url)`: `POST /v1/decide`; si escala, se juega el argmax de `probs` (modo demo) y se anota `bajo_tau`;
- `AgenteLaya(url)`: `POST /decide` de `laya_servidor.py` (envuelve `laya.Router.predict`, `[MASK]` por opción y softmax);
- `AgenteOptimo()`: la opción de menor distancia, sin red (tests y referencia)."""
from __future__ import annotations

import json
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from . import opciones as O
from .motor import LADOS, TICS_POR_S, Juego


class ErrorRed(Exception):
    pass


def _post(url: str, cuerpo: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ErrorRed(str(e)) from e


@dataclass
class Respuesta:
    id: Optional[str]
    probs: Dict[str, float]
    ms_servidor: Optional[float] = None
    bajo_tau: bool = False


class AgenteOptimo:
    nombre = "óptimo"

    def decidir(self, estado: str, ops: List[O.Opcion]) -> Respuesta:
        o = O.optima(ops)
        return Respuesta(o.id, {x.id: float(x.id == o.id) for x in ops})


class AgenteChispa:
    nombre = "Chispa"

    def __init__(self, url: str, timeout: float = 5.0):
        self.url, self.timeout = url.rstrip("/") + "/v1/decide", timeout

    def decidir(self, estado: str, ops: List[O.Opcion]) -> Respuesta:
        r = _post(self.url, O.peticion_chispa(estado, ops), self.timeout)
        ch = next((x for x in r.get("results", []) if x.get("id") == O.ID_PREGUNTA), {})
        probs = {k: float(v) for k, v in (ch.get("probs") or {}).items()}
        ids = [o.id for o in ops]
        if not ch.get("escalate") and ch.get("answer") in ids:
            return Respuesta(ch["answer"], probs, ch.get("ms"))
        elegido = max(ids, key=lambda i: probs.get(i, -1.0)) if probs else None
        return Respuesta(elegido, probs, ch.get("ms"), bajo_tau=True)


class AgenteLaya:
    nombre = "Laya"

    def __init__(self, url: str, timeout: float = 5.0):
        self.url, self.timeout = url.rstrip("/") + "/decide", timeout

    def decidir(self, estado: str, ops: List[O.Opcion]) -> Respuesta:
        r = _post(self.url, O.peticion_laya(estado, ops), self.timeout)
        probs = {k: float(v) for k, v in (r.get("probs") or {}).items()}
        ids = [o.id for o in ops]
        elegido = r.get("choice") if r.get("choice") in ids else (max(ids, key=lambda i: probs.get(i, -1.0)) if probs else None)
        return Respuesta(elegido, probs, r.get("ms"))


@dataclass
class Decision:
    lado: str
    tic_envio: int
    tic_aplicada: int
    ms: float
    ms_servidor: Optional[float]
    estado: str
    opciones: List[dict]
    elegida: Optional[str]
    optima: str
    probs: Dict[str, float]
    bajo_tau: bool = False
    error: str = ""


@dataclass
class Partida:
    juego: Juego
    agentes: Dict[str, object]
    semilla: int = 1
    tics: List[list] = field(default_factory=list)
    decisiones: List[Decision] = field(default_factory=list)

    def __post_init__(self):
        self.cerrojo = threading.Lock()
        self.parar = threading.Event()

    def _foto(self) -> list:
        e = self.juego.e
        return [e.tic, round(e.bx, 1), round(e.by, 1), round(e.palas["izquierda"], 1), round(e.palas["derecha"], 1),
                e.puntos["izquierda"], e.puntos["derecha"], e.acciones["izquierda"], e.acciones["derecha"]]

    def _motor(self, ritmo: float) -> None:
        dt = 1.0 / TICS_POR_S / ritmo
        siguiente = time.perf_counter()
        with self.cerrojo:
            self.tics.append(self._foto())
        while not self.parar.is_set():
            with self.cerrojo:
                self.juego.paso()
                self.tics.append(self._foto())
                if self.juego.e.terminada:
                    break
            siguiente += dt
            espera = siguiente - time.perf_counter()
            if espera > 0:
                time.sleep(espera)
        self.parar.set()

    def _agente(self, lado: str, agente) -> None:
        rng = random.Random(self.semilla * 7 + (1 if lado == "derecha" else 0))
        while not self.parar.is_set():
            with self.cerrojo:
                e = self.juego.e.copia()
            estado, ops = O.construir(e, lado, rng)
            opt = O.optima(ops)
            t0 = time.perf_counter()
            try:
                r = agente.decidir(estado, ops)
                err = ""
            except ErrorRed as ex:
                r, err = Respuesta(None, {}), str(ex)[:120]
            ms = (time.perf_counter() - t0) * 1000
            with self.cerrojo:
                elegida = next((o for o in ops if o.id == r.id), None)
                if elegida is not None:
                    self.juego.accion(lado, elegida.accion)
                tic = self.juego.e.tic
            self.decisiones.append(Decision(lado, e.tic, tic, round(ms, 2), r.ms_servidor, estado, [asdict(o) for o in ops],
                                            r.id, opt.id, r.probs, r.bajo_tau, err))
            if err:
                time.sleep(0.2)

    def jugar(self, ritmo: float = 1.0) -> None:
        hilos = [threading.Thread(target=self._motor, args=(ritmo,), daemon=True)]
        hilos += [threading.Thread(target=self._agente, args=(lado, ag), daemon=True) for lado, ag in self.agentes.items()]
        for h in hilos:
            h.start()
        hilos[0].join()
        for h in hilos[1:]:
            h.join(timeout=10)

    def resumen(self) -> dict:
        e = self.juego.e
        out = {"semilla": self.semilla, "tics": e.tic, "segundos": round(e.tic / TICS_POR_S, 1), "puntos": dict(e.puntos),
               "golpes": dict(e.golpes), "agentes": {}}
        for lado in LADOS:
            ds = [d for d in self.decisiones if d.lado == lado]
            ok = [d for d in ds if not d.error]
            lat = sorted(d.ms for d in ok)
            p = lambda q: round(lat[min(len(lat) - 1, int(q / 100 * len(lat)))], 1) if lat else None  # noqa: E731
            seg = e.tic / TICS_POR_S or 1
            out["agentes"][lado] = {
                "nombre": getattr(self.agentes.get(lado), "nombre", lado), "decisiones": len(ds), "errores": len(ds) - len(ok),
                "coincide_optima_pct": round(100 * sum(d.elegida == d.optima for d in ok) / len(ok), 1) if ok else None,
                "bajo_tau_pct": round(100 * sum(d.bajo_tau for d in ok) / len(ok), 1) if ok else None,
                "p50_ms": p(50), "p99_ms": p(99), "decisiones_por_s": round(len(ok) / seg, 1),
                "ms_servidor_p50": (sorted(d.ms_servidor for d in ok if d.ms_servidor is not None) or [None])[len(ok) // 2]
                if any(d.ms_servidor is not None for d in ok) else None}
        return out

    def guardar(self, ruta: str) -> None:
        with open(ruta, "w", encoding="utf-8") as f:
            json.dump({"resumen": self.resumen(), "tics": self.tics, "decisiones": [asdict(d) for d in self.decisiones]},
                      f, ensure_ascii=False)
