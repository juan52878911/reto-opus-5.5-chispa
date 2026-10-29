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

    /** El fichero trae CONJ (la cabeza conjunta, L2c). */
    fun tieneConj(): Boolean = false

    /**
     * L2c: [simsJson] es la pregunta más `l0` (probabilidades de L0), `ranuras` (K×d aplanado) y `k`. Devuelve la
     * misma forma que las demás capas; sin opinión si no hay cabeza para la pregunta.
     */
    fun cabezaConjunta(simsJson: String): String = throw UnsupportedOperationException("sin CONJ")

    /**
     * Zero-shot de L2 (esquema que el `.chispa` no trae en ESQUEMAS): textos de pasaje («passage: pregunta · opción ·
     * descripción») cuyas torres hay que calcular, en el orden en que las espera [instalarTorresL2]; vacío si el motor
     * no sabe pedirlas (motor sin soporte, o ya las tiene). Las torres que calcule el propio motor no pasan por aquí:
     * basta con que [torresL2] diga true.
     */
    fun textosTorreL2(preguntaJson: String): List<String> = emptyList()

    /**
     * Entrega al motor las torres de [preguntaJson] ([n] vectores de d float32 little endian, uno por texto de
     * [textosTorreL2]); el motor las cuantiza y las cachea, así que la siguiente [torresL2] de ese esquema da true sin
     * volver a calcular. false si no las acepta.
     */
    fun instalarTorresL2(preguntaJson: String, torres: ByteArray, n: Int): Boolean = false

    fun tieneTokenizadorE5(): Boolean = false
    fun cargarTokenizadorE5(ruta: String): Unit = throw UnsupportedOperationException("sin tokenizador")

    /** Ids de e5 como int32 little endian (4 bytes por id), o null si no se cargó el tokenizador. */
    fun tokenizarE5(texto: String): ByteArray? = null
}

/** Una capa de la cascada. Devuelve [SalidaCapa.SIN_OPINION] si no tiene nada que decir; lanza si falla. */
interface Capa {
    val nombre: String
    fun decidir(texto: String, pregunta: Pregunta): SalidaCapa

    /** Como [decidir], con lo que dijeron las capas anteriores por nombre (L2c lee las probabilidades de L0). */
    fun decidir(texto: String, pregunta: Pregunta, previas: Map<String, SalidaCapa>): SalidaCapa =
        decidir(texto, pregunta)
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

/** El tokenizador de e5 del propio motor (runtime/tok en Go): no hace falta que la app aporte uno. */
class TokenizadorMotor(private val motor: Motor) : Tokenizador {
    override fun ids(texto: String): LongArray {
        val b = motor.tokenizarE5(texto) ?: throw ErrorChispa("el motor no tiene el tokenizador de e5")
        val buf = java.nio.ByteBuffer.wrap(b).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        return LongArray(b.size / 4) { buf.getInt(4 * it).toLong() }
    }
}

/**
 * El codificador de torres de opción (e5 de pasaje + cabeza de torre, un segundo ONNX): texto de pasaje → d floats.
 * Solo hace falta para esquemas nuevos cuando el motor no calcula las torres por su cuenta.
 */
fun interface CodificadorTorre {
    fun torre(texto: String): FloatArray
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
 * pregunta no opina y no llega a tokenizar ni a llamar a ONNX. Si el fichero trae CONJ y L0 ya dio probabilidades,
 * es L2c: las similitudes salen de las mismas ranuras y la cabeza conjunta (en Go, la del servidor) decide; sin
 * cabeza para la pregunta, cae a L2 a secas. Con [codificador], un esquema que ESQUEMAS no trae (zero-shot) recibe sus
 * torres al vuelo la primera vez ([torresAlVuelo]) y el motor las cachea; sin él, no opina, como antes.
 */
class CapaL2(
    private val motor: Motor,
    private val sesion: SesionRanuras,
    private val tokenizador: Tokenizador,
    private val codificador: CodificadorTorre? = null,
) : Capa {
    override val nombre = "L2"

    override fun decidir(texto: String, pregunta: Pregunta): SalidaCapa =
        decidir(texto, pregunta, emptyMap())

    override fun decidir(texto: String, pregunta: Pregunta, previas: Map<String, SalidaCapa>): SalidaCapa {
        val pj = pregunta.toJson()
        if (!motor.torresL2(pj) && !torresAlVuelo(pj)) return SalidaCapa.SIN_OPINION
        val ids = tokenizador.ids(texto)
        if (ids.isEmpty()) return SalidaCapa.SIN_OPINION
        val s = sesion.ranuras(ids)
        val l0 = previas["L0"]?.probs
        if (!l0.isNullOrEmpty() && motor.tieneConj()) {
            val c = SalidaCapa.desdeJson(motor.cabezaConjunta(entradaConj(pj, l0, s)))
            if (c.opina) return c
        }
        return SalidaCapa.desdeJson(motor.puntuarL2(pj, s.aBytes(), s.k))
    }

    private fun torresAlVuelo(preguntaJson: String): Boolean {
        val enc = codificador ?: return false
        val textos = motor.textosTorreL2(preguntaJson)
        if (textos.isEmpty()) return false
        val torres = textos.map { enc.torre(it) }
        val d = torres[0].size
        if (d == 0 || torres.any { it.size != d }) throw ErrorChispa("L2: el codificador de torres devolvió dimensiones distintas")
        val b = java.nio.ByteBuffer.allocate(4 * d * torres.size).order(java.nio.ByteOrder.LITTLE_ENDIAN)
        for (t in torres) for (x in t) b.putFloat(x)
        return motor.instalarTorresL2(preguntaJson, b.array(), torres.size)
    }

    private fun entradaConj(preguntaJson: String, l0: Map<String, Double>, s: Ranuras): String {
        val ranuras = org.json.JSONArray()
        for (x in s.datos) ranuras.put(x.toDouble()) // float → double es exacto; Go lo vuelve a float32
        val p = org.json.JSONObject()
        for ((k, v) in l0) p.put(k, v)
        return org.json.JSONObject(preguntaJson).put("l0", p).put("ranuras", ranuras).put("k", s.k).toString()
    }
}
