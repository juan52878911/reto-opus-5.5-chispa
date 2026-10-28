package com.chispa.sdk

import android.content.Context
import java.io.File

/**
 * Chispa en el móvil: un .chispa v3 abierto con la cascada L0 → L1 → L2.
 *
 *     val chispa = Chispa.abrir(contexto, "modelo.chispa")
 *     val r = chispa.decidir("quiero comprar dos camisetas", listOf(pregunta)).first()
 *     // r.respuesta, r.confianza, r.capa, r.escalar
 *
 * L2 (ONNX Runtime) solo se monta si el fichero trae las secciones L2 y ESQUEMAS **y** se da un [Tokenizador] de e5.
 */
class Chispa private constructor(
    private val motor: Motor,
    private val cascada: Cascada,
    private val sesion: SesionRanuras?,
) : AutoCloseable {

    /** Capas que han quedado montadas, en orden. */
    val capas: List<String> get() = motor.capas().filter { it != "L2" || sesion != null }

    /** Decide cada pregunta para el [texto] (en orden). Sin conexión: todo ocurre en el dispositivo. */
    fun decidir(texto: String, preguntas: List<Pregunta>): List<Respuesta> =
        preguntas.map { cascada.decidir(texto, it) }

    override fun close() {
        sesion?.close()
        motor.close()
    }

    companion object {
        /**
         * Abre el modelo. [rutaModelo] es la ruta absoluta de un fichero, o el nombre de un asset (se copia una vez a
         * `filesDir`, porque el motor lo mapea en memoria y necesita un fichero de verdad).
         */
        fun abrir(contexto: Context, rutaModelo: String, tokenizador: Tokenizador? = null): Chispa {
            val fichero = resolver(contexto, rutaModelo)
            val motor = MotorNativo.abrir(fichero.absolutePath)
            return try {
                montar(motor, tokenizador, onnx = { motor.extraerL2ARuta(contexto, fichero) })
            } catch (e: Throwable) {
                motor.close()
                throw e
            }
        }

        /** Monta la cascada sobre cualquier [Motor] (los tests usan uno falso). [onnx] da la ruta del ONNX de L2. */
        internal fun montar(
            motor: Motor,
            tokenizador: Tokenizador?,
            onnx: () -> String,
            crearSesion: (String) -> SesionRanuras = { SesionOrt(it) },
        ): Chispa {
            var sesion: SesionRanuras? = null
            var l2: CapaL2? = null
            if ("L2" in motor.capas() && tokenizador != null) {
                sesion = crearSesion(onnx())
                l2 = CapaL2(motor, sesion, tokenizador)
            }
            try {
                return Chispa(motor, Cascada.armar(motor, l2), sesion)
            } catch (e: Throwable) {
                sesion?.close()
                throw e
            }
        }

        private fun resolver(contexto: Context, ruta: String): File {
            val f = File(ruta)
            if (f.isAbsolute) {
                if (!f.isFile) throw ErrorChispa("no existe el modelo $ruta")
                return f
            }
            val destino = File(contexto.filesDir, "chispa/$ruta")
            val tam = try {
                contexto.assets.openFd(ruta).use { it.length }
            } catch (e: java.io.IOException) {
                -1L // comprimido en el APK (sin openFd) o inexistente: se decide al abrirlo
            }
            if (destino.isFile && tam >= 0 && destino.length() == tam) return destino
            destino.parentFile?.mkdirs()
            try {
                contexto.assets.open(ruta).use { entrada ->
                    File(destino.path + ".tmp").outputStream().use { entrada.copyTo(it) }
                }
            } catch (e: java.io.IOException) {
                throw ErrorChispa("no existe el asset $ruta ni el fichero: ${e.message}", e)
            }
            File(destino.path + ".tmp").renameTo(destino)
            return destino
        }

        private fun Motor.extraerL2ARuta(contexto: Context, modelo: File): String {
            val onnx = File(contexto.cacheDir, "chispa-l2-${modelo.length()}.onnx")
            if (!onnx.isFile || onnx.length() == 0L) extraerL2(onnx.absolutePath)
            return onnx.absolutePath
        }
    }
}
