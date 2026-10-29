package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.assertThrows
import org.junit.Test

/** τ propio de L2 para esquemas con torres al vuelo (`tau_l2_esquema_nuevo`) y λ del soporte few-shot. */
class TauEsquemaNuevoTest {
    private class Codificador : CodificadorTorre {
        override fun torre(texto: String) = floatArrayOf(1f, 2f)
    }

    private fun motor(torres: Boolean, tauNuevo: Double) = MotorFalso(
        presentes = listOf("L2"), calib = true, tau = 0.9, torres = torres,
        l2 = { json("fraude", 0.7, "fraude" to 0.7) },
    ).also {
        it.textosTorre = listOf("passage: a", "passage: b")
        it.tauNuevo = tauNuevo
    }

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
        assertEquals(Pair(Chispa.LAMBDA_APAGADO, Chispa.LAMBDA_APAGADO), Chispa.soporteDe(null, null))
        assertEquals(4.0, Chispa.LAMBDA_SOPORTE_L1_POR_DEFECTO, 0.0)
        assertEquals(Pair(3.0, 5.0), Chispa.soporteDe(3.0, 5.0))
        assertEquals(Pair(3.0, Chispa.LAMBDA_APAGADO), Chispa.soporteDe(3.0, null))
        assertEquals(Pair(Chispa.LAMBDA_APAGADO, 0.0), Chispa.soporteDe(null, 0.0))
        // +∞ ya no apaga: es «solo descripción» y llega tal cual al motor.
        assertEquals(Pair(Double.POSITIVE_INFINITY, 0.0), Chispa.soporteDe(Double.POSITIVE_INFINITY, 0.0))
    }

    /** Por defecto (centinela) = `Abrir` del puente (null): λ de L1 lo decide el motor según el fichero; null = apagado y número = explícito, ambos por `AbrirConSoporte`. */
    @Test
    fun lambdaPorDefectoLoDecideElMotor() {
        assertTrue(Chispa.SOPORTE_POR_DEFECTO.isNaN())
        assertNull(Chispa.soporteDe(Chispa.SOPORTE_POR_DEFECTO, null))
        assertEquals(Pair(Chispa.LAMBDA_APAGADO, Chispa.LAMBDA_APAGADO), Chispa.soporteDe(null, null))
        assertEquals(Pair(4.0, Chispa.LAMBDA_APAGADO), Chispa.soporteDe(4.0, null))
        // Con L2 explícito el puente no ofrece «L1 por defecto»: L1 va con 4 explícito.
        assertEquals(Pair(4.0, 3.0), Chispa.soporteDe(Chispa.SOPORTE_POR_DEFECTO, 3.0))
        assertEquals(Pair(Chispa.LAMBDA_APAGADO, 3.0), Chispa.soporteDe(null, 3.0))
    }

    /** R4 #15: un λ negativo o NaN es error al abrir (antes se apagaba el soporte sin avisar); nulo sigue siendo apagado. */
    @Test
    fun lambdaNegativoONaNEsError() {
        assertThrows(ErrorChispa::class.java) { Chispa.soporteDe(-5.0, null) }
        assertThrows(ErrorChispa::class.java) { Chispa.soporteDe(null, -0.5) }
        assertThrows(ErrorChispa::class.java) { Chispa.soporteDe(2.0, Double.NaN) }
        assertThrows(ErrorChispa::class.java) { Chispa.soporteDe(Chispa.SOPORTE_POR_DEFECTO, Double.NaN) }
        assertThrows(ErrorChispa::class.java) { Chispa.soporteDe(Double.NEGATIVE_INFINITY, 0.0) }
        assertEquals(Pair(Chispa.LAMBDA_APAGADO, Chispa.LAMBDA_APAGADO), Chispa.soporteDe(null, null))
    }
}
