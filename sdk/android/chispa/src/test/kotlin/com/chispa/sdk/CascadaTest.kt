package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CascadaTest {
    private fun cascada(m: MotorFalso, l2: CapaL2? = null) = Cascada.armar(m, l2)

    @Test
    fun l0SeguroNoLlamaAL1() {
        val m = MotorFalso(l0 = { json("compra", 0.95, "compra" to 0.95, "soporte" to 0.05) })
        val r = cascada(m).decidir("quiero una camiseta", PREGUNTA)
        assertEquals("compra", r.respuesta)
        assertEquals("L0", r.capa)
        assertFalse(r.escalar)
        assertEquals(listOf("L0"), m.llamadas)
        assertEquals(0.05, r.probs["soporte"]!!, 1e-12)
    }

    @Test
    fun l0DudosoPasaAL1() {
        val m = MotorFalso(
            l0 = { json("queja", 0.5, "queja" to 0.5) },
            l1 = { json("soporte", 0.9, "soporte" to 0.9) },
        )
        val r = cascada(m).decidir("hola", PREGUNTA)
        assertEquals("L1", r.capa)
        assertEquals("soporte", r.respuesta)
        assertEquals(listOf("L0", "L1"), m.llamadas)
    }

    @Test
    fun laConfianzaIgualAlTauAcepta() {
        val m = MotorFalso(l0 = { json("compra", 0.80, "compra" to 0.80) })
        assertEquals("L0", cascada(m).decidir("x", PREGUNTA).capa)
    }

    @Test
    fun unaCapaQueFallaOSinOpinionSeSalta() {
        val m = MotorFalso(
            l0 = { throw RuntimeException("boom") },
            l1 = { """{"ok":false,"error":"sin L1"}""" },
            l2 = { json("saludo", 0.99, "saludo" to 0.99) },
        )
        val r = cascada(m, CapaL2(m, SesionFalsa(), { longArrayOf(1, 2) })).decidir("hola", PREGUNTA)
        assertEquals("L2", r.capa)
        assertEquals("saludo", r.respuesta)
    }

    @Test
    fun siNingunaLlegaEscalaConLaMejorPista() {
        val m = MotorFalso(
            l0 = { json("queja", 0.30, "queja" to 0.30) },
            l1 = { json("compra", 0.60, "compra" to 0.60) },
            l2 = { json("soporte", 0.50, "soporte" to 0.50) },
        )
        val r = cascada(m, CapaL2(m, SesionFalsa(), { longArrayOf(1) })).decidir("x", PREGUNTA)
        assertTrue(r.escalar)
        assertEquals("compra", r.respuesta) // la de mayor confianza vista
        assertEquals(0.60, r.confianza, 1e-12)
        assertEquals("L2", r.capa) // la última de la cascada
    }

    @Test
    fun siNadieOpinaEscalaSinRespuesta() {
        val r = cascada(MotorFalso(presentes = listOf("L0", "L1"))).decidir("x", PREGUNTA)
        assertTrue(r.escalar)
        assertEquals("", r.respuesta)
        assertEquals(0.0, r.confianza, 0.0)
        assertEquals("L1", r.capa)
    }

    @Test
    fun tauDeCalibParaL1YL2PeroNoL0() {
        // 0,5 de L1 no llega a 0,80 por defecto, pero con CALIB τ = 0,4 sí
        val sin = MotorFalso(presentes = listOf("L0", "L1"), l1 = { json("compra", 0.5, "compra" to 0.5) })
        assertTrue(cascada(sin).decidir("x", PREGUNTA).escalar)
        val con = MotorFalso(presentes = listOf("L0", "L1"), calib = true, tau = 0.4, l1 = { json("compra", 0.5, "compra" to 0.5) })
        val r = cascada(con).decidir("x", PREGUNTA)
        assertFalse(r.escalar)
        assertEquals("L1", r.capa)
        // L0 sigue en 0,80 aunque CALIB diga 0,4
        val l0 = MotorFalso(presentes = listOf("L0", "L1"), calib = true, tau = 0.4, l0 = { json("queja", 0.5, "queja" to 0.5) })
        assertEquals(listOf("L0", "L1"), l0.also { cascada(it).decidir("x", PREGUNTA) }.llamadas)
    }

    @Test
    fun tauPorDefectoDeL2EsMasBajoQueElDeL1() {
        val m = MotorFalso(presentes = listOf("L1", "L2"), l1 = { json("a", 0.75, "a" to 0.75) }, l2 = { json("b", 0.75, "b" to 0.75) })
        val r = cascada(m, CapaL2(m, SesionFalsa(), { longArrayOf(1) })).decidir("x", PREGUNTA)
        assertEquals("L2", r.capa) // 0,75 < 0,80 de L1 pero ≥ 0,70 de L2
        assertEquals("b", r.respuesta)
    }

    @Test
    fun sinL2MontadoLaCascadaNoLaUsa() {
        val m = MotorFalso(l2 = { json("x", 1.0, "x" to 1.0) })
        val r = cascada(m, null).decidir("hola", PREGUNTA)
        assertEquals(listOf("L0", "L1"), m.llamadas)
        assertTrue(r.escalar)
    }

    @Test(expected = ErrorChispa::class)
    fun sinCapasUtilizablesFalla() {
        Cascada.armar(MotorFalso(presentes = listOf("L2")), null)
    }

    @Test
    fun midelElTiempoConElRelojInyectado() {
        var t = 0L
        val reloj = { t.also { t += 2_500_000L } }
        val m = MotorFalso(l0 = { json("compra", 0.9, "compra" to 0.9) })
        val r = Cascada(listOf(CapaConTau(CapaL0(m), 0.8)), reloj).decidir("x", PREGUNTA)
        assertEquals(2.5, r.ms, 1e-9)
    }
}
