package com.chispa.sdk

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class TextoLargoTest {
    /** `[n][len][ids…]…` como lo da el motor. */
    private fun ventanas(vararg v: IntArray): ByteArray {
        val b = ByteBuffer.allocate(4 + v.sumOf { 4 + 4 * it.size }).order(ByteOrder.LITTLE_ENDIAN)
        b.putInt(v.size)
        for (w in v) {
            b.putInt(w.size)
            for (id in w) b.putInt(id)
        }
        return b.array()
    }

    @Test
    fun tokenizadorMotorLeeLasVentanas() {
        val m = MotorFalso()
        m.trozos = ventanas(intArrayOf(0, 7, 2), intArrayOf(0, 8, 9, 2))
        val v = TokenizadorMotor(m).trozos("texto largo")
        assertEquals(2, v.size)
        assertArrayEquals(longArrayOf(0, 7, 2), v[0])
        assertArrayEquals(longArrayOf(0, 8, 9, 2), v[1])
    }

    @Test
    fun sinTrozosDelMotorCaeAlTokenizarDeSiempre() {
        val m = MotorFalso(idsE5 = ByteBuffer.allocate(12).order(ByteOrder.LITTLE_ENDIAN).putInt(0).putInt(7).putInt(2).array())
        val v = TokenizadorMotor(m).trozos("hola")
        assertEquals(1, v.size)
        assertArrayEquals(longArrayOf(0, 7, 2), v[0])
    }

    @Test
    fun respuestaTruncadaDelMotorEsError() {
        val m = MotorFalso()
        m.trozos = ventanas(intArrayOf(0, 7, 2)).copyOf(9)
        val ex = try { TokenizadorMotor(m).trozos("x"); null } catch (e: ErrorChispa) { e }
        assertTrue(ex != null)
    }

    @Test
    fun conUnaVentanaEsLoDeSiempre() {
        val m = MotorFalso(l2 = { json("compra", 0.9, "compra" to 0.9) })
        m.trozos = ventanas(intArrayOf(0, 7, 2))
        val s = SesionFalsa(Ranuras(floatArrayOf(1f, -2f, 0.5f, 4f), 2))
        val r = CapaL2(m, s, TokenizadorMotor(m)).decidir("hola", PREGUNTA)
        assertEquals("compra", r.respuesta)
        assertEquals(listOf("L2"), m.llamadas) // puntuarL2, no puntuarL2Trozos
        assertEquals(2, m.ultimoK)
        assertEquals(1, s.llamadas)
    }

    @Test
    fun conVariasVentanasCorreOnnxEnCadaUnaYPuntuaLasConcatenadas() {
        val m = MotorFalso(l2 = { json("compra", 0.9, "compra" to 0.9) })
        m.trozos = ventanas(intArrayOf(0, 7, 2), intArrayOf(0, 8, 2), intArrayOf(0, 9, 2))
        val s = SesionFalsa(Ranuras(floatArrayOf(1f, 2f, 3f, 4f), 2))
        val r = CapaL2(m, s, TokenizadorMotor(m)).decidir("texto largo", PREGUNTA)
        assertEquals("compra", r.respuesta)
        assertEquals(3, s.llamadas)
        assertEquals(listOf("L2T"), m.llamadas)
        assertEquals("[2,2,2]", m.ultimosKs)
        assertEquals(3 * 4 * 4, m.ultimasRanuras!!.size)
    }

    @Test
    fun conCabezaConjuntaYL0LaCabezaDecideCadaVentana() {
        val m = MotorFalso(conj = true, cabeza = { json("compra", 0.9, "compra" to 0.9) })
        m.trozos = ventanas(intArrayOf(0, 7, 2), intArrayOf(0, 8, 2))
        val s = SesionFalsa(Ranuras(floatArrayOf(1f, 2f), 1))
        val l0 = SalidaCapa.desdeJson(json("compra", 0.5, "compra" to 0.5, "soporte" to 0.5))
        val r = CapaL2(m, s, TokenizadorMotor(m)).decidir("texto largo", PREGUNTA, mapOf("L0" to l0))
        assertEquals("compra", r.respuesta)
        assertEquals(listOf("CONJ"), m.llamadas)
        val o = org.json.JSONObject(m.ultimoSimsJson!!)
        assertEquals("[1,1]", o.getJSONArray("ks").toString())
        assertEquals(4, o.getJSONArray("ranuras").length())
    }

    @Test
    fun elTextoLargoPorDefectoEsCabeza() {
        assertEquals(TextoLargo.CABEZA, TextoLargo())
        val o = org.json.JSONObject(TextoLargo(estrategia = "trozos", agregacion = "max", solape = 16, maxTrozos = 4, ventanaL1 = 64).toJson())
        assertEquals("trozos", o.getString("estrategia"))
        assertEquals("max", o.getString("agregacion"))
        assertEquals(16, o.getInt("solape"))
        assertEquals(4, o.getInt("max_trozos"))
        assertEquals(64, o.getInt("ventana_l1"))
    }
}
