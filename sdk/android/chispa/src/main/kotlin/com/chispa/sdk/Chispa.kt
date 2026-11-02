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

    /**
     * Por qué el modelo cargó degradado, o "" si no: «texto_torre_inconsistente» = el `.chispa` trae TORR pero su META.texto_torre
     * no coincide; no hay torres al vuelo y L2 solo decide los esquemas de ESQUEMAS (reentrenar con `chispa train`).
     */
    fun torreAlVueloMotivo(): String = motor.torreAlVueloMotivo()

    /** Avisos no fatales de la apertura del modelo, uno por línea ("" si no hubo). */
    fun avisos(): String = motor.avisos()

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
         * [lambdaSoporteL1]/[lambdaSoporteL2]: λ del soporte few-shot (`AbrirConSoporte`, mismo nombre y semántica que
         * `l1_shrinkage_lambda`/`l2_shrinkage_lambda` del servidor). [lambdaSoporteL1] vale [SOPORTE_POR_DEFECTO] (`Double.NaN`)
         * si no se pasa: lo decide el motor (`Abrir` del puente: λ = 4 solo si el fichero trae `l1_lambda_calib`; un `.chispa` viejo con SOPL1 y sin él
         * queda con L1 apagado). `null` es el apagado explícito de L1; un número es explícito (se aplica tal cual). [lambdaSoporteL2] nulo = apagado (sin default).
         * Si se pasa [lambdaSoporteL2] con L1 por defecto, el puente solo ofrece λ explícitos: L1 queda en [LAMBDA_SOPORTE_L1_POR_DEFECTO] (4,0) aunque el fichero sea viejo.
         * 0 = solo ejemplos, `Double.POSITIVE_INFINITY` = solo descripción (ya no apaga); negativo o NaN lanza [ErrorChispa].
         * Sin sección SOPL1 en el fichero el default no tiene efecto.
         * [textoLargo]: qué hacer con un texto que pasa del truncado de L1 y L2 ([TextoLargo]: `cabeza_cola` o `trozos` con agregación `max`/`media`);
         * null (por defecto) = los primeros tokens, lo de siempre. Con `trozos`, L2 corre ONNX en cada ventana (como mucho `maxTrozos`).
         */
        fun abrir(
            contexto: Context,
            rutaModelo: String,
            tokenizador: Tokenizador? = null,
            rutaTokenizador: String? = null,
            codificadorTorres: CodificadorTorre? = null,
            alErrorCapa: (String, Throwable) -> Unit = ::registrarErrorCapa,
            proveedorOrt: ProveedorOrt = PROVEEDOR_ORT_POR_DEFECTO,
            lambdaSoporteL1: Double? = SOPORTE_POR_DEFECTO,
            lambdaSoporteL2: Double? = null,
            textoLargo: TextoLargo? = null,
        ): Chispa {
            val fichero = resolver(contexto, rutaModelo)
            val motor = MotorNativo.abrir(fichero.absolutePath, soporteDe(lambdaSoporteL1, lambdaSoporteL2), textoLargo)
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

        /** λ de L1 por defecto (`chispamovil.SoporteL1PorDefecto`; G.8b: massive 0,395 vs 0,266, inyecciones 0,740 vs 0,326, hatecheck 0,492 vs 0,224, JevBench 0,379 vs 0,398). */
        const val LAMBDA_SOPORTE_L1_POR_DEFECTO = 4.0

        /** Centinela de «λ por defecto: que decida el motor» (`Double.NaN`; compara con `isNaN()`, nunca con `==`). Solo vale para [abrir]`.lambdaSoporteL1`. */
        val SOPORTE_POR_DEFECTO: Double = Double.NaN

        /** `chispamovil.SoporteApagado`: el λ negativo que apaga el encogimiento en el puente (que no tiene opcionales). */
        internal const val LAMBDA_APAGADO = -1.0

        /**
         * (λL1, λL2) para `AbrirConSoporte`, o null si hay que llamar a `Abrir` del puente (L1 [SOPORTE_POR_DEFECTO] y L2 nulo: λ de L1 según el fichero).
         * Un λ nulo es apagado (LAMBDA_APAGADO); L1 por defecto con L2 explícito se manda como [LAMBDA_SOPORTE_L1_POR_DEFECTO] explícito.
         */
        internal fun soporteDe(l1: Double?, l2: Double?): Pair<Double, Double>? {
            val l1Defecto = l1 != null && l1.isNaN()
            // Un λ negativo o NaN es error (como el servidor con `l1_shrinkage_lambda < 0`); el NaN de L1 es el centinela por defecto.
            for ((nombre, l) in listOf("lambdaSoporteL1" to l1, "lambdaSoporteL2" to l2)) {
                if (l != null && (l < 0 || (l.isNaN() && !(nombre == "lambdaSoporteL1" && l1Defecto)))) throw ErrorChispa("$nombre inválido ($l): debe ser nulo (apagado) o >= 0")
            }
            if (l1Defecto) return if (l2 == null) null else Pair(LAMBDA_SOPORTE_L1_POR_DEFECTO, l2)
            return Pair(l1 ?: LAMBDA_APAGADO, l2 ?: LAMBDA_APAGADO)
        }

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
