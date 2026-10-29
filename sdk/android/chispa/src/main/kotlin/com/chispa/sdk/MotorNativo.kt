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
    override fun decidirL0(texto: String, preguntaJson: String): String = go.decidirL0(texto, preguntaJson)
    override fun decidirL1(texto: String, preguntaJson: String): String = go.decidir(texto, preguntaJson)
    override fun torresL2(preguntaJson: String): Boolean = go.torresL2(preguntaJson)
    override fun puntuarL2(preguntaJson: String, ranuras: ByteArray, k: Int): String =
        go.puntuarL2(preguntaJson, ranuras, k.toLong())

    override fun extraerL2(destino: String) = go.extraerL2(destino)
    override fun tieneConj(): Boolean = go.tieneConj()
    override fun cabezaConjunta(simsJson: String): String = go.cabezaConjunta(simsJson)
    override fun tieneTokenizadorE5(): Boolean = go.tieneTokenizadorE5()
    override fun cargarTokenizadorE5(ruta: String) = go.cargarTokenizadorE5(ruta)
    override fun tokenizarE5(texto: String): ByteArray? = go.tokenizarE5(texto)
    override fun close() = go.cerrar()

    companion object {
        fun abrir(ruta: String): MotorNativo = try {
            MotorNativo(Chispamovil.abrir(ruta))
        } catch (e: Exception) {
            throw ErrorChispa("no se pudo abrir $ruta: ${e.message}", e)
        }
    }
}
