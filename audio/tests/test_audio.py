import io
import unittest
import wave

import numpy as np

from chispa_audio import (CAPA_ESCALAR, Cabeza, CodificadorFalso, ErrAudio, ErrPregunta, Flujo, LogMel,
                          LogMelFlujo, Opcion, Pregunta, TorresFalsas, escribir_wav, leer_wav, FS)


def seno(f, s=1.0, a=0.3):
    return (a * np.sin(2 * np.pi * f * np.arange(int(FS * s)) / FS)).astype(np.float32)


def banda_pico(x):
    return int(np.argmax(LogMel().calcular(x).mean(axis=0)))


class TestWav(unittest.TestCase):
    def test_ida_y_vuelta(self):
        x = seno(440, 0.5)
        y = leer_wav(escribir_wav(x))
        self.assertEqual(len(y), len(x))
        self.assertLess(float(np.abs(x - y).max()), 1 / 16384)

    def test_frecuencia_incorrecta(self):
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000), w.writeframes(b"\0\0" * 80)
        with self.assertRaisesRegex(ErrAudio, "16000 Hz"):
            leer_wav(b.getvalue())

    def test_estereo_a_mono(self):
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(2), w.setsampwidth(2), w.setframerate(FS)
            w.writeframes(np.array([1000, 3000] * 100, "<i2").tobytes())
        y = leer_wav(b.getvalue())
        self.assertEqual(len(y), 100)
        self.assertAlmostEqual(float(y[0]), 2000 / 32768, places=6)

    def test_basura_y_tope(self):
        with self.assertRaises(ErrAudio):
            leer_wav(b"esto no es un wav")
        with self.assertRaisesRegex(ErrAudio, "tope"):
            leer_wav(escribir_wav(seno(440, 2)), max_s=1)

    def test_recorta_a_rango(self):
        y = leer_wav(escribir_wav(np.array([2.0, -2.0])))
        self.assertTrue(np.all(np.abs(y) <= 1.0))


class TestLogMel(unittest.TestCase):
    def test_forma(self):
        self.assertEqual(LogMel().calcular(seno(440, 1.0)).shape, (98, 64))  # 1 + (16000-400)//160
        self.assertEqual(LogMel().calcular(np.zeros(399)).shape, (0, 64))

    def test_pico_sube_con_la_frecuencia(self):
        self.assertLess(banda_pico(seno(300)), banda_pico(seno(1000)))
        self.assertLess(banda_pico(seno(1000)), banda_pico(seno(4000)))

    def test_silencio_es_constante_y_menor(self):
        m = LogMel().calcular(np.zeros(FS))
        self.assertTrue(np.all(m == m[0, 0]))
        self.assertLess(m.max(), LogMel().calcular(seno(440)).max())
        self.assertTrue(np.isfinite(m).all())

    def test_flujo_igual_que_lote(self):
        x = np.random.default_rng(1).standard_normal(FS).astype(np.float32) * 0.1
        lote = LogMel().calcular(x)
        f, partes, i = LogMelFlujo(), [], 0
        for n in (1, 399, 160, 1000, 7, 4000, 3033, 100000):
            partes.append(f.empujar(x[i : i + n]))
            i += n
        np.testing.assert_allclose(np.concatenate(partes), lote, atol=1e-5)


class TestCodificador(unittest.TestCase):
    def setUp(self):
        self.cod, self.mel = CodificadorFalso(), LogMel()

    def test_dim_norma_y_determinismo(self):
        m = self.mel.calcular(seno(440))
        a, b = self.cod.abrir().empujar(m), CodificadorFalso().abrir().empujar(m)
        self.assertEqual(a.shape, (32,))
        self.assertAlmostEqual(float(np.linalg.norm(a)), 1.0, places=5)
        np.testing.assert_array_equal(a, b)

    def test_causal(self):
        m = self.mel.calcular(seno(440, 2.0))
        s1, s2 = self.cod.abrir(), self.cod.abrir()
        a = s1.empujar(m[:50])
        s2.empujar(m[:50])
        s2.empujar(m[50:])  # lo que llegue después no cambia lo ya devuelto
        np.testing.assert_array_equal(a, self.cod.abrir().empujar(m[:50]))

    def test_trozos_dan_lo_mismo_que_de_golpe(self):
        m = self.mel.calcular(seno(700, 1.0))
        s = self.cod.abrir()
        for i in range(0, len(m), 13):
            v = s.empujar(m[i : i + 13])
        np.testing.assert_allclose(v, self.cod.abrir().empujar(m), atol=1e-6)

    def test_silencio_no_rompe(self):
        v = self.cod.abrir().empujar(self.mel.calcular(np.zeros(FS)))
        self.assertTrue(np.isfinite(v).all())

    def test_distingue_tonos(self):
        a = self.cod.abrir().empujar(self.mel.calcular(seno(300)))
        b = self.cod.abrir().empujar(self.mel.calcular(seno(3000)))
        self.assertLess(float(a @ b), 0.99)


def qs():
    return [
        Pregunta("e", "¿Qué emoción?", "choice", [Opcion("enojo", "voz alterada"), Opcion("calma"), Opcion("duda")], nonce="n1"),
        Pregunta("u", "¿Está molesto?", "noul"),
        Pregunta("g", "¿Qué tan urgente?", "score", [Opcion(str(i)) for i in range(1, 6)]),
    ]


CLAVES = {"id", "kind", "answer", "probs", "layer", "escalate", "ms", "nonce"}


class TestCabeza(unittest.TestCase):
    def setUp(self):
        self.v = CodificadorFalso().abrir().empujar(LogMel().calcular(seno(440)))
        self.cab = Cabeza(TorresFalsas(), tau=0.0)

    def test_forma_como_decide(self):
        r = self.cab.decidir_lote(self.v, qs())
        self.assertEqual([x.id for x in r], ["e", "u", "g"])
        self.assertEqual(set(r[0].a_dict()), CLAVES)
        self.assertEqual(set(r[1].a_dict()), CLAVES - {"nonce"})
        for x in r:
            self.assertAlmostEqual(sum(x.probs.values()), 1.0, places=9)
            self.assertIn(x.answer, x.probs)
            self.assertEqual(x.answer, max(x.probs, key=x.probs.get))
            self.assertFalse(x.escalate)
            self.assertEqual(x.layer, "A1")
        self.assertEqual(set(r[1].probs), {"false", "true"})
        self.assertEqual(set(r[2].probs), {"1", "2", "3", "4", "5"})

    def test_escala_con_tau_alto(self):
        r = Cabeza(TorresFalsas(), tau=1.01).decidir(self.v, qs()[0])
        self.assertTrue(r.escalate)
        self.assertEqual(r.layer, CAPA_ESCALAR)
        self.assertIn(r.answer, r.probs)  # la mejor pista, como el servidor

    def test_sin_opinion(self):
        r = Cabeza.sin_opinion(qs()[0])
        self.assertEqual((r.answer, r.probs, r.escalate, r.layer), ("", {}, True, "escalar"))

    def test_validacion_con_ruta(self):
        casos = [
            (Pregunta("a", "q", "raro", []), r"questions\[1\]\.kind"),
            (Pregunta("a", "q", "choice", [Opcion("x")]), "al menos 2"),
            (Pregunta("a", "q", "choice", [Opcion("x"), Opcion("x")]), "repetidos"),
            (Pregunta("a", "q", "noul", [Opcion("si"), Opcion("no")]), "false"),
            (Pregunta("a", "q", "choice", [Opcion("x"), Opcion("")]), r"options\[1\]\.id"),
            (Pregunta("a", "q" * 5000, "noul"), "question"),
            (Pregunta("a" * 300, "q", "noul"), "id"),
            (Pregunta("a", "q", "choice", [Opcion(str(i)) for i in range(300)]), "máximo"),
            (Pregunta("", "q", "noul"), "id"),
        ]
        for p, msg in casos:
            with self.subTest(msg), self.assertRaisesRegex(ErrPregunta, msg):
                self.cab.decidir_lote(self.v, [qs()[1], p])

    def test_score_con_ids_libres(self):
        # /v1/decide acepta cualquier id único en score: audio no debe exigir "1"…"K"
        for ids in (["bajo", "medio", "alto"], ["1", "3"]):
            Pregunta("a", "q", "score", [Opcion(i) for i in ids]).validar()

    def test_ids_repetidos_en_lote(self):
        with self.assertRaises(ErrPregunta):
            self.cab.decidir_lote(self.v, [qs()[1], qs()[1]])

    def test_temperatura_afila(self):
        p = lambda T: max(Cabeza(TorresFalsas(), temperatura=T).decidir(self.v, qs()[0]).probs.values())
        self.assertGreater(p(0.02), p(0.5))


class TestFlujo(unittest.TestCase):
    def flujo(self, **kw):
        return Flujo(CodificadorFalso(), Cabeza(TorresFalsas(), tau=0.0), qs()[:2], **kw)

    def test_una_lectura_por_trozo(self):
        f = self.flujo()
        ls = f.empujar(seno(440, 1.0))  # 98 fotogramas → 3 trozos de 32
        self.assertEqual(len(ls), 3)
        self.assertEqual(len(ls[0].resultados), 2)
        self.assertAlmostEqual(ls[1].t_ms - ls[0].t_ms, 320.0)

    def test_trozos_de_audio_arbitrarios_dan_las_mismas_lecturas(self):
        x, a, b = seno(440, 2.0), self.flujo(), self.flujo()
        a.empujar(x)
        for i in range(0, len(x), 777):
            b.empujar(x[i : i + 777])
        self.assertEqual(len(a.lecturas), len(b.lecturas))
        for p, q in zip(a.lecturas, b.lecturas):
            self.assertEqual(p.resultados[0].probs.keys(), q.resultados[0].probs.keys())
            for k, v in p.resultados[0].probs.items():
                self.assertAlmostEqual(v, q.resultados[0].probs[k], places=5)

    def test_silencio_escala_sin_opinar(self):
        f = self.flujo()
        f.empujar(np.zeros(FS))
        self.assertTrue(f.lecturas)
        for l in f.lecturas:
            for r in l.resultados:
                self.assertTrue(r.escalate and r.answer == "" and r.probs == {})
        self.assertIsNone(f.decision(0))

    def test_acuerdo_exige_k_lecturas_estables(self):
        f = self.flujo(acuerdo=3)
        f.empujar(seno(440, 0.7))  # 2 trozos: aún no hay 3 lecturas
        self.assertIsNone(f.decision(0))
        f.empujar(seno(440, 3.0))
        self.assertIn(f.decision(0), {"enojo", "calma", "duda"})

    def test_tono_estable_da_decision_y_silencio_posterior_la_quita(self):
        f = self.flujo(acuerdo=3)
        f.empujar(seno(440, 3.0))
        self.assertIsNotNone(f.decision(0))
        f.empujar(np.zeros(2 * FS))
        self.assertIsNone(f.decision(0))


if __name__ == "__main__":
    unittest.main()
