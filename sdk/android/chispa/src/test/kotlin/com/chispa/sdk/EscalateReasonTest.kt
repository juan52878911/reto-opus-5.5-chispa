package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** `escalate_reason` con los mismos valores que el servidor y la regla «score solo con ids 1..K». */
class EscalateReasonTest {
    private fun score(vararg ids: String) = Pregunta("Gravedad", ids.map { Opcion(it) }, tipo = "score")
    private fun cascada(m: MotorFalso) = Cascada.armar(m, CapaL2(m, SesionFalsa(), { longArrayOf(1) }))

    @Test
    fun losValoresSonLosDelServidor() {
        assertEquals("sin_opinion", MotivoEscalada.SIN_OPINION)
        assertEquals("baja_confianza", MotivoEscalada.BAJA_CONFIANZA)
        assertEquals("score_ids_no_validos", MotivoEscalada.SCORE_IDS_NO_VALIDOS)
    }

    @Test
    fun bajaConfianzaSiAlgunaOpinaPeroNoLlegaATau() {
        val m = MotorFalso(l1 = { json("compra", 0.6, "compra" to 0.6) })
        val r = cascada(m).decidir("x", PREGUNTA)
        assertTrue(r.escalar)
        assertEquals("baja_confianza", r.escalateReason)
    }

    @Test
    fun sinOpinionSiNingunaOpina() {
        val r = cascada(MotorFalso()).decidir("x", PREGUNTA)
        assertTrue(r.escalar)
        assertEquals("sin_opinion", r.escalateReason)
    }

    @Test
    fun scoreConIdsFueraDe1aKNoOpinaYLoDice() {
        for (ids in listOf(
            listOf("bajo", "medio", "alto"), listOf("0", "1", "2"), listOf("01", "2", "3"),
            listOf("+1", "2", "3"), listOf("1", "2", "4"), listOf("1", "1", "2"),
        )) {
            val r = cascada(MotorFalso()).decidir("x", score(*ids.toTypedArray()))
            assertTrue(ids.toString(), r.escalar)
            assertEquals(ids.toString(), "score_ids_no_validos", r.escalateReason)
        }
    }

    @Test
    fun scoreConIdsValidosEnCualquierOrdenNoEsScoreIdsNoValidos() {
        for (ids in listOf(listOf("1", "2", "3"), listOf("3", "1", "2"), listOf("2", "3", "1"))) {
            assertTrue(scoreIdsValidos(score(*ids.toTypedArray())))
            val r = cascada(MotorFalso()).decidir("x", score(*ids.toTypedArray()))
            assertEquals("sin_opinion", r.escalateReason)
        }
    }

    @Test
    fun scoreIdsValidosSoloMiraScore() {
        assertTrue(scoreIdsValidos(PREGUNTA)) // choice con ids cualesquiera
        assertFalse(scoreIdsValidos(score()))
        assertFalse(scoreIdsValidos(score("2")))
    }

    @Test
    fun siUnaCapaFallaNoHayMotivo() {
        val m = MotorFalso(l0 = { throw RuntimeException("boom") })
        val r = cascada(m).decidir("x", PREGUNTA)
        assertTrue(r.escalar)
        assertNull(r.escalateReason)
    }

    @Test
    fun siDecideUnaCapaNoHayMotivo() {
        val m = MotorFalso(l0 = { json("compra", 0.95, "compra" to 0.95) })
        assertNull(cascada(m).decidir("x", PREGUNTA).escalateReason)
    }

    @Test
    fun l2NoTokenizaNiLlamaAOnnxConIdsNoValidos() {
        val m = MotorFalso()
        val s = SesionFalsa()
        var tokenizo = false
        val r = CapaL2(m, s, { tokenizo = true; longArrayOf(1) }).decidir("x", score("bajo", "medio", "alto"))
        assertFalse(r.opina)
        assertFalse(tokenizo)
        assertEquals(0, s.llamadas)
        assertFalse(m.llamadas.contains("L2"))
    }
}
