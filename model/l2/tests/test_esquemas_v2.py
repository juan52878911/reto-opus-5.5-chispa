import json
import os
import struct
import subprocess
import sys
import unittest
from pathlib import Path

from model.l2 import exportar as E
from model.l2.tests import gen_esquemas_v2 as G

FIX = Path(__file__).resolve().parent / "fixtures"
SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"


def leer_esquemas(chispa):
    """(versión, dim, hashes en hex) de la sección ESQUEMAS (tipo 5) leída con el lector Python del SDK, y META."""
    sys.path.insert(0, str(SDK))
    try:
        from chispa import formato
    finally:
        sys.path.remove(str(SDK))
    secs = formato.leer(chispa.read_bytes())
    b = secs[5]
    w0, n = struct.unpack_from("<II", b, 0)
    return w0 >> 16, w0 & 0xffff, [b[8 + 16 * i:8 + 16 * (i + 1)].hex() for i in range(n)], json.loads(secs[1])


class ClavesV2(unittest.TestCase):
    def test_vectores_del_formato(self):
        vs = json.loads((Path(__file__).resolve().parents[3] / "format" / "chispa3" / "vectores-clave-v2.json").read_text(encoding="utf-8"))["vectores"]
        self.assertEqual(len(vs), 5)
        for v in vs:
            ops = [(o["id"], o["description"]) for o in v["opciones"]]
            self.assertEqual(E.hash_clave(v["pregunta"], v["kind"], ops), v["hash"], v["nombre"])
            self.assertEqual(G.hash_esquema2(v["pregunta"], v["kind"], ops).hex(), v["hash"], v["nombre"])

    def test_clave_torre(self):
        fs = G.filas()
        self.assertEqual(E.clave_torre(fs[0], "alarma")[1:], ("choice", (("alarma", "Poner una alarma."),)))
        self.assertEqual(E.clave_torre(fs[0], "musica")[2], (("musica", ""),))
        self.assertEqual(E.clave_torre(fs[2])[1:], ("noul", (("false", "Mensaje legítimo."), ("true", "Mensaje no deseado."))))
        self.assertEqual(E.clave_torre(fs[3])[1], "score")

    def test_la_descripcion_cambia_la_clave(self):
        a, b = G.filas()[:2]
        h = lambda r, o: E.hash_clave(*E.clave_torre(r, o))
        self.assertNotEqual(h(a, "alarma"), h(b, "alarma"))
        self.assertEqual(h(a, "tiempo"), h(b, "tiempo"))

    def test_meta_no_lleva_version_de_clave(self):
        self.assertEqual(E.meta_de(G.filas())["version"], 1)

    def test_fixture_v2_coincide_con_lo_esperado(self):
        esp = json.loads((FIX / "esquemas-v2.json").read_text(encoding="utf-8"))
        self.assertEqual(esp, G.esperado(G.filas()))
        ver, dim, hs, meta = leer_esquemas(FIX / "esquemas-v2.chispa")
        self.assertEqual((ver, dim), (2, 256))
        self.assertEqual(hs, sorted(c["hash"] for c in esp["claves"]))
        self.assertTrue(all(c["hash"] == E.hash_clave(c["pregunta"], c["kind"], [(o["id"], o["description"]) for o in c["opciones"]])
                            for c in esp["claves"] + esp["conj"]))
        self.assertLess((FIX / "esquemas-v2.chispa").stat().st_size, 8192)

    def test_chispa3_abre_el_fixture(self):
        # el lector de Go (chispa3.Abrir + Esquemas) busca cada clave con BuscarEsquema
        env = {**os.environ, "CHISPA_FICHERO": str(FIX / "esquemas-v2.chispa"), "CHISPA_FIXTURE_JSON": str(FIX / "esquemas-v2.json"),
               "GOFLAGS": "-mod=mod", "GOPROXY": "off"}
        p = subprocess.run([E.go_bin(), "test", "-count=1", "-run", "TestFixtureEsquemasV2", "-v", "."], cwd=E.GO_DIR, env=env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("SKIP", p.stdout)


class PerfilesCli(unittest.TestCase):
    def test_perfil_servidor_y_movil(self):
        self.assertEqual(E.PERFILES["servidor"], dict(cuant="ninguna", cuant_torre="ninguna", sin_poda=True))
        self.assertEqual(E.PERFILES["movil"]["cuant_torre"], "dinamico")
        self.assertFalse(E.PERFILES["movil"]["sin_poda"])

    def test_perfil_choca_con_flags(self):
        with self.assertRaises(SystemExit):
            E.main(["--perfil", "servidor", "--cuant", "todo", "--torre-onnx", "x", "--ckpt-aleatorio"])
        with self.assertRaises(SystemExit):
            E.main(["--perfil", "movil", "--sin-poda", "--torre-onnx", "x", "--ckpt-aleatorio"])

    def test_textos_de_y_ampliar(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            j, x = Path(t) / "a.jsonl", Path(t) / "b.txt"
            j.write_text(json.dumps({"texto": "hola", "pregunta": "¿q?", "opciones": ["o"], "descripciones": {"o": "d"}}) + "\n\n")
            x.write_text("uno\n\ndos\n")
            self.assertEqual(E.textos_de(j), ["hola", "¿q?", "o", "d"])
            self.assertEqual(E.textos_de(x), ["uno", "dos"])

            class Tok:
                def __call__(self, textos, truncation, max_length):
                    return {"input_ids": [[0] + [10 + len(w) for w in t.split()] + [2] for t in textos]}

            class Enc:
                tok = Tok()

            v, inf = E.ampliar_vocab(Enc(), {"ids_originales": [0, 1, 2, 3], "conservados": 4}, [x])
            self.assertEqual(v["ids_originales"], [0, 1, 2, 3, 13, 16, 18])  # con los prefijos «query:» y «passage:»
            self.assertEqual(inf["ids_despues"], len(v["ids_originales"]))


if __name__ == "__main__":
    unittest.main()
