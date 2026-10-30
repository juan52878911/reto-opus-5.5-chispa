"""Conjunto dorado común (server/decide/testdata/dorados, generado por el servidor Go amd64).

Python comprueba las partes que calcula o define: el formato (lectura de los .chispa, CRC y sha256), las claves de esquema
(hash_esquema2, clave_conj) y L0TF (n-gramas char_wb de sklearn + TF-IDF + regresión logística, en numpy), que es la
referencia con la que se entrena. Tolerancias: docs/07-rendimiento-y-limites.md, sección Determinismo."""
import json
import math
import struct
import unittest
from pathlib import Path

import numpy as np

from chispa import formato

DIR = Path(__file__).resolve().parents[3] / "server/decide/testdata/dorados"
TOL_L0TF = 1e-9  # numpy en float64 sobre coeficientes float32: el servidor Go hace lo mismo; medido ≤ 1e-15


def ngramas_char_wb(texto, min_n=2, max_n=5):
    """`TfidfVectorizer(analyzer='char_wb', lowercase=True)`: `_char_wb_ngrams` de sklearn, literal."""
    out = []
    for w in texto.lower().split():
        w = " " + w + " "
        n_w = len(w)
        for n in range(min_n, max_n + 1):
            off = 0
            out.append(w[off:off + n])
            while off + n < n_w:
                off += 1
                out.append(w[off:off + n])
            if off == 0:  # la palabra cabe en un solo n-grama
                break
    return out


class L0TF:
    def __init__(self, b):
        ver, v, c, dt = struct.unpack_from("<IIII", b, 0)
        assert ver == formato.L0TF_VERSION and dt in (1, 2)
        p, self.etiquetas = 16, []
        for _ in range(c):
            (n,) = struct.unpack_from("<H", b, p)
            self.etiquetas.append(b[p + 2:p + 2 + n].decode("utf-8"))
            p += 2 + n
        self.inter = np.frombuffer(b, "<f4", c, p).astype(np.float64)
        p += 4 * c
        self.idf = np.frombuffer(b, "<f4", v, p).astype(np.float64)
        p += 4 * v
        offs = np.frombuffer(b, "<u4", v + 1, p)
        p += 4 * (v + 1)
        blob = b[p:p + int(offs[-1])]
        p += int(offs[-1])
        self.indice = {blob[offs[i]:offs[i + 1]].decode("utf-8"): i for i in range(v)}
        self.coef = np.frombuffer(b, "<f2" if dt == 2 else "<f4", v * c, p).reshape(v, c).astype(np.float64)
        assert p + v * c * (2 if dt == 2 else 4) == len(b)

    def probs(self, texto):
        cuentas = {}
        for g in ngramas_char_wb(texto):
            i = self.indice.get(g)
            if i is not None:
                cuentas[i] = cuentas.get(i, 0) + 1
        z = self.inter.copy()
        if cuentas:
            idx = np.array(sorted(cuentas))
            x = np.array([(1 + math.log(cuentas[i])) for i in idx]) * self.idf[idx]
            z += (x / math.sqrt(float(x @ x))) @ self.coef[idx]
        e = np.exp(z - z.max())
        return e / e.sum()


def cargar(nombre):
    return json.loads((DIR / nombre).read_text(encoding="utf-8"))


class TestDorados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.peticiones = cargar("peticiones.json")
        cls.esperado = cargar("esperado.json")
        cls.claves = cargar("claves.json")

    def test_los_ficheros_se_leen_y_se_reescriben_igual(self):
        for f, tipos in (("l0l1.chispa", {formato.META, formato.CALIB, formato.L0, formato.L1}),
                         ("l0tf.chispa", {formato.META, formato.CALIB, formato.L0TF}),
                         ("l2.chispa", {formato.META, formato.CALIB, formato.L2, formato.ESQUEMAS})):
            datos = (DIR / f).read_bytes()
            secs = formato.leer(datos)  # comprueba CRC y sha256
            self.assertEqual(set(secs), tipos, f)
            self.assertEqual(formato.escribir(secs), datos, f"{f}: Python escribe otros bytes que Go")

    def test_claves_de_esquema_como_el_servidor(self):
        self.assertGreaterEqual(len(self.peticiones), 100)
        for p in self.peticiones:
            ops = p["options"]
            c = self.claves[p["id"]]
            h2 = formato.hash_esquema2(p["question"], p["kind"], [(o["id"], o.get("description", "")) for o in ops])
            self.assertEqual(h2.hex(), c["esquema2"], p["id"])
            self.assertEqual(formato.clave_conj(p["question"], [o["id"] for o in ops]).hex(), c["conj"], p["id"])
        # el orden de las opciones no cambia la clave
        p = next(p for p in self.peticiones if p["id"] == "l1-choice-a")
        q = next(q for q in self.peticiones if q["id"] == "l1-choice-inv-a")
        self.assertEqual(self.claves[p["id"]], self.claves[q["id"]])

    def test_l0tf_igual_al_servidor(self):
        m = L0TF(formato.leer((DIR / "l0tf.chispa").read_bytes())[formato.L0TF])
        n, peor = 0, 0.0
        for p in self.peticiones:
            if p["fichero"] != "l0tf.chispa" or p["capa"] != "L0":
                continue
            want = self.esperado["capas"][p["id"]]
            self.assertTrue(want["opina"], p["id"])
            pr = m.probs(p["estado"])
            self.assertEqual(m.etiquetas[int(np.argmax(pr))], want["answer"], p["id"])
            self.assertEqual(set(want["probs"]), set(m.etiquetas))
            for e, x in zip(m.etiquetas, pr):
                peor = max(peor, abs(x - want["probs"][e]))
            self.assertLessEqual(abs(pr.max() - want["conf"]), TOL_L0TF, p["id"])
            n += 1
        self.assertGreaterEqual(n, 20)
        self.assertLessEqual(peor, TOL_L0TF, f"|Δp| máxima {peor:.3g}")
        print(f"\nL0TF: {n} peticiones, |Δp| máxima frente al servidor {peor:.3g}")


if __name__ == "__main__":
    unittest.main()
