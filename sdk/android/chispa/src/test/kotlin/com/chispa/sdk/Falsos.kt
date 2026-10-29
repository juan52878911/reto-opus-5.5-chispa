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
    var conj: Boolean = false,
    var cabeza: () -> String = { json(null, 0.0) },
    var idsE5: ByteArray? = null,
    var tauConj: Double = -1.0,
    var hashes: Map<Int, String> = emptyMap(),
) : Motor {
    /** Qué hace [extraerL2]: escribe en el destino que se le da (por defecto, nada). */
    var alExtraer: (String) -> Unit = {}
    var extracciones = 0

    /** false = [instalarTorresL2] rechaza las torres (y no las cachea). */
    var aceptaTorres = true

    var ultimoSimsJson: String? = null
    val llamadas = ArrayList<String>()
    var ultimasRanuras: ByteArray? = null
    var ultimoK = -1
    var cerrado = false

    /** Zero-shot: mientras [torres] sea false el motor pide estos textos; al instalarlas, [torres] pasa a true (caché). */
    var textosTorre: List<String> = emptyList()
    var torresInstaladas: ByteArray? = null
    var nInstaladas = 0

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
    override fun textosTorreL2(preguntaJson: String) = if (torres) emptyList() else textosTorre
    override fun instalarTorresL2(preguntaJson: String, torres: ByteArray, n: Int): Boolean {
        llamadas.add("TORRES")
        if (!aceptaTorres) return false
        torresInstaladas = torres; nInstaladas = n; this.torres = true; return true
    }

    override fun puntuarL2(preguntaJson: String, ranuras: ByteArray, k: Int): String {
        llamadas.add("L2"); ultimasRanuras = ranuras; ultimoK = k; return l2()
    }

    override fun extraerL2(destino: String) {
        extracciones++; alExtraer(destino)
    }

    override fun tauL2c() = tauConj
    override fun hashSeccion(tipo: Int) = hashes[tipo] ?: ""
    override fun tieneConj() = conj
    override fun cabezaConjunta(simsJson: String): String {
        llamadas.add("CONJ"); ultimoSimsJson = simsJson; return cabeza()
    }

    /** TORR: [onnxDeTorre] no nulo = el fichero la trae; [idsDePasaje] da los ids (int32 LE) de cada texto de torre. */
    var onnxDeTorre: ByteArray? = null
    var idsDePasaje: (String) -> ByteArray? = { null }
    override fun tieneTorre() = onnxDeTorre != null
    override fun onnxTorre() = onnxDeTorre
    override fun idsPasaje(texto: String) = idsDePasaje(texto)

    override fun tieneTokenizadorE5() = idsE5 != null
    override fun tokenizarE5(texto: String) = idsE5
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

/** Una pregunta con un esquema que ningún `.chispa` trae. */
val PREGUNTA_NUEVA = Pregunta(
    "¿Qué tipo de incidencia es?",
    listOf(Opcion("fraude", "cargo no reconocido"), Opcion("tarjeta", "tarjeta bloqueada o perdida")),
)
