package com.chispa.sdk

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class L2Test {
    @Test
    fun sinTorresNoTokenizaNiLlamaAOnnx() {
        val m = MotorFalso(torres = false)
        val s = SesionFalsa()
        var tokenizo = false
        val capa = CapaL2(m, s, { tokenizo = true; longArrayOf(1) })
        assertTrue(!capa.decidir("hola", PREGUNTA).opina)
        assertTrue(!tokenizo)
        assertEquals(0, s.llamadas)
        assertTrue(m.llamadas.isEmpty())
    }

    @Test
    fun pasaLosIdsYLasRanurasEnFloat32LittleEndian() {
        val m = MotorFalso(l2 = { json("compra", 0.9, "compra" to 0.9) })
        val s = SesionFalsa(Ranuras(floatArrayOf(1f, -2f, 0.5f, 4f), 2))
        val r = CapaL2(m, s, { longArrayOf(0, 7, 2) }).decidir("hola", PREGUNTA)
        assertEquals("compra", r.respuesta)
        assertArrayEquals(longArrayOf(0, 7, 2), s.ultimosIds)
        assertEquals(2, m.ultimoK)
        val esperado = ByteBuffer.allocate(16).order(ByteOrder.LITTLE_ENDIAN)
        for (x in floatArrayOf(1f, -2f, 0.5f, 4f)) esperado.putFloat(x)
        assertArrayEquals(esperado.array(), m.ultimasRanuras)
    }

    @Test
    fun sinTokensNoOpina() {
        val m = MotorFalso()
        val s = SesionFalsa()
        assertTrue(!CapaL2(m, s, { LongArray(0) }).decidir("", PREGUNTA).opina)
        assertEquals(0, s.llamadas)
    }

    @Test
    fun ranurasRechazaFormasImposibles() {
        val ex = try { Ranuras(floatArrayOf(1f, 2f, 3f), 2); null } catch (e: IllegalArgumentException) { e }
        assertTrue(ex != null)
    }

    @Test
    fun montarSoloCreaLaSesionConTokenizadorYConL2() {
        val s = SesionFalsa()
        var rutas = 0
        val sinTok = Chispa.montar(MotorFalso(), null, { rutas++; "x.onnx" }, { s })
        assertEquals(0, rutas)
        assertEquals(listOf("L0", "L1"), sinTok.capas.filter { it != "L2" })
        assertTrue("L2" !in sinTok.capas)

        val m = MotorFalso(l2 = { json("compra", 0.95, "compra" to 0.95) })
        val conTok = Chispa.montar(m, { longArrayOf(1) }, { rutas++; "x.onnx" }, { s })
        assertEquals(1, rutas)
        assertEquals(listOf("L0", "L1", "L2"), conTok.capas)
        val r = conTok.decidir("hola", listOf(PREGUNTA, PREGUNTA))
        assertEquals(2, r.size)
        assertEquals("L2", r[0].capa)
        conTok.close()
        assertTrue(s.cerrada && m.cerrado)

        val sinL2 = MotorFalso(presentes = listOf("L1"))
        rutas = 0
        Chispa.montar(sinL2, { longArrayOf(1) }, { rutas++; "x" }, { s })
        assertEquals(0, rutas)
    }
}
