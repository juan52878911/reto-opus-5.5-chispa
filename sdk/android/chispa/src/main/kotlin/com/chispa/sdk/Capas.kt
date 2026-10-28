package com.chispa.sdk

/**
 * Lo que el SDK necesita del motor nativo (gomobile). Es una interfaz para poder probar la cascada en la JVM con un
 * motor falso; [MotorNativo] es la implementación real.
 */
interface Motor : AutoCloseable {
    /** Capas presentes en el fichero, p. ej. ["L0","L1","L2"]. */
    fun capas(): List<String>
    fun tieneCalib(): Boolean
    fun tauEscalate(): Double
    fun decidirL0(texto: String, preguntaJson: String): String
    fun decidirL1(texto: String, preguntaJson: String): String
    fun torresL2(preguntaJson: String): Boolean
    /** [ranuras]: K×d float32 little endian. */
    fun puntuarL2(preguntaJson: String, ranuras: ByteArray, k: Int): String
    fun extraerL2(destino: String)
}

/** Una capa de la cascada. Devuelve [SalidaCapa.SIN_OPINION] si no tiene nada que decir; lanza si falla. */
interface Capa {
    val nombre: String
    fun decidir(texto: String, pregunta: Pregunta): SalidaCapa
}

class CapaL0(private val motor: Motor) : Capa {
    override val nombre = "L0"
    override fun decidir(texto: String, pregunta: Pregunta): SalidaCapa =
        SalidaCapa.desdeJson(motor.decidirL0(texto, pregunta.toJson()))
}

class CapaL1(private val motor: Motor) : Capa {
    override val nombre = "L1"
    override fun decidir(texto: String, pregunta: Pregunta): SalidaCapa =
        SalidaCapa.desdeJson(motor.decidirL1(texto, pregunta.toJson()))
}

/** Convierte un texto en los ids del tokenizador de e5 (con «query: » delante, tokens especiales y recorte a 128). */
fun interface Tokenizador {
    fun ids(texto: String): LongArray
}

/** El ONNX de L2: ids → S ∈ R^{K×d}, aplanado por filas. */
interface SesionRanuras : AutoCloseable {
    fun ranuras(ids: LongArray): Ranuras
}

class Ranuras(val datos: FloatArray, val k: Int) {
    init {
        require(k > 0 && datos.size % k == 0) { "ranuras: ${datos.size} valores no caben en $k filas" }
    }

    /** float32 little endian, que es lo que espera `PuntuarL2`. */
    fun aBytes(): ByteArray {
        val b = java.nio.ByteBuffer.allocate(4 * datos.size).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        b.asFloatBuffer().put(datos)
        return b.array()
    }
}

/**
 * L2: ranuras del mensaje (ONNX Runtime) contra las torres de ESQUEMAS. Si el fichero no trae torres para la
 * pregunta no opina y no llega a tokenizar ni a llamar a ONNX.
 */
class CapaL2(
    private val motor: Motor,
    private val sesion: SesionRanuras,
    private val tokenizador: Tokenizador,
) : Capa {
    override val nombre = "L2"
    override fun decidir(texto: String, pregunta: Pregunta): SalidaCapa {
        val pj = pregunta.toJson()
        if (!motor.torresL2(pj)) return SalidaCapa.SIN_OPINION
        val ids = tokenizador.ids(texto)
        if (ids.isEmpty()) return SalidaCapa.SIN_OPINION
        val s = sesion.ranuras(ids)
        return SalidaCapa.desdeJson(motor.puntuarL2(pj, s.aBytes(), s.k))
    }
}
