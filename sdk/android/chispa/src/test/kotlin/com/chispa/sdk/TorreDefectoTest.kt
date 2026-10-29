package com.chispa.sdk

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** El CodificadorTorre por defecto (ids del motor + ONNX de TORR) con motor y sesión falsos; ORT no corre en la JVM de test. */
class TorreDefectoTest {
    private val textos = listOf("passage: q · fraude · cargo", "passage: q · tarjeta · bloqueada")

    private fun ids(vararg v: Int): ByteArray {
        val b = ByteBuffer.allocate(4 * v.size).order(ByteOrder.LITTLE_ENDIAN)
        v.forEach { b.putInt(it) }
        return b.array()
    }

    private class SesionTorreFalsa : SesionTorre {
        val pedidos = ArrayList<LongArray>()
        var cerrada = false
        override fun embeber(ids: LongArray): FloatArray {
            pedidos.add(ids)
            return floatArrayOf(ids.size.toFloat(), 1f)
        }

        override fun close() {
            cerrada = true
        }
    }

    private fun motor(): MotorFalso {
        val m = MotorFalso(torres = false, l2 = { json("fraude", 0.9, "fraude" to 0.9) })
        m.textosTorre = textos
        m.onnxDeTorre = byteArrayOf(7, 7)
        m.idsE5 = ids(0, 5, 2)
        m.idsDePasaje = { t -> if ("fraude" in t) ids(0, 9, 8, 2) else ids(0, 9, 2) }
        return m
    }

    @Test
    fun codificaConLosIdsDelMotorYElOnnxDeTorreAbiertoUnaSolaVez() {
        val m = motor()
        val s = SesionTorreFalsa()
        var abiertas = 0
        var onnxVisto: ByteArray? = null
        val enc = CodificadorTorreMotor(m) { b -> abiertas++; onnxVisto = b; s }
        assertEquals(0, abiertas) // perezosa
        assertArrayEquals(floatArrayOf(4f, 1f), enc.torre(textos[0]), 0f)
        assertArrayEquals(floatArrayOf(3f, 1f), enc.torre(textos[1]), 0f)
        assertEquals(1, abiertas)
        assertArrayEquals(byteArrayOf(7, 7), onnxVisto)
        assertArrayEquals(longArrayOf(0, 9, 8, 2), s.pedidos[0])
        enc.close()
        assertTrue(s.cerrada)
    }

    @Test
    fun sinIdsOSinOnnxFallaConErrorChispa() {
        val m = motor()
        m.idsDePasaje = { null }
        assertTrue(runCatching { CodificadorTorreMotor(m) { SesionTorreFalsa() }.torre("x") }.exceptionOrNull() is ErrorChispa)
        val m2 = motor()
        m2.onnxDeTorre = null
        assertTrue(runCatching { CodificadorTorreMotor(m2) { SesionTorreFalsa() }.torre("x") }.exceptionOrNull() is ErrorChispa)
    }

    @Test
    fun montarSinCodificadorDeLaAppUsaTorrDelFicheroYLasTorresLlegaranAlMotor() {
        val m = motor()
        val s = SesionTorreFalsa()
        val ch = Chispa.montar(m, { longArrayOf(0, 2) }, { "x.onnx" }, { SesionFalsa() }, null, { s })
        val r = ch.decidir("hola", listOf(PREGUNTA_NUEVA))[0]
        assertEquals("L2", r.capa)
        assertEquals(2, m.nInstaladas)
        assertEquals(2, s.pedidos.size)
        val esperado = ByteBuffer.allocate(16).order(ByteOrder.LITTLE_ENDIAN)
        for (x in floatArrayOf(4f, 1f, 3f, 1f)) esperado.putFloat(x)
        assertArrayEquals(esperado.array(), m.torresInstaladas)
        ch.close()
        assertTrue(s.cerrada)
    }

    @Test
    fun sinTorrNiCodificadorUnEsquemaNuevoNoOpina() {
        val m = motor()
        m.onnxDeTorre = null
        val ch = Chispa.montar(m, { longArrayOf(0, 2) }, { "x.onnx" }, { SesionFalsa() })
        val r = ch.decidir("hola", listOf(PREGUNTA_NUEVA))[0]
        // Al escalar, la capa es la última de la cascada (L2) aunque no opine: lo que cuenta es que L2 no puntuó.
        assertFalse(r.capa == "L2" && !r.escalar)
        assertFalse("L2" in m.llamadas)
        assertFalse("TORRES" in m.llamadas)
        assertEquals(0, m.nInstaladas)
    }

    @Test
    fun elCodificadorDeLaAppManda() {
        val m = motor()
        val s = SesionTorreFalsa()
        Chispa.montar(m, { longArrayOf(0, 2) }, { "x.onnx" }, { SesionFalsa() }, { floatArrayOf(1f, 1f) }, { s })
            .decidir("hola", listOf(PREGUNTA_NUEVA))
        assertTrue(s.pedidos.isEmpty())
    }
}
