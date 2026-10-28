package com.chispa.sdk

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ModelosTest {
    @Test
    fun preguntaAJsonComoElServidor() {
        val o = JSONObject(PREGUNTA.toJson())
        assertEquals("¿Qué quiere el cliente?", o.getString("question"))
        assertEquals("choice", o.getString("kind"))
        val ops = o.getJSONArray("options")
        assertEquals(3, ops.length())
        assertEquals("compra", ops.getJSONObject(0).getString("id"))
        assertEquals("quiere comprar", ops.getJSONObject(0).getString("description"))
        assertFalse(ops.getJSONObject(2).has("description")) // sin descripción no se envía el campo
    }

    @Test
    fun parseaUnaRespuestaCompleta() {
        val s = SalidaCapa.desdeJson("""{"ok":true,"opina":true,"answer":"queja","conf":0.75,"probs":{"queja":0.75,"compra":0.25}}""")
        assertTrue(s.opina)
        assertEquals("queja", s.respuesta)
        assertEquals(0.75, s.confianza, 1e-12)
        assertEquals(0.25, s.probs["compra"]!!, 1e-12)
    }

    @Test
    fun sinOpinionYErrores() {
        assertFalse(SalidaCapa.desdeJson("""{"ok":true,"opina":false,"answer":"","conf":0,"probs":{}}""").opina)
        val ex = try { SalidaCapa.desdeJson("""{"ok":false,"error":"el fichero no trae la sección L1"}"""); null } catch (e: ErrorChispa) { e }
        assertEquals("el fichero no trae la sección L1", ex!!.message)
        val ex2 = try { SalidaCapa.desdeJson("esto no es json"); null } catch (e: ErrorChispa) { e }
        assertTrue(ex2!!.message!!.startsWith("respuesta de la capa ilegible"))
    }

    @Test
    fun confianzaCeroNoOpinaAunqueHayaRespuesta() {
        assertFalse(SalidaCapa("a", 0.0, emptyMap()).opina)
        assertFalse(SalidaCapa("", 0.9, emptyMap()).opina)
    }
}
