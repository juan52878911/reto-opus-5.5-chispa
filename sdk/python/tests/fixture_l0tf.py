"""Fixture de paridad Go ↔ sklearn del L0 TF-IDF (T4.5c).

    python -m tests.fixture_l0tf [directorio]     (desde sdk/python; por defecto server/decide/testdata/l0tf)

Entrena con `chispa.l0tf` (el `correr_l0` de las líneas base) sobre frases inventadas y escribe `modelo.l0tf` (sección L0TF
en f32), `modelo_f16.l0tf` (la misma en f16) y `frases.json`: ≥ 200 frases con tildes, emojis, mayúsculas y espacios raros,
con `predict_proba` de sklearn en doble precisión. Go debe coincidir con |Δp| ≤ 1e-5 (f32)."""
import json
import random
import sys
from pathlib import Path

from chispa import l0tf
from chispa.train import encontrar_repo

CLASES = {
    "facturas": ["factura", "cobro duplicado", "recibo", "IVA", "importe", "cargo en mi cuenta", "abono"],
    "envíos": ["envío", "paquete", "mensajería", "retraso en la entrega", "seguimiento", "dirección", "repartidor"],
    "garantía": ["garantía", "avería", "reparación", "defecto de fábrica", "sustitución", "no enciende", "cobertura"],
    "devolución": ["devolver", "reembolso", "cambio de talla", "me arrepiento", "plazo de devolución", "etiqueta"],
    "cuenta": ["contraseña", "iniciar sesión", "correo", "darme de baja", "perfil", "verificación", "acceso"],
    "otros": ["buenos días", "gracias", "¿Qué tal?", "opinión", "sugerencia", "queja", "horario"],
}
PREFIJOS = ["Hola,", "oye", "necesito saber", "quería preguntar", "por favor", "¿podéis ayudarme?", "urgente:", "ñandú"]
RAROS = ["😀", "🎉🎉", "ÁÉÍÓÚ ÜÑ", "İstanbul", "ΟΔΟΣ", "ΣΟΦΟΣ.", "naïve café", "é", "ǅ", "straße", "日本語", "x" * 40,
         "\t", " ", "　", " ", "\x1c", "\n", "  ", "a", "ab", "#", "¿?", "—", "'", "µ", "ﬁ"]
TRAIN_N, TEST_N = 40, 260


def frase(rng, clase):
    ps = rng.sample(CLASES[clase], rng.randint(1, 2)) + [rng.choice(PREFIJOS)]
    rng.shuffle(ps)
    return " ".join(ps)


def datos(semilla=0):
    rng = random.Random(semilla)
    train = [{"texto": frase(rng, c), "etiqueta": c} for c in CLASES for _ in range(TRAIN_N)]
    sep = [" ", "  ", "\t", " ", "　", "\n", "\x1c", " "]
    test = []
    for i in range(TEST_N):
        t = frase(rng, rng.choice(list(CLASES)))
        if i % 3 == 0:
            t = t.upper()
        elif i % 5 == 0:
            t = t.title()
        parts = t.split(" ")
        for j in range(rng.randint(0, 3)):
            parts.insert(rng.randint(0, len(parts)), rng.choice(RAROS))
        t = "".join(p + rng.choice(sep) for p in parts[:-1]) + parts[-1]
        if i % 17 == 0:
            t = rng.choice(sep) + t + rng.choice(sep)
        test.append(t)
    test += ["", " ", "   \t ", "x", "😀", "zzzzzzzz qqqqq", "ΣΑΣ ΑΣ Σ", "İİ", "ß", "a b c d e f g"]
    return train, test


def generar(destino, repo):
    import numpy as np
    train, test = datos()
    vec, clf = l0tf.ajustar(train, repo)
    sec32, sec16 = l0tf.seccion(vec, clf, False), l0tf.seccion(vec, clf, True)
    p = clf.predict_proba(vec.transform(test))
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "modelo.l0tf").write_bytes(sec32)
    (destino / "modelo_f16.l0tf").write_bytes(sec16)
    out = {"etiquetas": [str(c) for c in clf.classes_], "ngramas": len(vec.vocabulary_),
           "frases": [{"texto": t, "probs": [float(x) for x in row]} for t, row in zip(test, p)]}
    (destino / "frases.json").write_text(json.dumps(out, ensure_ascii=False, indent=0))
    return out


if __name__ == "__main__":
    repo = encontrar_repo()
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else repo / "server/decide/testdata/l0tf"
    o = generar(d, repo)
    print(d, len(o["frases"]), "frases,", o["ngramas"], "n-gramas")
