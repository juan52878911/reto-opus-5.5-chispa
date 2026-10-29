package com.chispa.sdk

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class ConjTest {
    private val l0 = mapOf("compra" to 0.5, "soporte" to 0.3, "saludo" to 0.2)
    private val previasL0 = mapOf("L0" to SalidaCapa("compra", 0.5, l0))

    private fun capa(m: MotorFalso, s: SesionFalsa = SesionFalsa(Ranuras(floatArrayOf(1f, -2f, 0.5f, 4f), 2))) =
        CapaL2(m, s, { longArrayOf(0, 7, 2) })

    @Test
    fun conConjYProbabilidadesDeL0DecideLaCabezaConjunta() {
        val m = MotorFalso(conj = true, cabeza = { json("soporte", 0.91, "soporte" to 0.91) })
        val r = capa(m).decidir("hola", PREGUNTA, previasL0)
        assertEquals("soporte", r.respuesta)
        assertEquals(0.91, r.confianza, 1e-12)
        assertEquals(listOf("CONJ"), m.llamadas) // no llega a puntuarL2
        val j = JSONObject(m.ultimoSimsJson!!)
        assertEquals(PREGUNTA.texto, j.getString("question"))
        assertEquals(2, j.getInt("k"))
        assertEquals(0.5, j.getJSONObject("l0").getDouble("compra"), 0.0)
        val ranuras = j.getJSONArray("ranuras")
        assertEquals(4, ranuras.length())
        assertEquals(floatArrayOf(1f, -2f, 0.5f, 4f).toList(), List(4) { ranuras.getDouble(it).toFloat() })
    }

    @Test
    fun sinConjUsaPuntuarL2() {
        val m = MotorFalso(conj = false, l2 = { json("compra", 0.8, "compra" to 0.8) })
        val r = capa(m).decidir("hola", PREGUNTA, previasL0)
        assertEquals("compra", r.respuesta)
        assertEquals(listOf("L2"), m.llamadas)
    }

    @Test
    fun sinProbabilidadesDeL0UsaPuntuarL2() {
        val m = MotorFalso(conj = true, l2 = { json("compra", 0.8, "compra" to 0.8) })
        capa(m).decidir("hola", PREGUNTA, mapOf("L0" to SalidaCapa.SIN_OPINION))
        capa(m).decidir("hola", PREGUNTA)
        assertEquals(listOf("L2", "L2"), m.llamadas)
    }

    @Test
    fun siLaCabezaNoOpinaCaeAL2() {
        val m = MotorFalso(conj = true, l2 = { json("compra", 0.8, "compra" to 0.8) })
        val r = capa(m).decidir("hola", PREGUNTA, previasL0)
        assertEquals("compra", r.respuesta)
        assertEquals(listOf("CONJ", "L2"), m.llamadas)
    }

    @Test
    fun laCascadaPasaLasProbabilidadesDeL0AL2c() {
        val m = MotorFalso(
            conj = true,
            l0 = { json("compra", 0.5, "compra" to 0.5, "soporte" to 0.3, "saludo" to 0.2) },
            cabeza = { json("compra", 0.95, "compra" to 0.95) },
        )
        val c = Cascada.armar(m, capa(m))
        val r = c.decidir("hola", PREGUNTA)
        assertEquals("L2", r.capa)
        assertFalse(r.escalar)
        assertEquals(0.95, r.confianza, 1e-12)
        assertEquals(listOf("L0", "L1", "CONJ"), m.llamadas)
        assertEquals(0.3, JSONObject(m.ultimoSimsJson!!).getJSONObject("l0").getDouble("soporte"), 0.0)
    }

    @Test
    fun unaCapaFallidaNoBorraLasPreviasDeLasDemas() {
        val m = MotorFalso(
            conj = true,
            l0 = { json("compra", 0.5, "compra" to 0.5) },
            l1 = { throw ErrorChispa("falla") },
            cabeza = { json("compra", 0.95, "compra" to 0.95) },
        )
        assertEquals("L2", Cascada.armar(m, capa(m)).decidir("hola", PREGUNTA).capa)
    }

    @Test
    fun tokenizadorDelMotorLeeInt32LittleEndian() {
        val b = ByteBuffer.allocate(12).order(ByteOrder.LITTLE_ENDIAN).putInt(0).putInt(250001).putInt(2).array()
        assertArrayEquals(longArrayOf(0, 250001, 2), TokenizadorMotor(MotorFalso(idsE5 = b)).ids("x"))
        assertTrue(MotorFalso(idsE5 = b).tieneTokenizadorE5())
        val ex = try { TokenizadorMotor(MotorFalso()).ids("x"); null } catch (e: ErrorChispa) { e }
        assertTrue(ex != null)
    }

    @Test
    fun montarConTokenizadorDelMotorMontaL2() {
        val b = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN).putInt(0).putInt(2).array()
        val s = SesionFalsa()
        val m = MotorFalso(idsE5 = b, l2 = { json("compra", 0.95, "compra" to 0.95) })
        val ch = Chispa.montar(m, TokenizadorMotor(m), { "x.onnx" }, { s })
        assertEquals(listOf("L0", "L1", "L2"), ch.capas)
        ch.decidir("hola", listOf(PREGUNTA))
        assertArrayEquals(longArrayOf(0, 2), s.ultimosIds)
    }
}
