import struct
import unittest
from pathlib import Path

import numpy as np

from chispa import formato

TESTDATA = Path(__file__).resolve().parents[3] / "format/chispa3/testdata/soporte.chispa"
TESTDATA_V2 = TESTDATA.with_name("soporte-v2.chispa")
TESTDATA_V3 = TESTDATA.with_name("soporte-v3.chispa")
DIM = 4


def entradas():
    esc, q = formato.cuantizar_media([[0.5, -0.25, 0.0, 0.125], [0, 0, 0, 0]])
    return [{"hash": formato.clave_conj("¿p?", ["b", "a"]), "ids": ["a", "b"], "k": [3, 0], "escala": esc, "media": q}]


def entradas_v2():
    """Caso a mano de n = 3 (ver TestSOPL1V2Go en format/chispa3): K = 2 ranuras con normas √5/3 y 1; la clase «b» sin ejemplos."""
    e = entradas()[0]
    e["normas"] = np.array([[np.sqrt(5) / 3, 1.0], [0.0, 0.0]], dtype=np.float32)
    return [e]


def entradas_v3():
    """El v2 con n_l2: «a» tiene k = 3 pero el soporte de CONJ solo 2 ejemplos; «b» sin dato (0)."""
    e = entradas_v2()[0]
    e["n_l2"] = np.array([2, 0], dtype=np.uint32)
    return [e]


def fichero(v2=False, v3=False) -> bytes:
    return formato.escribir({formato.META: formato.meta(["q"]), formato.CALIB: formato.calib({}, 0.5),
                             formato.SOPL1: formato.sopl1(DIM, entradas_v3() if v3 else entradas_v2() if v2 else entradas())})


class TestSOPL1(unittest.TestCase):
    def test_cuantizar(self):
        esc, q = formato.cuantizar_media([[0.5, -0.25, 0.0, 0.125], [0, 0, 0, 0]])
        self.assertEqual(q.tolist(), [[127, -64, 0, 32], [0, 0, 0, 0]])  # -63,5 y 31,75 redondean a par/al más cercano
        self.assertEqual(esc.tolist(), [np.float32(0.5) / np.float32(127), 0.0])

    def test_layout(self):
        b = formato.sopl1(DIM, entradas())
        self.assertEqual(b[:12].hex(), "01000000" "04000000" "01000000")
        self.assertEqual(b[44:48].hex(), "02000000")  # C = 2 tras el hash

    def test_ida_y_vuelta(self):
        got = formato.leer_sopl1(formato.leer(fichero())[formato.SOPL1])
        e = got["entradas"][0]
        self.assertEqual((got["dim"], e["ids"], e["k"].tolist()), (DIM, ["a", "b"], [3, 0]))
        self.assertEqual(e["media"].tolist(), [[127, -64, 0, 32], [0, 0, 0, 0]])

    def test_rechaza(self):
        e = entradas()[0]
        for mal in ({"ids": ["b", "a"]}, {"k": [1]}, {"hash": b"x"}, {"media": np.zeros((2, 3), np.int8)}):
            with self.assertRaises(ValueError):
                formato.sopl1(DIM, [{**e, **mal}])
        with self.assertRaises(ValueError):
            formato.leer_sopl1(b"\0" * 8)

    def test_el_fichero_guardado_es_el_que_se_genera(self):
        self.assertTrue(TESTDATA.is_file(), "falta " + str(TESTDATA))
        self.assertEqual(TESTDATA.read_bytes(), fichero())

    def test_v2_layout_e_ida_y_vuelta(self):
        b = formato.sopl1(DIM, entradas_v2())
        self.assertEqual(b[:4].hex(), "02000000")
        v1 = formato.sopl1(DIM, entradas())
        self.assertEqual(b[4:len(v1)], v1[4:])           # el cuerpo de la entrada es el de v1
        self.assertEqual(b[len(v1):len(v1) + 4].hex(), "02000000")  # K = 2
        self.assertEqual(len(b), len(v1) + 4 + 4 * 2 * 2)
        e = formato.leer_sopl1(b)["entradas"][0]
        self.assertEqual(e["normas"].shape, (2, 2))
        self.assertAlmostEqual(float(e["normas"][0, 0]), 5 ** 0.5 / 3, places=6)

    def test_v1_se_lee_sin_normas_y_sin_normas_son_los_bytes_de_siempre(self):
        b = formato.sopl1(DIM, entradas())
        self.assertEqual(b[:4].hex(), "01000000")
        self.assertIsNone(formato.leer_sopl1(b)["entradas"][0]["normas"])
        sin = {**entradas()[0], "normas": None}
        self.assertEqual(formato.sopl1(DIM, [sin]), b)

    def test_v2_rechaza_normas_malas(self):
        for mal in (np.ones((3, 2)), np.full((2, 2), 2.0), np.full((2, 2), np.nan), np.full((2, 2), -0.5)):
            with self.assertRaises(ValueError):
                formato.sopl1(DIM, [{**entradas()[0], "normas": mal}])

    def test_el_fichero_v2_guardado_es_el_que_se_genera(self):
        self.assertTrue(TESTDATA_V2.is_file(), "falta " + str(TESTDATA_V2))
        self.assertEqual(TESTDATA_V2.read_bytes(), fichero(True))

    def test_v3_layout_e_ida_y_vuelta(self):
        b = formato.sopl1(DIM, entradas_v3())
        v2 = formato.sopl1(DIM, entradas_v2())
        self.assertEqual(b[:4].hex(), "03000000")
        self.assertEqual(b[4:len(v2)], v2[4:])  # el cuerpo es el de v2
        self.assertEqual(b[len(v2):len(v2) + 4].hex(), "02000000")  # M = C = 2
        self.assertEqual(b[len(v2) + 4:].hex(), "0200000000000000")
        e = formato.leer_sopl1(b)["entradas"][0]
        self.assertEqual(e["n_l2"].tolist(), [2, 0])
        self.assertEqual(e["normas"].shape, (2, 2))

    def test_sin_n_l2_los_bytes_son_los_de_antes(self):
        for en, ver in ((entradas(), 1), (entradas_v2(), 2)):
            b = formato.sopl1(DIM, [{**en[0], "n_l2": None}])
            self.assertEqual(b, formato.sopl1(DIM, en))
            self.assertEqual(b[0], ver)
            self.assertIsNone(formato.leer_sopl1(b)["entradas"][0]["n_l2"])

    def test_v3_sin_normas_y_entradas_mezcladas(self):
        e = {**entradas()[0], "n_l2": [3, 0]}
        otra = {**entradas()[0], "hash": b"\xff" * 32}  # sin n_l2 ni normas: M = 0, K = 0
        r = formato.leer_sopl1(formato.sopl1(DIM, [e, otra]))["entradas"]
        self.assertEqual(sorted(x["n_l2"] is None for x in r), [False, True])
        self.assertTrue(all(x["normas"] is None for x in r))

    def test_v3_rechaza_n_l2_malo(self):
        for mal in ([1], [1, 2, 3], [-1, 0], [1.5, 0]):
            with self.assertRaises(ValueError):
                formato.sopl1(DIM, [{**entradas()[0], "n_l2": mal}])
        b = formato.sopl1(DIM, entradas_v3())
        for malo in (b[:-1], b + b"\0"):
            with self.assertRaises(Exception):
                formato.leer_sopl1(malo)

    def test_el_fichero_v3_guardado_es_el_que_se_genera(self):
        self.assertTrue(TESTDATA_V3.is_file(), "falta " + str(TESTDATA_V3))
        self.assertEqual(TESTDATA_V3.read_bytes(), fichero(v3=True))

    def test_paridad_con_go_rechaza_lo_mismo(self):
        """Los mismos bytes corruptos que TestSOPL1ParidadConPythonRechazaLoMismo (Go): el lector y el escritor Python los rechazan."""
        raw = formato.sopl1(DIM, entradas_v3())
        formato.leer_sopl1(raw)
        casos = {"escala NaN": (62, "<I", 0x7fc00000), "escala negativa": (62, "<I", 0xbf800000), "escala +Inf": (62, "<I", 0x7f800000),
                 "norma NaN": (82, "<I", 0x7fc00000), "norma > 1.001": (82, "<I", 0x40000000), "ids no crecientes": (50, "<B", ord("c"))}
        for nombre, (off, fmt, val) in casos.items():
            m = bytearray(raw)
            struct.pack_into(fmt, m, off, val)
            with self.assertRaises(ValueError, msg=nombre):
                formato.leer_sopl1(bytes(m))
        dup = struct.pack("<III", 3, DIM, 2) + raw[12:] + raw[12:]
        with self.assertRaises(ValueError):
            formato.leer_sopl1(dup)

    def test_escritor_rechaza_lo_que_go_rechaza(self):
        e = entradas_v3()[0]
        for mal in (np.array([np.nan, 0], dtype=np.float32), np.array([-1.0, 0], dtype=np.float32), np.array([np.inf, 0], dtype=np.float32)):
            with self.assertRaises(ValueError):
                formato.sopl1(DIM, [{**e, "escala": mal}])
        with self.assertRaises(ValueError):
            formato.sopl1(DIM, [e, {**e}])  # hashes repetidos
        with self.assertRaises(ValueError):
            formato.sopl1(DIM, [{**e, "normas": np.array([[np.nan, 0], [0, 0]], dtype=np.float32)}])
        for grande in (2 ** 32, 2 ** 40):  # antes se truncaba a 0 («sin dato, usa k»)
            with self.assertRaises(ValueError):
                formato.sopl1(DIM, [{**e, "n_l2": np.array([grande, 0], dtype=np.uint64)}])
            with self.assertRaises(ValueError):
                formato.sopl1(DIM, [{**e, "n_l2": [grande, 0]}])


if __name__ == "__main__":
    unittest.main()
