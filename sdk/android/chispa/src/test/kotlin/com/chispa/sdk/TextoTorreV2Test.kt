package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * Texto de torre v2 (META.texto_torre = «v2_sin_id»): lo construye el motor (chispamovil, con la regla de runtime/torre) y el SDK
 * lo pasa tal cual al codificador. Con descripción no lleva el id; sin ella, el texto v1.
 */
class TextoTorreV2Test {
    private val v2 = listOf("passage: ¿Qué tipo de incidencia es? · cargo no reconocido", "passage: ¿Qué tipo de incidencia es? · tarjeta bloqueada o perdida")

    private class Codificador : CodificadorTorre {
        val pedidos = ArrayList<String>()
        override fun torre(texto: String): FloatArray {
            pedidos.add(texto)
            return if ("cargo" in texto) floatArrayOf(1f, -2f) else floatArrayOf(0.5f, 4f)
        }
    }

    @Test
    fun elCodificadorRecibeLosTextosDelMotorSinReconstruirlos() {
        val m = MotorFalso(torres = false, l2 = { json("fraude", 0.9, "fraude" to 0.9) })
        m.versionTorre = "v2_sin_id"
        m.textosTorre = v2
        val enc = Codificador()
        val c = CapaL2(m, SesionFalsa(), { longArrayOf(0, 7, 2) }, enc, { 0L })
        c.decidir("no reconozco un cargo", PREGUNTA_NUEVA)
        assertEquals(v2, enc.pedidos)
        assertEquals("v2_sin_id", m.textoTorre())
    }

    @Test
    fun sinElCampoLaVersionEsV1() {
        assertEquals("v1", MotorFalso().textoTorre())
    }
}
