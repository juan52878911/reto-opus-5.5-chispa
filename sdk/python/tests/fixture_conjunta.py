"""Fixture de paridad Go ↔ Python de la cabeza conjunta (T2.6b).

    python -m tests.fixture_conjunta [salida.json]     (desde sdk/python, con el repo en CHISPA_REPO o como ancestro)

Entradas fijas (semilla 0): prototipos cuantizados a int8, ranuras S, similitudes MaxSim y probabilidades de L0.
Salida esperada: simproto y P_L2 en doble precisión con numpy, y las probabilidades de `conjunta.Cabeza.probs`
(la cabeza `lr` de `model/l2/conjunta.py`, sin copiarla). Go lee el JSON y debe coincidir con |Δp| ≤ 1e-4."""
import base64
import json
import sys
from pathlib import Path

import numpy as np

from chispa import formato
from chispa.train import encontrar_repo

PREGUNTA = "¿Qué quiere el cliente?"
CLASES = ["facturas", "envíos", "garantía", "devolución", "cuenta", "otros"]  # orden del esquema
EN_CONJ = ["cuenta", "devolución", "envíos", "facturas", "garantía"]  # «otros» no tiene prototipo
K, D, CASOS = 4, 16, 8
T, BETA = 0.4, 1.5
ESC = [1.3, 0.2, 0.8]
W = [1.1, 0.7, 0.9, 0.3, -0.2, 0.15]
RUTA = Path(encontrar_repo() or ".") / "model/l2/tests/fixtures_conjunta/paridad.json"


def _softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()


def generar():
    repo = encontrar_repo()
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from model.l2 import conjunta as C

    rs = np.random.RandomState(0)
    P = rs.randn(len(EN_CONJ), K, D)
    P /= np.linalg.norm(P, axis=-1, keepdims=True)
    escala, proto = formato.cuantizar_protos(P)
    Pq = proto.astype(np.float64) * escala.astype(np.float64)[..., None]  # lo que ve el servidor
    ops = sorted(CLASES)
    seccion = formato.conj([{"hash": formato.hash_esquema(PREGUNTA, ops), "T": T, "beta": BETA, "esc": ESC, "w": W,
                             "clases": EN_CONJ, "escala": escala, "proto": proto}])
    cab = C.Cabeza("lr", 0.0)
    cab.w, cab.esc = __import__("torch").tensor(W, dtype=__import__("torch").double), list(ESC)
    casos = []
    for _ in range(CASOS):
        S = rs.randn(K, D) * 0.6
        sims = rs.rand(len(CLASES))
        l0 = rs.dirichlet(np.ones(len(CLASES)) * 2.0)
        sp = np.zeros(len(CLASES))
        for i, c in enumerate(CLASES):
            if c in EN_CONJ:
                sp[i] = (S @ Pq[EN_CONJ.index(c)].reshape(-1, D).T).reshape(K, K).max(1).mean()
        l2 = _softmax((sims + BETA * sp) / T)
        probs = cab.probs(l0[None], sp[None], l2[None])[0]
        casos.append({"S": S.tolist(), "sims": sims.tolist(), "l0": dict(zip(CLASES, l0.tolist())),
                      "sp": sp.tolist(), "l2": l2.tolist(), "probs": probs.tolist()})
    return {"pregunta": PREGUNTA, "opciones": CLASES, "T": T, "beta": BETA, "K": K, "d": D, "tolerancia": 1e-4,
            "conj_b64": base64.b64encode(seccion).decode(), "casos": casos}


if __name__ == "__main__":
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else RUTA
    ruta.write_text(json.dumps(generar(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(ruta)
