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
 * L0 usa la sección L0TF si el fichero la trae. L2 (ONNX Runtime) solo se monta si el fichero trae las secciones L2
 * y ESQUEMAS **y** hay tokenizador de e5: el de la app ([Tokenizador]) o el del motor, cargado de un `.chispa-tok`
 * (`rutaTokenizador`, el mismo que usa el servidor). Con CONJ en el fichero, L2 es L2c (cabeza conjunta).
 *
 * Esquema nuevo (zero-shot): la pregunta trae sus opciones con descripciones. L1 las usa tal cual (torres de texto
 * cacheadas en el motor); L2 recibe las torres al vuelo con un [CodificadorTorre] (opcional) y el motor las cachea.
 */
class Chispa private constructor(
    private val motor: Motor,
    private val cascada: Cascada,
    private val sesion: SesionRanuras?,
    private val torreOrt: AutoCloseable? = null,
) : AutoCloseable {

    /** El proveedor de ORT con el que quedó L2 (CPU si el pedido falló); null si no hay L2 o la sesión es de otro tipo. */
    val proveedorOrt: ProveedorOrt? get() = (sesion as? SesionOrt)?.proveedorEfectivo

    /** Capas que han quedado montadas, en orden. */
    val capas: List<String> get() = motor.capas().filter { it != "L2" || sesion != null }

    /** Decide cada pregunta para el [texto] (en orden). Sin conexión: todo ocurre en el dispositivo. */
    fun decidir(texto: String, preguntas: List<Pregunta>): List<Respuesta> =
        preguntas.map { cascada.decidir(texto, it) }

    override fun close() {
        sesion?.close()
        torreOrt?.close()
        motor.close()
    }

    companion object {
        /**
         * Abre el modelo. [rutaModelo] es la ruta absoluta de un fichero, o el nombre de un asset (se copia una vez a
         * `filesDir`, porque el motor lo mapea en memoria y necesita un fichero de verdad).
         * [proveedorOrt] elige el proveedor de ORT de L2 y de la torre (XNNPACK por defecto; si falla al crear la sesión, CPU).
         * [lambdaSoporteL1]/[lambdaSoporteL2]: λ del soporte few-shot (`AbrirConSoporte`); nulos = `Abrir` de siempre.
         */
        fun abrir(
            contexto: Context,
            rutaModelo: String,
            tokenizador: Tokenizador? = null,
            rutaTokenizador: String? = null,
            codificadorTorres: CodificadorTorre? = null,
            alErrorCapa: (String, Throwable) -> Unit = ::registrarErrorCapa,
            proveedorOrt: ProveedorOrt = PROVEEDOR_ORT_POR_DEFECTO,
            lambdaSoporteL1: Double? = null,
            lambdaSoporteL2: Double? = null,
        ): Chispa {
            val fichero = resolver(contexto, rutaModelo)
            val motor = MotorNativo.abrir(fichero.absolutePath, soporteDe(lambdaSoporteL1, lambdaSoporteL2))
            return try {
                var tok = tokenizador
                if (tok == null && rutaTokenizador != null) {
                    motor.cargarTokenizadorE5(resolver(contexto, rutaTokenizador).absolutePath)
                    tok = TokenizadorMotor(motor)
                }
                montar(motor, tok, onnx = { motor.extraerL2ARuta(contexto, fichero) }, codificadorTorres = codificadorTorres, alErrorCapa = alErrorCapa,
                    crearSesion = { SesionOrt(it, proveedorOrt) }, crearSesionTorre = { SesionTorreOrt(it, proveedorOrt) })
            } catch (e: Throwable) {
                motor.close()
                throw e
            }
        }

        /** (λL1, λL2) para `AbrirConSoporte`; un λ nulo es ∞ (sin mezcla); sin ninguno, null = `Abrir` de siempre. */
        internal fun soporteDe(l1: Double?, l2: Double?): Pair<Double, Double>? =
            if (l1 == null && l2 == null) null else Pair(l1 ?: Double.POSITIVE_INFINITY, l2 ?: Double.POSITIVE_INFINITY)

        /** Monta la cascada sobre cualquier [Motor] (los tests usan uno falso). [onnx] da la ruta del ONNX de L2. */
        internal fun montar(
            motor: Motor,
            tokenizador: Tokenizador?,
            onnx: () -> String,
            crearSesion: (String) -> SesionRanuras = { SesionOrt(it) },
            codificadorTorres: CodificadorTorre? = null,
            crearSesionTorre: (ByteArray) -> SesionTorre = { SesionTorreOrt(it) },
            alErrorCapa: (String, Throwable) -> Unit = ::registrarErrorCapa,
        ): Chispa {
            var sesion: SesionRanuras? = null
            var l2: CapaL2? = null
            var torreOrt: CodificadorTorreMotor? = null
            if ("L2" in motor.capas() && tokenizador != null) {
                sesion = crearSesion(onnx())
                // Sin codificador de la app, y con TORR en el fichero, las torres al vuelo salen del ONNX de TORR.
                var enc = codificadorTorres
                if (enc == null && motor.tieneTorre() && motor.tieneTokenizadorE5()) {
                    torreOrt = CodificadorTorreMotor(motor, crearSesionTorre)
                    enc = torreOrt
                }
                l2 = CapaL2(motor, sesion, tokenizador, enc)
            }
            try {
                return Chispa(motor, Cascada.armar(motor, l2, alErrorCapa = alErrorCapa), sesion, torreOrt)
            } catch (e: Throwable) {
                sesion?.close()
                torreOrt?.close()
                throw e
            }
        }

        private fun resolver(contexto: Context, ruta: String): File {
            val f = File(ruta)
            if (f.isAbsolute) {
                if (!f.isFile) throw ErrorChispa("no existe el modelo $ruta")
                return f
            }
            // Una carpeta por versión de la app (lastUpdateTime): un .chispa reentrenado del mismo tamaño no reutiliza la copia vieja.
            val version = try {
                contexto.packageManager.getPackageInfo(contexto.packageName, 0).lastUpdateTime
            } catch (e: Exception) {
                0L
            }
            val destino = File(contexto.filesDir, "chispa/$version/$ruta")
            if (destino.isFile && destino.length() > 0L) return destino
            try {
                contexto.assets.open(ruta).use { CacheFicheros.copiarAtomico(it, destino) }
                CacheFicheros.borrarVersionesViejas(File(contexto.filesDir, "chispa"), version.toString())
            } catch (e: java.io.IOException) {
                throw ErrorChispa("no existe el asset $ruta ni el fichero: ${e.message}", e)
            }
            return destino
        }

        private fun Motor.extraerL2ARuta(contexto: Context, modelo: File): String =
            CacheFicheros.rutaOnnxL2(this, contexto.cacheDir, modelo)
    }
}
