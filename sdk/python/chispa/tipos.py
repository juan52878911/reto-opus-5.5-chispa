"""Tipos de petición y respuesta de `/v1/decide` (contrato en `server/README.md`)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Union

KINDS = ("choice", "noul", "score")


@dataclass(frozen=True)
class Opcion:
    id: str
    description: str = ""

    def a_json(self) -> dict:
        d = {"id": self.id}
        if self.description:
            d["description"] = self.description
        return d


def _opciones(ops: Sequence[Union[str, Opcion, tuple, dict]]) -> List[Opcion]:
    out = []
    for o in ops:
        if isinstance(o, Opcion):
            out.append(o)
        elif isinstance(o, str):
            out.append(Opcion(o))
        elif isinstance(o, dict):
            out.append(Opcion(str(o["id"]), o.get("description", "")))
        else:
            out.append(Opcion(str(o[0]), o[1] if len(o) > 1 else ""))
    return out


@dataclass(frozen=True)
class Pregunta:
    """Una pregunta; usa `Choice`, `Noul` o `Score`."""
    id: str
    question: str
    kind: str
    options: tuple = ()
    nonce: Optional[str] = None

    def a_json(self) -> dict:
        d = {"id": self.id, "question": self.question, "kind": self.kind}
        if self.options:
            d["options"] = [o.a_json() for o in self.options]
        if self.nonce is not None:
            d["nonce"] = self.nonce
        return d


def Choice(id: str, question: str, options, nonce: Optional[str] = None) -> Pregunta:
    """Elegir una opción: ≥ 2 con `id` único (`str`, `Opcion`, `(id, descripción)` o `{"id", "description"}`)."""
    ops = _opciones(options)
    if len(ops) < 2:
        raise ValueError("choice necesita ≥ 2 opciones")
    if len({o.id for o in ops}) != len(ops):
        raise ValueError("choice: ids de opción repetidos")
    return Pregunta(id, question, "choice", tuple(ops), nonce)


def Noul(id: str, question: str, nonce: Optional[str] = None) -> Pregunta:
    """Pregunta booleana: la respuesta es `"true"` o `"false"`."""
    return Pregunta(id, question, "noul", (), nonce)


def Score(id: str, question: str, niveles: int, nonce: Optional[str] = None) -> Pregunta:
    """Ordinal de 1 a `niveles` (≥ 2); la respuesta es `"1"…"K"`."""
    if niveles < 2:
        raise ValueError("score necesita ≥ 2 niveles")
    return Pregunta(id, question, "score", tuple(Opcion(str(i)) for i in range(1, niveles + 1)), nonce)


@dataclass(frozen=True)
class Resultado:
    id: str
    kind: str
    answer: str  # "" si ninguna capa opinó
    probs: Dict[str, float] = field(default_factory=dict)
    layer: str = ""
    escalate: bool = False
    ms: float = 0.0
    nonce: Optional[str] = None

    @classmethod
    def de_json(cls, d: dict) -> "Resultado":
        return cls(id=d["id"], kind=d["kind"], answer=d.get("answer", ""), probs=dict(d.get("probs") or {}),
                   layer=d.get("layer", ""), escalate=bool(d.get("escalate", False)), ms=float(d.get("ms", 0.0)),
                   nonce=d.get("nonce"))

    @property
    def verdadero(self) -> Optional[bool]:
        """En `noul`: la respuesta como bool (None si no hay)."""
        return {"true": True, "false": False}.get(self.answer)

    @property
    def nivel(self) -> Optional[int]:
        """En `score`: el nivel como entero (None si no hay)."""
        return int(self.answer) if self.answer.isdigit() else None
