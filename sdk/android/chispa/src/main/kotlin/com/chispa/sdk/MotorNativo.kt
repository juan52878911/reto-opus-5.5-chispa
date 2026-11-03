package com.chispa.sdk

import org.json.JSONArray
import chispamovil.Chispa as ChispaGo
import chispamovil.Chispamovil

/** El motor real: el AAR de `gomobile bind` sobre sdk/movil/chispamovil. */
class MotorNativo private constructor(private val go: ChispaGo) : Motor {
    override fun capas(): List<String> {
        val a = JSONArray(go.capas())
        return List(a.length()) { a.getString(it) }
    }

    override fun tieneCalib(): Boolean = go.tieneCalib()
    override fun tauEscalate(): Double = go.tauEscalate()
    override fun tauEscalateL2(): Double = go.tauEscalateL2()
    override fun tauL2c(): Double = go.tauL2c()
    override fun tauL2EsquemaNuevo(): Double = go.tauL2EsquemaNuevo()

    /** `true` = sin τ propio para esquemas nuevos (ni el de CALIB ni 0,846); llamar antes de construir la cascada. */
    fun sinTauL2EsquemaNuevo(apagar: Boolean) = go.sinTauEsquemaNuevo(apagar)

    override fun hashSeccion(tipo: Int): String = go.hashSeccion(tipo.toLong())
    override fun decidirL0(texto: String, preguntaJson: String): String = go.decidirL0(texto, preguntaJson)
    override fun decidirL1(texto: String, preguntaJson: String): String = go.decidir(texto, preguntaJson)
    override fun torresL2(preguntaJson: String): Boolean = go.torresL2(preguntaJson)
    override fun puntuarL2(preguntaJson: String, ranuras: ByteArray, k: Int): String =
        go.puntuarL2(preguntaJson, ranuras, k.toLong())

    override fun extraerL2(destino: String) = go.extraerL2(destino)
    override fun tieneConj(): Boolean = go.tieneConj()
    override fun cabezaConjunta(simsJson: String): String = go.cabezaConjunta(simsJson)
    override fun textosTorreL2(preguntaJson: String): List<String> {
        val a = JSONArray(go.textosTorreL2(preguntaJson))
        return List(a.length()) { a.getString(it) }
    }

    override fun textoTorre(): String = go.textoTorre()
    override fun torreAlVueloMotivo(): String = go.torreAlVueloMotivo()
    override fun avisos(): String = go.avisos()

    override fun instalarTorresL2(preguntaJson: String, torres: ByteArray, n: Int): Boolean =
        go.instalarTorresL2(preguntaJson, torres, n.toLong())

    override fun instalarTorresL2Motivo(preguntaJson: String, torres: ByteArray, n: Int): String =
        go.instalarTorresL2Motivo(preguntaJson, torres, n.toLong())

    override fun tieneTorre(): Boolean = go.tieneTorre()
    override fun onnxTorre(): ByteArray? = go.onnxTorre()
    override fun idsPasaje(texto: String): ByteArray? = go.idsPasaje(texto)
    override fun tieneTokenizadorE5(): Boolean = go.tieneTokenizadorE5()
    override fun cargarTokenizadorE5(ruta: String) = go.cargarTokenizadorE5(ruta)
    override fun tokenizarE5(texto: String): ByteArray? = go.tokenizarE5(texto)
    override fun trozosE5(texto: String): ByteArray? = go.trozosE5(texto)
    override fun puntuarL2Trozos(preguntaJson: String, ranuras: ByteArray, ksJson: String): String =
        go.puntuarL2Trozos(preguntaJson, ranuras, ksJson)

    /** Textos que pasaron del truncado de L1 o de la consulta de L2 desde que se abrió (`TextoLargoSuperados`). */
    fun textoLargoSuperados(): Long = go.textoLargoSuperados()
    override fun close() = go.cerrar()

    companion object {
        /** [soporte]: (λ de L1, λ de L2c) del encogimiento few-shot (`AbrirConSoporte`); null = `Abrir` del puente (λ de L1 según el fichero, L2 apagado). [textoLargo]: estrategia para textos que pasan del truncado (`AbrirConTextoLargo`); null = cabeza, sin llamar a ese constructor. */
        fun abrir(ruta: String, soporte: Pair<Double, Double>? = null, textoLargo: TextoLargo? = null): MotorNativo = try {
            MotorNativo(
                when {
                    // `AbrirConTextoLargo` con explicito=false es `Abrir` (los λ se ignoran)
                    textoLargo != null -> Chispamovil.abrirConTextoLargo(ruta, soporte?.first ?: 0.0, soporte?.second ?: 0.0, soporte != null, textoLargo.toJson())
                    soporte == null -> Chispamovil.abrir(ruta)
                    else -> Chispamovil.abrirConSoporte(ruta, soporte.first, soporte.second)
                },
            )
        } catch (e: Exception) {
            throw ErrorChispa("no se pudo abrir $ruta: ${e.message}", e)
        }
    }
}
