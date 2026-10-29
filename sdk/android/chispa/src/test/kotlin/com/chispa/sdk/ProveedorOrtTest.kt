package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/** La elección de proveedor de ORT y su respaldo a CPU, con «sesiones» falsas (ORT no corre en la JVM de test). */
class ProveedorOrtTest {
    @Test
    fun xnnpackPorDefecto() {
        assertEquals(ProveedorOrt.XNNPACK, PROVEEDOR_ORT_POR_DEFECTO)
    }

    @Test
    fun laOpcionLlegaALaSesion() {
        for (p in ProveedorOrt.values()) {
            val pedidos = ArrayList<ProveedorOrt>()
            val (s, usado) = abrirConRespaldo(p, "L2", { _, _ -> fail("no debía avisar") }) { pedidos.add(it); "sesion-$it" }
            assertEquals(listOf(p), pedidos)
            assertEquals(p, usado)
            assertEquals("sesion-$p", s)
        }
    }

    @Test
    fun siFallaCaeACpuYAvisa() {
        for (p in listOf(ProveedorOrt.XNNPACK, ProveedorOrt.NNAPI)) {
            val pedidos = ArrayList<ProveedorOrt>()
            val avisos = ArrayList<String>()
            val (s, usado) = abrirConRespaldo(p, "torre", { m, _ -> avisos.add(m) }) {
                pedidos.add(it)
                if (it != ProveedorOrt.CPU) throw IllegalStateException("sin $it") else "cpu"
            }
            assertEquals(listOf(p, ProveedorOrt.CPU), pedidos)
            assertEquals(ProveedorOrt.CPU, usado)
            assertEquals("cpu", s)
            assertEquals(1, avisos.size)
            assertTrue(avisos[0].contains("torre") && avisos[0].contains(p.name))
        }
    }

    @Test
    fun cpuNoReintentaYSiFallaSube() {
        var llamadas = 0
        try {
            abrirConRespaldo<String>(ProveedorOrt.CPU, "L2", { _, _ -> fail("no debía avisar") }) {
                llamadas++
                throw IllegalStateException("roto")
            }
            fail("debía lanzar")
        } catch (e: IllegalStateException) {
            assertEquals(1, llamadas)
        }
    }

    @Test
    fun siCpuTambienFallaSubeElError() {
        var llamadas = 0
        try {
            abrirConRespaldo<String>(ProveedorOrt.NNAPI, "L2", { _, _ -> }) { llamadas++; throw IllegalStateException("roto") }
            fail("debía lanzar")
        } catch (e: IllegalStateException) {
            assertEquals(2, llamadas)
        }
    }
}
