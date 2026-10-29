package com.chispa.demo

import com.chispa.sdk.Capa
import com.chispa.sdk.CapaConTau
import com.chispa.sdk.Cascada
import com.chispa.sdk.ErrorChispa
import com.chispa.sdk.Opcion
import com.chispa.sdk.Pregunta
import com.chispa.sdk.SalidaCapa
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** R2 #12: la Cascada se traga las excepciones de capa; «Medir» las cuenta con alErrorCapa. */
class MedidorErroresTest {
    private val pregunta = Pregunta("¿qué quiere?", listOf(Opcion("a", null), Opcion("b", null)), "choice")

    private val capaRota = object : Capa {
        override val nombre = "L2"
        override fun decidir(texto: String, pregunta: Pregunta): SalidaCapa = throw ErrorChispa("torre sin memoria")
    }

    @Test
    fun unFalloDeCapaSeCuentaComoErrorYQuedaEnLaNota() {
        val fallos = Medidor.Companion.FallosCapa()
        val cascada = Cascada(listOf(CapaConTau(capaRota, 0.0)), alErrorCapa = fallos::anotar)
        val r = Medidor.medir("t", "zero-shot", "c", ConfigMedida(n = 3, calentamiento = 2), {}, { false }, fallos) {
            cascada.decidir(it, pregunta)
        }
        assertEquals(1 + 1 + 3, r.errores) // primera + 1 de calentamiento + 3 medidas
        assertTrue(r.nota, r.nota!!.contains("torre sin memoria"))
    }

    @Test
    fun sinFallosErroresSigueEnCero() {
        val fallos = Medidor.Companion.FallosCapa()
        val r = Medidor.medir("t", "few-shot", "c", ConfigMedida(n = 2, calentamiento = 1), {}, { false }, fallos) {
            com.chispa.sdk.Respuesta("a", 1.0, mapOf("a" to 1.0), "L1", false, 0.1)
        }
        assertEquals(0, r.errores)
        assertEquals(null, r.nota)
    }
}
