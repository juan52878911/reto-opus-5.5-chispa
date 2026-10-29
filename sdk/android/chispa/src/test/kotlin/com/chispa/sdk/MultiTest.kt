package com.chispa.sdk

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** El tipo `multi`: cada opción es un sí/no; la confianza de la capa es la de la opción más dudosa (la calcula el motor). */
class MultiTest {
    private val probs = arrayOf("cobro" to 0.93, "atencion" to 0.81, "fraude" to 0.07)

    private fun cascada(m: MotorFalso) = Cascada.armar(m, CapaL2(m, SesionFalsa(), { longArrayOf(1) }))

    @Test
    fun preguntaMultiViajaConSuKind() {
        assertEquals("multi", JSONObject(PREGUNTA_MULTI.toJson()).getString("kind"))
    }

    @Test
    fun leeLasActivasYLasProbsPorOpcion() {
        val s = SalidaCapa.desdeJson(jsonMulti(listOf("cobro", "atencion"), 0.81, *probs))
        assertTrue(s.opina)
        assertEquals("cobro", s.respuesta)
        assertEquals(listOf("cobro", "atencion"), s.respuestas)
        assertEquals(0.07, s.probs["fraude"]!!, 1e-12) // las p no suman 1
    }

    @Test
    fun sinAnswersNoEsMulti() {
        assertNull(SalidaCapa.desdeJson(json("compra", 0.9, "compra" to 0.9)).respuestas)
    }

    @Test
    fun conActivasLaCapaQueLlegaATauResponde() {
        val m = MotorFalso(l1 = { jsonMulti(listOf("cobro", "atencion"), 0.81, *probs) })
        val r = cascada(m).decidir("me cobraron dos veces y nadie contesta", PREGUNTA_MULTI)
        assertFalse(r.escalar)
        assertEquals("L1", r.capa)
        assertEquals("cobro", r.respuesta)
        assertEquals(listOf("cobro", "atencion"), r.respuestas)
        assertEquals(0.81, r.confianza, 1e-12)
        assertEquals(listOf("L0", "L1"), m.llamadas) // L0 no opina en multi, L1 basta
    }

    @Test
    fun ningunaActivaEsUnaRespuestaValidaYNoEscala() {
        val m = MotorFalso(l1 = { jsonMulti(emptyList(), 0.90, "cobro" to 0.05, "atencion" to 0.10, "fraude" to 0.02) })
        val r = cascada(m).decidir("hola, buenos días", PREGUNTA_MULTI)
        assertFalse(r.escalar)
        assertEquals("L1", r.capa)
        assertEquals("", r.respuesta)
        assertTrue(r.respuestas.isEmpty())
        assertEquals(0.90, r.confianza, 1e-12)
    }

    @Test
    fun unaOpcionDudosaHaceQueLaCapaNoLleguePasaALaSiguiente() {
        // L1: una opción está en 0,55 → la confianza de la capa es 0,55 < τ y se pasa a L2
        val m = MotorFalso(
            l1 = { jsonMulti(listOf("cobro"), 0.55, "cobro" to 0.95, "atencion" to 0.45, "fraude" to 0.03) },
            l2 = { jsonMulti(listOf("cobro", "atencion"), 0.88, "cobro" to 0.97, "atencion" to 0.88, "fraude" to 0.02) },
        )
        val r = cascada(m).decidir("x", PREGUNTA_MULTI)
        assertFalse(r.escalar)
        assertEquals("L2", r.capa)
        assertEquals(listOf("cobro", "atencion"), r.respuestas)
        assertEquals(listOf("L0", "L1", "L2"), m.llamadas)
    }

    @Test
    fun siNingunaCapaLlegaEscalaConLasActivasDeLaMejorPista() {
        val m = MotorFalso(
            l1 = { jsonMulti(listOf("cobro"), 0.55, "cobro" to 0.95, "atencion" to 0.45, "fraude" to 0.03) },
            l2 = { jsonMulti(listOf("cobro", "fraude"), 0.60, "cobro" to 0.90, "atencion" to 0.20, "fraude" to 0.60) },
        )
        val r = cascada(m).decidir("x", PREGUNTA_MULTI)
        assertTrue(r.escalar)
        assertEquals("escalar", r.capa)
        assertEquals(0.60, r.confianza, 1e-12)
        assertEquals(listOf("cobro", "fraude"), r.respuestas) // la pista es la de mayor confianza (L2)
    }

    @Test
    fun escalarSinNingunaOpinionDejaRespuestasVacias() {
        val r = cascada(MotorFalso()).decidir("x", PREGUNTA_MULTI)
        assertTrue(r.escalar)
        assertTrue(r.respuestas.isEmpty())
    }

    @Test
    fun choiceNoLlevaRespuestas() {
        val m = MotorFalso(l0 = { json("compra", 0.95, "compra" to 0.95) })
        assertTrue(cascada(m).decidir("x", PREGUNTA).respuestas.isEmpty())
    }
}
