"""Cabeza tipada: vector de audio + opciones → la misma respuesta que `POST /v1/decide` (choice/score/noul)."""
import hashlib
import time
from dataclasses import dataclass, field

import numpy as np

KINDS = ("choice", "score", "noul")
CAPA_AUDIO = "A1"
CAPA_ESCALAR = "escalar"  # igual que decide.CapaEscalar del servidor


class ErrPregunta(ValueError):
    """Pregunta inválida; el mensaje lleva la ruta del campo, como el 400 del servidor."""


@dataclass
class Opcion:
    id: str
    description: str = ""


@dataclass
class Pregunta:
    id: str
    question: str
    kind: str
    options: list = field(default_factory=list)
    nonce: str = ""

    def validar(self, ruta="questions[0]"):
        if not self.id:
            raise ErrPregunta(f"{ruta}.id: obligatorio")
        if not self.question:
            raise ErrPregunta(f"{ruta}.question: obligatorio")
        if self.kind not in KINDS:
            raise ErrPregunta(f'{ruta}.kind: "{self.kind}" no válido (choice, score o noul)')
        ids = [o.id for o in self.options]
        if len(set(ids)) != len(ids):
            raise ErrPregunta(f"{ruta}.options: ids repetidos")
        if self.kind == "noul":
            if ids and sorted(ids) != ["false", "true"]:
                raise ErrPregunta(f'{ruta}.options: en noul solo "false" y "true"')
        elif len(ids) < 2:
            raise ErrPregunta(f"{ruta}.options: {self.kind} necesita al menos 2 opciones")
        if self.kind == "score" and ids != [str(i) for i in range(1, len(ids) + 1)]:
            raise ErrPregunta(f'{ruta}.options: score pide ids "1"…"K" en orden')

    def opciones(self):
        return self.options or [Opcion("false"), Opcion("true")]


@dataclass
class Resultado:
    id: str
    kind: str
    answer: str
    probs: dict
    layer: str
    escalate: bool
    ms: float
    nonce: str = ""

    def a_dict(self):
        """Mismas claves que el JSON de /v1/decide (`nonce` solo si hay)."""
        d = {"id": self.id, "kind": self.kind, "answer": self.answer, "probs": self.probs,
             "layer": self.layer, "escalate": self.escalate, "ms": self.ms}
        if self.nonce:
            d["nonce"] = self.nonce
        return d


class TorresFalsas:
    """Torre de opción de mentira: vector unitario determinista por (pregunta, opción). Sustituye al texto → espacio de audio."""

    def __init__(self, dim=32):
        self.dim = dim

    def vector(self, pregunta, opcion):
        h = hashlib.sha256(f"{pregunta.question}\x00{opcion.id}\x00{opcion.description}".encode()).digest()
        v = np.random.default_rng(int.from_bytes(h[:8], "little")).standard_normal(self.dim)
        return (v / np.linalg.norm(v)).astype(np.float32)


class Cabeza:
    """softmax(cos(audio, torre_opción) / T). Si la confianza top-1 < tau → escalar, con la mejor respuesta como pista."""

    def __init__(self, torres, temperatura=0.1, tau=0.6):
        self.torres, self.T, self.tau = torres, temperatura, tau

    def decidir(self, vector, pregunta, ruta="questions[0]"):
        t0 = time.perf_counter()
        pregunta.validar(ruta)
        ops = pregunta.opciones()
        sims = np.array([float(np.dot(vector, self.torres.vector(pregunta, o))) for o in ops]) / self.T
        p = np.exp(sims - sims.max())
        p /= p.sum()
        mejor = int(np.argmax(p))
        esc = bool(p[mejor] < self.tau)
        return Resultado(pregunta.id, pregunta.kind, ops[mejor].id, {o.id: float(q) for o, q in zip(ops, p)},
                         CAPA_ESCALAR if esc else CAPA_AUDIO, esc, (time.perf_counter() - t0) * 1000, pregunta.nonce)

    def decidir_lote(self, vector, preguntas):
        ids = [q.id for q in preguntas]
        if len(set(ids)) != len(ids):
            raise ErrPregunta("questions: ids repetidos")
        return [self.decidir(vector, q, f"questions[{i}]") for i, q in enumerate(preguntas)]

    @staticmethod
    def sin_opinion(pregunta):
        """Sin señal que clasificar: como el servidor cuando ninguna capa opina (answer vacío, probs vacío)."""
        return Resultado(pregunta.id, pregunta.kind, "", {}, CAPA_ESCALAR, True, 0.0, pregunta.nonce)
