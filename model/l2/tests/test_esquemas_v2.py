import json
import struct
import sys
import unittest
from pathlib import Path

from model.l2 import exportar as E
from model.l2.tests import gen_esquemas_v2 as G

FIX = Path(__file__).resolve().parent / "fixtures"
SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"


def hashes_esquemas(chispa):
    """Hashes de la sección ESQUEMAS (tipo 5) leída con el lector Python del SDK."""
    sys.path.insert(0, str(SDK))
    try:
        from chispa import formato
    finally:
        sys.path.remove(str(SDK))
    secs = formato.leer(chispa.read_bytes())
    b = secs[5]
    dim, n = struct.unpack_from("<II", b, 0)
    return [b[8 + 32 * i:8 + 32 * (i + 1)].hex() for i in range(n)], json.loads(secs[1])


class ClavesV2(unittest.TestCase):
    def test_opciones_clave(self):
        fs = G.filas()
        self.assertEqual(E.opciones_clave(fs[0], "alarma"), ["alarma", "Poner una alarma."])
        self.assertEqual(E.opciones_clave(fs[0], "musica"), ["musica", ""])
        self.assertEqual(E.opciones_clave(fs[2]), ["false", "Mensaje legítimo.", "true", "Mensaje no deseado."])
        self.assertEqual(E.opciones_clave(fs[0], "alarma", 1), ["alarma"])
        self.assertEqual(E.opciones_clave(fs[3], version=1), ["1", "2", "3"])

    def test_la_descripcion_cambia_la_clave(self):
        a, b = G.filas()[:2]
        self.assertNotEqual(G.hash_esquema(a["pregunta"], E.opciones_clave(a, "alarma")), G.hash_esquema(b["pregunta"], E.opciones_clave(b, "alarma")))
        self.assertEqual(G.hash_esquema(a["pregunta"], E.opciones_clave(a, "tiempo")), G.hash_esquema(b["pregunta"], E.opciones_clave(b, "tiempo")))

    def test_el_exportador_escribe_v2(self):
        self.assertEqual(E.meta_de(G.filas())["version"], 2)

    def test_fixture_v2_coincide_con_lo_esperado(self):
        esp = json.loads((FIX / "esquemas-v2.json").read_text(encoding="utf-8"))
        self.assertEqual(esp, G.esperado(G.filas()))
        hs, meta = hashes_esquemas(FIX / "esquemas-v2.chispa")
        self.assertEqual(meta["version"], 2)
        self.assertEqual(hs, sorted(c["hash"] for c in esp["claves"]))
        self.assertTrue(all(c["hash"] != c["hash_v1"] for c in esp["claves"]))
        self.assertLess((FIX / "esquemas-v2.chispa").stat().st_size, 8192)

    def test_ejemplo_de_clave_del_contrato(self):
        # el ejemplo de contrato-torre.md y de 04-formato-chispa.md
        h = G.hash_esquema("¿Qué quiere la persona?", ["alarma", "Poner una alarma."]).hex()
        self.assertEqual(h, "6143d44c05f4222dee1832556566605bb109f52893a315334728e742121880d4")
        self.assertIn(h, (Path(__file__).resolve().parents[1] / "contrato-torre.md").read_text(encoding="utf-8"))


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
