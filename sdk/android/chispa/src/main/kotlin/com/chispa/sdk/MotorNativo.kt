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
    override fun tauL2c(): Double = go.tauL2c()
    override fun tauL2EsquemaNuevo(): Double = go.tauL2EsquemaNuevo()
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

    override fun instalarTorresL2(preguntaJson: String, torres: ByteArray, n: Int): Boolean =
        go.instalarTorresL2(preguntaJson, torres, n.toLong())

    override fun tieneTorre(): Boolean = go.tieneTorre()
    override fun onnxTorre(): ByteArray? = go.onnxTorre()
    override fun idsPasaje(texto: String): ByteArray? = go.idsPasaje(texto)
    override fun tieneTokenizadorE5(): Boolean = go.tieneTokenizadorE5()
    override fun cargarTokenizadorE5(ruta: String) = go.cargarTokenizadorE5(ruta)
    override fun tokenizarE5(texto: String): ByteArray? = go.tokenizarE5(texto)
    override fun close() = go.cerrar()

    companion object {
        /** [soporte]: (λ de L1, λ de L2c) del encogimiento few-shot (`AbrirConSoporte`); null = `Abrir` del puente (λ de L1 = 4, L2 apagado). */
        fun abrir(ruta: String, soporte: Pair<Double, Double>? = null): MotorNativo = try {
            MotorNativo(if (soporte == null) Chispamovil.abrir(ruta) else Chispamovil.abrirConSoporte(ruta, soporte.first, soporte.second))
        } catch (e: Exception) {
            throw ErrorChispa("no se pudo abrir $ruta: ${e.message}", e)
        }
    }
}
