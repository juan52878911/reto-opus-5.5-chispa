package com.chispa.sdk

import org.json.JSONObject

/**
 * Qué hacer con un texto más largo que el truncado de L1 (`max_tokens` del modelo) y de L2 (`chispa.consulta.max_len`,
 * 128 por defecto). Mismo objeto que `texto_largo` de la config del servidor; el valor por defecto es [CABEZA]: los primeros
 * tokens, lo de siempre (bit a bit).
 *
 * - `cabeza`: los primeros tokens.
 * - `cabeza_cola`: la mitad de los primeros y la mitad de los últimos.
 * - `trozos`: ventanas de [solape] tokens compartidos, como mucho [maxTrozos] (0 = 8, máximo 64); cada una se decide y se
 *   agregan las probabilidades por opción con [agregacion] (`max` o `media`).
 *
 * [ventanaL1] (0 = `max_tokens` del modelo) es la ventana de L1 con `cabeza_cola` y `trozos`; con `cabeza` no tiene efecto.
 * El motor Go valida los valores al abrir y lanza [ErrorChispa] si no valen.
 */
data class TextoLargo(
    val estrategia: String = "cabeza",
    val agregacion: String = "media",
    val solape: Int = 0,
    val maxTrozos: Int = 0,
    val ventanaL1: Int = 0,
) {
    internal fun toJson(): String = JSONObject()
        .put("estrategia", estrategia).put("agregacion", agregacion).put("solape", solape)
        .put("max_trozos", maxTrozos).put("ventana_l1", ventanaL1).toString()

    companion object {
        val CABEZA = TextoLargo()
    }
}
