package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** R12-H7: con CONJ, el respaldo de L2c (L2 base) se corta con `tau_escalate_l2` y no con `tau_l2c`, el τ de la cabeza. */
class RespaldoL2cTest {
    private fun motor(l0Probs: Boolean) = MotorFalso(
        presentes = if (l0Probs) listOf("L0", "L2") else listOf("L2"), calib = true, tau = 0.5, conj = true,
        l0 = { json("compra", 0.5, "compra" to 0.5, "soporte" to 0.5) },
        l2 = { json("compra", 0.8, "compra" to 0.8) },
        cabeza = { json("compra", 0.8, "compra" to 0.8) },
    ).also {
        it.tauL2 = 0.95 // tau_escalate_l2
        it.tauConj = 0.3 // tau_l2c
    }

    private fun decidir(m: MotorFalso) =
        Cascada.armar(m, CapaL2(m, SesionFalsa(), { longArrayOf(0, 7, 2) })).decidir("hola", PREGUNTA)

    @Test
    fun laCabezaConjuntaSigueUsandoTauL2c() {
        val r = decidir(motor(l0Probs = true))
        assertEquals("L2", r.capa)
        assertFalse(r.escalar) // 0.8 ≥ 0.3
    }

    @Test
    fun elRespaldoDeL2BaseUsaTauEscalateL2() {
        val m = motor(l0Probs = false) // sin probabilidades de L0: L2c cae a L2 base
        val r = decidir(m)
        assertTrue(r.escalar) // 0.8 < 0.95
        assertEquals(listOf("L2"), m.llamadas)
    }

    @Test
    fun laCapaMarcaElRespaldoSoloConConj() {
        val m = motor(l0Probs = false)
        assertTrue(CapaL2(m, SesionFalsa(), { longArrayOf(0, 7, 2) }).decidir("hola", PREGUNTA).respaldo)
        m.conj = false
        assertFalse(CapaL2(m, SesionFalsa(), { longArrayOf(0, 7, 2) }).decidir("hola", PREGUNTA).respaldo)
    }
}
