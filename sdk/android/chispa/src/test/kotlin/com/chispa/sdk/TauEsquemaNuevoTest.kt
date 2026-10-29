package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** τ propio de L2 para esquemas con torres al vuelo (`tau_l2_esquema_nuevo`) y λ del soporte few-shot. */
class TauEsquemaNuevoTest {
    private class Codificador : CodificadorTorre {
        override fun torre(texto: String) = floatArrayOf(1f, 2f)
    }

    private fun motor(torres: Boolean, tauNuevo: Double) = MotorFalso(
        presentes = listOf("L2"), calib = true, tau = 0.9, torres = torres, tauNuevo = tauNuevo,
        l2 = { json("fraude", 0.7, "fraude" to 0.7) },
    ).also { it.textosTorre = listOf("passage: a", "passage: b") }

    private fun decidir(m: MotorFalso) =
        Cascada.armar(m, CapaL2(m, SesionFalsa(), { longArrayOf(1, 2) }, Codificador())).decidir("x", PREGUNTA)

    @Test
    fun esquemaConocidoUsaElTauDeSiempre() {
        val r = decidir(motor(torres = true, tauNuevo = 0.5))
        assertTrue(r.escalar) // 0.7 < 0.9
    }

    @Test
    fun esquemaNuevoUsaElTauNuevo() {
        val r = decidir(motor(torres = false, tauNuevo = 0.5))
        assertEquals("L2", r.capa)
        assertFalse(r.escalar) // 0.7 ≥ 0.5
    }

    @Test
    fun siElTauNuevoEsMasAltoEsquemaNuevoEscala() {
        val r = decidir(motor(torres = false, tauNuevo = 0.95).also { it.tau = 0.6 })
        assertTrue(r.escalar)
    }

    @Test
    fun sinTauNuevoNadaCambia() {
        assertTrue(decidir(motor(torres = false, tauNuevo = -1.0)).escalar)
        assertFalse(decidir(motor(torres = false, tauNuevo = -1.0).also { it.tau = 0.6 }).escalar)
    }

    @Test
    fun lasTorresCacheadasDeUnEsquemaNuevoSiguenSiendoNuevas() {
        val m = motor(torres = false, tauNuevo = 0.5)
        val c = Cascada.armar(m, CapaL2(m, SesionFalsa(), { longArrayOf(1, 2) }, Codificador()))
        assertFalse(c.decidir("x", PREGUNTA).escalar)
        assertFalse(c.decidir("x", PREGUNTA).escalar) // segunda: torresL2 ya da true, pero se instalaron al vuelo
        assertEquals(1, m.llamadas.count { it == "TORRES" })
    }

    @Test
    fun laCapaMarcaEsquemaNuevoSoloConTorresAlVuelo() {
        val nuevo = motor(torres = false, tauNuevo = -1.0)
        assertTrue(CapaL2(nuevo, SesionFalsa(), { longArrayOf(1) }, Codificador()).decidir("x", PREGUNTA).esquemaNuevo)
        val conocido = motor(torres = true, tauNuevo = -1.0)
        assertFalse(CapaL2(conocido, SesionFalsa(), { longArrayOf(1) }, Codificador()).decidir("x", PREGUNTA).esquemaNuevo)
    }

    @Test
    fun lambdaDelSoporteLlegaAlMotor() {
        assertNull(Chispa.soporteDe(null, null))
        assertEquals(Pair(3.0, 5.0), Chispa.soporteDe(3.0, 5.0))
        assertEquals(Pair(3.0, Chispa.LAMBDA_APAGADO), Chispa.soporteDe(3.0, null))
        assertEquals(Pair(Chispa.LAMBDA_APAGADO, 0.0), Chispa.soporteDe(null, 0.0))
        // +∞ ya no apaga: es «solo descripción» y llega tal cual al motor.
        assertEquals(Pair(Double.POSITIVE_INFINITY, 0.0), Chispa.soporteDe(Double.POSITIVE_INFINITY, 0.0))
    }
}
