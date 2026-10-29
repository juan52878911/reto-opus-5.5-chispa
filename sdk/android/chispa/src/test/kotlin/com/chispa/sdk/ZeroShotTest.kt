package com.chispa.sdk

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Zero-shot (esquema que el .chispa no trae), few-shot (esquema entrenado dentro del .chispa) y L0TF. */
class ZeroShotTest {
    private val textos = listOf("passage: q · fraude · cargo", "passage: q · tarjeta · bloqueada")

    private class Codificador : CodificadorTorre {
        val pedidos = ArrayList<String>()
        override fun torre(texto: String): FloatArray {
            pedidos.add(texto)
            return if ("fraude" in texto) floatArrayOf(1f, -2f) else floatArrayOf(0.5f, 4f)
        }
    }

    private fun capa(m: MotorFalso, enc: CodificadorTorre?, ahoraMs: () -> Long = { 0L }) =
        CapaL2(m, SesionFalsa(), { longArrayOf(0, 7, 2) }, enc, ahoraMs)

    @Test
    fun esquemaNuevoLaPrimeraVezCalculaLasTorresYLaSegundaUsaLaCache() {
        val m = MotorFalso(torres = false, l2 = { json("fraude", 0.9, "fraude" to 0.9) })
        m.textosTorre = textos
        val enc = Codificador()
        val c = capa(m, enc)

        val r1 = c.decidir("no reconozco un cargo", PREGUNTA_NUEVA)
        assertEquals("fraude", r1.respuesta)
        assertEquals(textos, enc.pedidos)
        assertEquals(listOf("TORRES", "L2"), m.llamadas)
        assertEquals(2, m.nInstaladas)
        val esperado = ByteBuffer.allocate(16).order(ByteOrder.LITTLE_ENDIAN)
        for (x in floatArrayOf(1f, -2f, 0.5f, 4f)) esperado.putFloat(x)
        assertArrayEquals(esperado.array(), m.torresInstaladas)

        val r2 = c.decidir("otro mensaje", PREGUNTA_NUEVA)
        assertEquals("fraude", r2.respuesta)
        assertEquals(textos, enc.pedidos) // no volvió a codificar
        assertEquals(listOf("TORRES", "L2", "L2"), m.llamadas)
        assertEquals(2, m.nInstaladas)
    }

    @Test
    fun sinCodificadorUnEsquemaNuevoNoOpinaYNoTokeniza() {
        val m = MotorFalso(torres = false)
        m.textosTorre = textos
        var tokenizo = false
        val capa = CapaL2(m, SesionFalsa(), { tokenizo = true; longArrayOf(1) })
        assertFalse(capa.decidir("hola", PREGUNTA_NUEVA).opina)
        assertFalse(tokenizo)
        assertTrue(m.llamadas.isEmpty())
    }

    @Test
    fun siElMotorNoPideTextosNoOpina() {
        val m = MotorFalso(torres = false) // motor sin soporte de torres al vuelo
        val enc = Codificador()
        assertFalse(capa(m, enc).decidir("hola", PREGUNTA_NUEVA).opina)
        assertTrue(enc.pedidos.isEmpty())
    }

    @Test
    fun siElCodificadorFallaNoSeCacheaYSeReintentaPasadoElTtl() {
        val m = MotorFalso(torres = false, l2 = { json("fraude", 0.9, "fraude" to 0.9) })
        m.textosTorre = textos
        var falla = true
        var ahora = 0L
        val c = capa(m, { t -> if (falla) throw ErrorChispa("sin memoria") else floatArrayOf(1f, 2f) }, { ahora })
        val ex = try { c.decidir("hola", PREGUNTA_NUEVA); null } catch (e: ErrorChispa) { e }
        assertTrue(ex != null)
        assertEquals(0, m.nInstaladas)
        falla = false
        ahora = 61_000L // pasado el TTL de la caché negativa
        assertEquals("fraude", c.decidir("hola", PREGUNTA_NUEVA).respuesta)
    }

    @Test
    fun dimensionesDeTorreDistintasSeRechazan() {
        val m = MotorFalso(torres = false)
        m.textosTorre = textos
        val c = capa(m, { t -> if ("fraude" in t) floatArrayOf(1f) else floatArrayOf(1f, 2f) })
        val ex = try { c.decidir("hola", PREGUNTA_NUEVA); null } catch (e: ErrorChispa) { e }
        assertTrue(ex != null)
        assertEquals(0, m.nInstaladas)
    }

    @Test
    fun cascadaZeroShotL0NoTieneModeloL1Duda_L2AlVueloDecide() {
        val m = MotorFalso(
            torres = false,
            l1 = { json("fraude", 0.55, "fraude" to 0.55, "tarjeta" to 0.45) }, // L1-zs con descripciones: por debajo de τ
            l2 = { json("fraude", 0.93, "fraude" to 0.93) },
        )
        m.textosTorre = textos
        val r = Cascada.armar(m, capa(m, Codificador())).decidir("no reconozco un cargo", PREGUNTA_NUEVA)
        assertEquals("L2", r.capa)
        assertFalse(r.escalar)
        assertEquals(listOf("L0", "L1", "TORRES", "L2"), m.llamadas)
    }

    @Test
    fun cascadaZeroShotL1SeguraNoLlegaAL2() {
        val m = MotorFalso(torres = false, l1 = { json("fraude", 0.9, "fraude" to 0.9) })
        m.textosTorre = textos
        val enc = Codificador()
        val r = Cascada.armar(m, capa(m, enc)).decidir("cargo raro", PREGUNTA_NUEVA)
        assertEquals("L1", r.capa)
        assertTrue(enc.pedidos.isEmpty()) // no se calcula ninguna torre si L1 basta
    }

    @Test
    fun montarPasaElCodificadorALaCapaL2() {
        val m = MotorFalso(torres = false, l2 = { json("fraude", 0.95, "fraude" to 0.95) })
        m.textosTorre = textos
        val ch = Chispa.montar(m, { longArrayOf(0, 2) }, { "x.onnx" }, { SesionFalsa() }, Codificador())
        val r = ch.decidir("hola", listOf(PREGUNTA_NUEVA))[0]
        assertEquals("L2", r.capa)
        assertEquals(2, m.nInstaladas)
    }

    @Test
    fun fewShotElEsquemaEntrenadoVieneEnElFicheroYNoCalculaTorres() {
        // few-shot: chispa train metió L0 (L0TF) y ESQUEMAS del esquema; el SDK no necesita codificador
        val m = MotorFalso(
            l0 = { json("compra", 0.97, "compra" to 0.97, "soporte" to 0.02, "saludo" to 0.01) },
        )
        val enc = Codificador()
        val r = Cascada.armar(m, capa(m, enc)).decidir("quiero dos camisetas", PREGUNTA)
        assertEquals("L0", r.capa)
        assertEquals(0.97, r.confianza, 1e-12)
        assertEquals(listOf("L0"), m.llamadas)
        assertTrue(enc.pedidos.isEmpty())
    }

    @Test
    fun fewShotConTorresEnElFicheroL2NoCalculaNada() {
        val m = MotorFalso(
            torres = true,
            l0 = { json("compra", 0.4, "compra" to 0.4, "soporte" to 0.3, "saludo" to 0.3) },
            l1 = { json("compra", 0.5, "compra" to 0.5) },
            l2 = { json("compra", 0.9, "compra" to 0.9) },
        )
        m.textosTorre = textos
        val enc = Codificador()
        assertEquals("L2", Cascada.armar(m, capa(m, enc)).decidir("hola", PREGUNTA).capa)
        assertTrue(enc.pedidos.isEmpty())
        assertEquals(0, m.nInstaladas)
    }

    @Test
    fun l0TfPasaSusProbabilidadesALaCabezaConjuntaDeL2c() {
        // L0TF responde con sus probabilidades (por debajo de τ); L2c las recibe como «l0»
        val m = MotorFalso(
            conj = true,
            l0 = { json("compra", 0.6, "compra" to 0.6, "soporte" to 0.3, "saludo" to 0.1) },
            cabeza = { json("compra", 0.95, "compra" to 0.95) },
        )
        val r = Cascada.armar(m, capa(m, null)).decidir("hola", PREGUNTA)
        assertEquals("L2", r.capa)
        assertEquals(listOf("L0", "L1", "CONJ"), m.llamadas)
        assertTrue(m.ultimoSimsJson!!.contains("\"saludo\""))
    }
}
