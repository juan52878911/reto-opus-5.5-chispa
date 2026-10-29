package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.File

/** Hallazgos R1 #3, #8, #14 y #19: cachés por hash y atómicas, τ de L2c, errores de capa visibles, torres que fallan. */
class CacheYErroresTest {
    @get:Rule
    val tmp = TemporaryFolder()

    private val modelo get() = File(tmp.root, "m.chispa").also { if (!it.exists()) it.writeText("x") }

    // --- #3: el ONNX de L2 se identifica por el hash de la sección y se escribe de forma atómica ---

    @Test
    fun dosModelosDelMismoTamanoNoComparteOnnxDeL2() {
        val a = MotorFalso(hashes = mapOf(SECCION_L2 to "aaa")).also { it.alExtraer = { d -> File(d).writeText("A") } }
        val b = MotorFalso(hashes = mapOf(SECCION_L2 to "bbb")).also { it.alExtraer = { d -> File(d).writeText("B") } }
        val ra = CacheFicheros.rutaOnnxL2(a, tmp.root, modelo)
        val rb = CacheFicheros.rutaOnnxL2(b, tmp.root, modelo) // mismo .chispa de tamaño, otra sección L2
        assertTrue(ra != rb)
        assertEquals("A", File(ra).readText())
        assertEquals("B", File(rb).readText())
        CacheFicheros.rutaOnnxL2(a, tmp.root, modelo)
        assertEquals(1, a.extracciones) // la segunda vez reutiliza
    }

    @Test
    fun siLaExtraccionMuereNoQuedaUnOnnxTruncadoConElNombreDefinitivo() {
        val m = MotorFalso(hashes = mapOf(SECCION_L2 to "h1"))
        m.alExtraer = { d -> File(d).writeText("trunc"); throw RuntimeException("proceso muerto") }
        try { CacheFicheros.rutaOnnxL2(m, tmp.root, modelo); org.junit.Assert.fail() } catch (e: RuntimeException) {}
        assertFalse(File(tmp.root, "chispa-l2-h1.onnx").exists())
        assertEquals(emptyList<String>(), tmp.root.list()!!.filter { it.endsWith(".tmp") })
        m.alExtraer = { d -> File(d).writeText("completo") }
        assertEquals("completo", File(CacheFicheros.rutaOnnxL2(m, tmp.root, modelo)).readText())
    }

    // --- #19: copia del asset atómica, con el resultado de renameTo comprobado ---

    @Test
    fun copiarAtomicoNoDejaTemporalesYReemplazaUnDestinoViejo() {
        val destino = File(tmp.root, "chispa/1/modelo.chispa")
        destino.parentFile!!.mkdirs()
        destino.writeText("viejo")
        CacheFicheros.copiarAtomico(ByteArrayInputStream("nuevo".toByteArray()), destino)
        assertEquals("nuevo", destino.readText())
        assertEquals(listOf("modelo.chispa"), destino.parentFile!!.list()!!.toList())
    }

    @Test
    fun siRenameToFallaSeLanzaYNoSeDevuelveUnDestinoInexistente() {
        // el destino es un directorio no vacío: renameTo de un fichero sobre él falla y delete() tampoco puede quitarlo
        val destino = File(tmp.root, "d").also { it.mkdirs(); File(it, "x").writeText("1") }
        try {
            CacheFicheros.copiarAtomico(ByteArrayInputStream("z".toByteArray()), destino)
            org.junit.Assert.fail("debía lanzar ErrorChispa")
        } catch (e: ErrorChispa) {
        }
        assertEquals(listOf("x"), destino.list()!!.toList())
        assertEquals(listOf("d"), tmp.root.list()!!.toList())
    }

    // --- R2 #11: se borran las copias de versiones viejas del asset ---

    @Test
    fun borrarVersionesViejasDejaSoloLaActual() {
        val raiz = File(tmp.root, "chispa")
        for (v in listOf("1", "2", "3")) File(raiz, "$v/modelo.chispa").also { it.parentFile!!.mkdirs(); it.writeText(v) }
        CacheFicheros.borrarVersionesViejas(raiz, "3")
        assertEquals(listOf("3"), raiz.list()!!.toList())
        assertEquals("3", File(raiz, "3/modelo.chispa").readText())
    }

    @Test
    fun borrarVersionesViejasSinCarpetaNoFalla() {
        CacheFicheros.borrarVersionesViejas(File(tmp.root, "nada"), "1")
    }

    // --- R2 #10: el reloj por defecto de la caché negativa es monótono, no el de pared ---

    @Test
    fun elRelojPorDefectoEsMonotonico() {
        val a = relojMonotonicoMs()
        val b = relojMonotonicoMs()
        assertTrue(b >= a)
        // nanoTime/1e6 tiene origen arbitrario; el reloj de pared (epoch) no puede coincidir con él
        assertTrue(kotlin.math.abs(a - System.nanoTime() / 1_000_000L) < 1_000L)
    }

    // --- #8: τ de L2c ---

    @Test
    fun l2cUsaTauL2cSiEsMayorOIgualACero() {
        val m = MotorFalso(
            presentes = listOf("L2"), calib = true, tau = 0.6, conj = true, tauConj = 0.9,
            l2 = { json("compra", 0.7, "compra" to 0.7) },
        )
        val c = Cascada.armar(m, CapaL2(m, SesionFalsa(), { longArrayOf(1) }))
        val r = c.decidir("x", PREGUNTA)
        assertTrue(r.escalar) // 0.7 < 0.9: el servidor también escala
    }

    @Test
    fun l2UsaTauEscalateL2YL1ConservaTauEscalate() {
        val m = MotorFalso(
            presentes = listOf("L1", "L2"), calib = true, tau = 0.6, tauL2 = 0.9,
            l1 = { json("compra", 0.7, "compra" to 0.7) },
            l2 = { json("compra", 0.7, "compra" to 0.7) },
        )
        val r = Cascada.armar(m, CapaL2(m, SesionFalsa(), { longArrayOf(1) })).decidir("x", PREGUNTA)
        assertEquals("L1", r.capa) // 0.7 ≥ 0.6 de L1: no llega a L2 (cuyo τ es 0.9)
        val s = MotorFalso(
            presentes = listOf("L2"), calib = true, tau = 0.6, tauL2 = 0.9,
            l2 = { json("compra", 0.7, "compra" to 0.7) },
        )
        assertTrue(Cascada.armar(s, CapaL2(s, SesionFalsa(), { longArrayOf(1) })).decidir("x", PREGUNTA).escalar)
    }

    @Test
    fun sinTauL2cL2UsaTauEscalate() {
        val m = MotorFalso(
            presentes = listOf("L2"), calib = true, tau = 0.6, conj = true, tauConj = -1.0,
            l2 = { json("compra", 0.7, "compra" to 0.7) },
        )
        val r = Cascada.armar(m, CapaL2(m, SesionFalsa(), { longArrayOf(1) })).decidir("x", PREGUNTA)
        assertFalse(r.escalar)
        assertEquals("L2", r.capa)
    }

    @Test
    fun sinConjTauL2cNoSeAplica() {
        val m = MotorFalso(
            presentes = listOf("L2"), calib = true, tau = 0.6, conj = false, tauConj = 0.9,
            l2 = { json("compra", 0.7, "compra" to 0.7) },
        )
        assertFalse(Cascada.armar(m, CapaL2(m, SesionFalsa(), { longArrayOf(1) })).decidir("x", PREGUNTA).escalar)
    }

    // --- #14: errores de capa visibles y torre que falla no se recalcula ---

    @Test
    fun unErrorDeCapaSeRegistraConSuNombre() {
        val vistos = ArrayList<String>()
        val m = MotorFalso(
            l0 = { throw IllegalStateException("boom") },
            l1 = { json("soporte", 0.95, "soporte" to 0.95) },
        )
        val r = Cascada.armar(m, null) { capa, e -> vistos.add("$capa:${e.message}") }.decidir("x", PREGUNTA)
        assertEquals("L1", r.capa)
        assertEquals(listOf("L0:boom"), vistos)
    }

    @Test
    fun unaTorreQueFallaNoSeRecalculaEnCadaLlamadaHastaElTtl() {
        val m = MotorFalso(torres = false)
        m.textosTorre = listOf("t1", "t2")
        var llamadasCodificador = 0
        var ahora = 0L
        val c = CapaL2(m, SesionFalsa(), { longArrayOf(1) }, { llamadasCodificador++; throw ErrorChispa("no carga") }, { ahora })
        try { c.decidir("x", PREGUNTA_NUEVA); org.junit.Assert.fail() } catch (e: ErrorChispa) {}
        assertEquals(1, llamadasCodificador)
        repeat(3) { assertFalse(c.decidir("x", PREGUNTA_NUEVA).opina) }
        assertEquals(1, llamadasCodificador) // la negativa cacheada evita más pasadas de la torre
        ahora = 61_000L
        try { c.decidir("x", PREGUNTA_NUEVA); org.junit.Assert.fail() } catch (e: ErrorChispa) {}
        assertEquals(2, llamadasCodificador)
    }

    @Test
    fun siElMotorRechazaLasTorresSeLanzaYSeCacheaLaNegativa() {
        val rechazo = MotorFalso(torres = false).also { it.aceptaTorres = false; it.textosTorre = listOf("t1", "t2") }
        var codificadas = 0
        val c = CapaL2(rechazo, SesionFalsa(), { longArrayOf(1) }, { codificadas++; floatArrayOf(1f, 2f) }, { 0L })
        try { c.decidir("x", PREGUNTA_NUEVA); org.junit.Assert.fail() } catch (e: ErrorChispa) {
            assertTrue(e.message!!.contains("rechazó"))
        }
        assertFalse(c.decidir("x", PREGUNTA_NUEVA).opina)
        assertEquals(2, codificadas) // solo la primera llamada codificó (2 textos)
    }
}
