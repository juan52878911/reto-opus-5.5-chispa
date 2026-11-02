package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Test

/** Casos copiados de server/decide/testdata/normalizacion.json (entrada → salida de `normalizar_mayusculas` en Python). */
class NormalizarMayusculasTest {
    private val casos = listOf(
        "ABCDEFG" to "ABCDEFG",
        "ABCDEFGHIJklmn" to "abcdefghijklmn",
        "ABCDEFGhij" to "ABCDEFGhij",
        "ABCDEFGHij" to "abcdefghij",
        "ÁRBOL ÑANDÚ ÉXITO" to "árbol ñandú éxito",
        "12345 !!! 678" to "12345 !!! 678",
        "" to "",
        "HOLA 😀 QUIERO CANCELAR 123 MI TARJETA 💳" to "hola 😀 quiero cancelar 123 mi tarjeta 💳",
        "Quiero cancelar mi tarjeta" to "Quiero cancelar mi tarjeta",
        "ARBOL ñandú" to "ARBOL ñandú",
        "CANCELAR MI TARJETA YA" to "cancelar mi tarjeta ya",
        "¿QUÉ PASA CON MI PEDIDO? Gracias" to "¿qué pasa con mi pedido? gracias",
        "LA CITA Nº 2ª vez" to "LA CITA Nº 2ª vez", // «ª» y «º» son letras, no mayúsculas
        "ⓉⓄⒹⓄ ⓂⒶⓁ ok" to "ⓉⓄⒹⓄ ⓂⒶⓁ ok", // letras en círculo: no son letras (categoría So)
    )

    @Test
    fun paridadConPython() {
        for ((entrada, salida) in casos) assertEquals(entrada, salida, normalizarMayusculas(entrada))
    }

    @Test
    fun limites() {
        assertEquals("ABCDEFG", normalizarMayusculas("ABCDEFG")) // 7 letras
        assertEquals("abcdefgh", normalizarMayusculas("ABCDEFGH")) // 8 letras
        assertEquals("ABCDEFGHIJKLMNopqrst", normalizarMayusculas("ABCDEFGHIJKLMNopqrst")) // 70 % exacto
        val setentaYUno = "A".repeat(71) + "b".repeat(29)
        assertEquals(setentaYUno.lowercase(java.util.Locale.ROOT), normalizarMayusculas(setentaYUno))
        val setenta = "A".repeat(70) + "b".repeat(30)
        assertEquals(setenta, normalizarMayusculas(setenta))
    }

    @Test
    fun idempotente() {
        for ((entrada, _) in casos) {
            val una = normalizarMayusculas(entrada)
            assertEquals(una, normalizarMayusculas(una))
        }
    }

    @Test
    fun l2NormalizaElMensajeAntesDeTokenizar() {
        val vistos = mutableListOf<String>()
        val m = MotorFalso(l2 = { json("compra", 0.9, "compra" to 0.9) })
        val capa = CapaL2(m, SesionFalsa(), { vistos.add(it); longArrayOf(0, 7, 2) })
        capa.decidir("CANCELAR MI TARJETA YA", PREGUNTA)
        capa.decidir("cancelar mi tarjeta ya", PREGUNTA)
        capa.decidir("ABCDEFG", PREGUNTA)
        assertEquals(listOf("cancelar mi tarjeta ya", "cancelar mi tarjeta ya", "ABCDEFG"), vistos)
    }
}
