package com.chispa.sdk

import org.json.JSONArray
import org.json.JSONObject

/** Una opción de respuesta; [descripcion] ayuda a L1 (entra en el texto de la torre). */
data class Opcion(val id: String, val descripcion: String? = null)

/** Una pregunta, con la misma forma que la del servidor: `question`, `kind` y `options`. */
data class Pregunta(
    val texto: String,
    val opciones: List<Opcion>,
    val tipo: String = "choice",
) {
    fun toJson(): String {
        val ops = JSONArray()
        for (o in opciones) {
            val j = JSONObject().put("id", o.id)
            if (!o.descripcion.isNullOrEmpty()) j.put("description", o.descripcion)
            ops.put(j)
        }
        return JSONObject().put("question", texto).put("kind", tipo).put("options", ops).toString()
    }
}

/** Lo que dice una capa. [confianza] 0 significa «sin opinión». */
data class SalidaCapa(val respuesta: String, val confianza: Double, val probs: Map<String, Double>) {
    val opina: Boolean get() = confianza > 0 && respuesta.isNotEmpty()

    companion object {
        val SIN_OPINION = SalidaCapa("", 0.0, emptyMap())

        /** Lee el JSON de chispamovil (`{"ok":…,"opina":…,"answer":…,"conf":…,"probs":{…}}`). */
        fun desdeJson(js: String): SalidaCapa {
            val o = try {
                JSONObject(js)
            } catch (e: org.json.JSONException) {
                throw ErrorChispa("respuesta de la capa ilegible: ${e.message}")
            }
            if (!o.optBoolean("ok", false)) {
                throw ErrorChispa(o.optString("error", "error sin mensaje"))
            }
            if (!o.optBoolean("opina", false)) return SIN_OPINION
            val probs = LinkedHashMap<String, Double>()
            val pj = o.optJSONObject("probs")
            if (pj != null) {
                val ks = pj.keys()
                while (ks.hasNext()) {
                    val k = ks.next()
                    probs[k] = pj.getDouble(k)
                }
            }
            return SalidaCapa(o.optString("answer", ""), o.optDouble("conf", 0.0), probs)
        }
    }
}

/** La decisión final de una pregunta. [escalar] es true si ninguna capa llegó a su τ ([respuesta] es la pista). */
data class Respuesta(
    val respuesta: String,
    val confianza: Double,
    val probs: Map<String, Double>,
    val capa: String,
    val escalar: Boolean,
    val ms: Double,
)

class ErrorChispa(mensaje: String, causa: Throwable? = null) : Exception(mensaje, causa)
