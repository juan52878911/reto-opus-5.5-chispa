package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** El rechazo de las torres al vuelo dice por qué, y una torre fallida no deja a la cascada parseando una respuesta vacía. */
class TorreMotivoTest {
    private val textos = listOf("passage: q · fraude · cargo", "passage: q · tarjeta · bloqueada")

    private fun capa(m: MotorFalso, enc: CodificadorTorre, ahoraMs: () -> Long = { 0L }) =
        CapaL2(m, SesionFalsa(), { longArrayOf(0, 7, 2) }, enc, ahoraMs)

    @Test
    fun elMensajeDeErrorIncluyeElMotivoDelMotor() {
        val m = MotorFalso(torres = false)
        m.textosTorre = textos
        m.aceptaTorres = false
        m.motivoRechazo = "d=2 no casa con el Dim=256 que declara TORR"
        val c = capa(m, { floatArrayOf(1f, 2f) })
        val ex = try { c.decidir("hola", PREGUNTA_NUEVA); null } catch (e: ErrorChispa) { e }
        assertTrue(ex != null)
        assertTrue(ex!!.message, ex.message!!.contains("d=2, n=2"))
        assertTrue(ex.message, ex.message!!.contains("Dim=256"))
    }

    @Test
    fun unaSalidaConValoresNoFinitosSeReportaConSuMotivo() {
        // Lo que daría un ONNX fp16 que desborda: el motor (Go) rechaza el Inf y lo dice.
        val m = MotorFalso(torres = false)
        m.textosTorre = textos
        m.aceptaTorres = false
        m.motivoRechazo = "valor no finito (+Inf) en la torre 0, columna 0: la salida del ONNX de la torre desbordó (¿fp16?)"
        val c = capa(m, { floatArrayOf(Float.POSITIVE_INFINITY, 1f) })
        val ex = try { c.decidir("hola", PREGUNTA_NUEVA); null } catch (e: ErrorChispa) { e }
        assertTrue(ex!!.message, ex.message!!.contains("desbordó"))
    }

    @Test
    fun elMotorPorDefectoSinMotivoDaUnoGenerico() {
        val m = MotorFalso(torres = false)
        m.textosTorre = textos
        m.aceptaTorres = false
        assertEquals("motivo falso", m.instalarTorresL2Motivo("{}", ByteArray(0), 0))
        m.aceptaTorres = true
        assertEquals("", m.instalarTorresL2Motivo("{}", ByteArray(0), 0))
    }

    @Test
    fun trasUnFalloDeTorreLaCascadaRegistraUnSoloErrorYNoParseaRespuestaVacia() {
        val m = MotorFalso(torres = false, l2 = { "" }) // si algo llegara a puntuar, devolvería vacío
        m.textosTorre = textos
        m.aceptaTorres = false
        val errores = ArrayList<Pair<String, Throwable>>()
        val c = capa(m, { floatArrayOf(1f, 2f) })
        val cascada = Cascada.armar(m, c, alErrorCapa = { n, e -> errores.add(n to e) })
        repeat(3) {
            val r = cascada.decidir("hola", PREGUNTA_NUEVA)
            assertTrue(r.escalar)
        }
        assertEquals(1, errores.size) // el de la torre; los otros dos intentos caen en la caché negativa
        assertEquals("L2", errores[0].first)
        assertFalse(errores[0].second.message!!.contains("ilegible"))
        assertFalse(m.llamadas.contains("L2")) // L2 no llegó a puntuar
    }

    @Test
    fun unaRespuestaVaciaDelMotorTieneMensajeClaro() {
        val ex = try { SalidaCapa.desdeJson(""); null } catch (e: ErrorChispa) { e }
        assertEquals("el motor devolvió una respuesta vacía", ex!!.message)
    }
}
