package com.chispa.sdk

import org.json.JSONObject

/** JSON de una capa, con la forma de chispamovil. */
fun json(respuesta: String?, conf: Double, vararg probs: Pair<String, Double>): String {
    if (respuesta == null) return """{"ok":true,"opina":false,"answer":"","conf":0,"probs":{}}"""
    val p = JSONObject()
    for ((k, v) in probs) p.put(k, v)
    return JSONObject().put("ok", true).put("opina", true).put("answer", respuesta).put("conf", conf)
        .put("probs", p).toString()
}

/** Un motor falso: cada capa devuelve lo que se le diga y se anotan las llamadas. */
class MotorFalso(
    var presentes: List<String> = listOf("L0", "L1", "L2"),
    var calib: Boolean = false,
    var tau: Double = 0.0,
    var l0: () -> String = { json(null, 0.0) },
    var l1: () -> String = { json(null, 0.0) },
    var torres: Boolean = true,
    var l2: () -> String = { json(null, 0.0) },
) : Motor {
    val llamadas = ArrayList<String>()
    var ultimasRanuras: ByteArray? = null
    var ultimoK = -1
    var cerrado = false

    override fun capas() = presentes
    override fun tieneCalib() = calib
    override fun tauEscalate() = tau
    override fun decidirL0(texto: String, preguntaJson: String): String {
        llamadas.add("L0"); return l0()
    }

    override fun decidirL1(texto: String, preguntaJson: String): String {
        llamadas.add("L1"); return l1()
    }

    override fun torresL2(preguntaJson: String) = torres
    override fun puntuarL2(preguntaJson: String, ranuras: ByteArray, k: Int): String {
        llamadas.add("L2"); ultimasRanuras = ranuras; ultimoK = k; return l2()
    }

    override fun extraerL2(destino: String) {}
    override fun close() {
        cerrado = true
    }
}

class SesionFalsa(val devuelve: Ranuras = Ranuras(floatArrayOf(1f, 2f, 3f, 4f, 5f, 6f), 2)) : SesionRanuras {
    var llamadas = 0
    var cerrada = false
    var ultimosIds: LongArray? = null
    override fun ranuras(ids: LongArray): Ranuras {
        llamadas++; ultimosIds = ids; return devuelve
    }

    override fun close() {
        cerrada = true
    }
}

val PREGUNTA = Pregunta(
    "¿Qué quiere el cliente?",
    listOf(Opcion("compra", "quiere comprar"), Opcion("soporte", "pide ayuda"), Opcion("saludo")),
)
