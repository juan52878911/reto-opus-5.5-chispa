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
data class SalidaCapa(
    val respuesta: String,
    val confianza: Double,
    val probs: Map<String, Double>,
    /** L2 puntuó con torres al vuelo (la pregunta no estaba en ESQUEMAS; lo marca el motor, `esquema_nuevo`): la cascada usa `tauL2EsquemaNuevo`. */
    val esquemaNuevo: Boolean = false,
    /**
     * Solo en `multi` (el motor manda `answers`): las opciones activas en el orden de la pregunta, vacía si ninguna; null en los
     * demás tipos. En `multi` [respuesta] es la activa más probable o "" y la [confianza] es la de la opción más dudosa.
     */
    val respuestas: List<String>? = null,
    /** L2c cayó a L2 base (sin cabeza para la pregunta, sin L0 o tipo ≠ choice): la cascada la corta con `tau_escalate_l2` y no con `tau_l2c`. */
    val respaldo: Boolean = false,
) {
    /** En `multi`, «ninguna activa» (respuesta vacía, [respuestas] vacía) es una opinión válida si hay confianza. */
    val opina: Boolean get() = confianza > 0 && (respuesta.isNotEmpty() || respuestas != null)

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
            val aj = o.optJSONArray("answers")
            val respuestas = if (aj == null) null else List(aj.length()) { aj.getString(it) }
            return SalidaCapa(
                o.optString("answer", ""), o.optDouble("conf", 0.0), probs,
                esquemaNuevo = o.optBoolean("esquema_nuevo", false), respuestas = respuestas,
            )
        }
    }
}

/**
 * La decisión final de una pregunta. [escalar] es true si ninguna capa llegó a su τ ([respuesta] es la pista).
 * [respuestas] solo se llena en `multi` (las activas; vacía si ninguna): [respuesta] es la más probable de ellas o "".
 */
data class Respuesta(
    val respuesta: String,
    val confianza: Double,
    val probs: Map<String, Double>,
    val capa: String,
    val escalar: Boolean,
    val ms: Double,
    val respuestas: List<String> = emptyList(),
    /**
     * Solo si [escalar] y se sabe por qué (mismo campo y valores que `escalate_reason` del servidor): [MotivoEscalada.SIN_OPINION],
     * [MotivoEscalada.BAJA_CONFIANZA] o [MotivoEscalada.SCORE_IDS_NO_VALIDOS]; null si no escaló o si escaló por el fallo de una capa.
     */
    val escalateReason: String? = null,
)

/** Valores de `escalate_reason` (`server/decide/cascada.go`). */
object MotivoEscalada {
    /** Ninguna capa opinó (sin error): el modelo no puede decidir ese esquema. */
    const val SIN_OPINION = "sin_opinion"

    /** Alguna capa opinó pero ninguna llegó a su τ. */
    const val BAJA_CONFIANZA = "baja_confianza"

    /** Sin opinión porque los ids de un `score` no son exactamente 1..K. */
    const val SCORE_IDS_NO_VALIDOS = "score_ids_no_validos"
}

/**
 * Los ids de un `score` valen si son exactamente 1..K: enteros canónicos (sin «01», «+1»), sin huecos ni repetidos, en cualquier
 * orden. Cualquier otra pregunta vale. Es la misma regla que aplica el motor Go en cada capa (que entonces no opina).
 */
fun scoreIdsValidos(pregunta: Pregunta): Boolean {
    if (pregunta.tipo != "score") return true
    val k = pregunta.opciones.size
    val vistos = BooleanArray(k)
    for (o in pregunta.opciones) {
        val n = o.id.toIntOrNull() ?: return false
        if (n.toString() != o.id || n < 1 || n > k || vistos[n - 1]) return false
        vistos[n - 1] = true
    }
    return k > 0
}

class ErrorChispa(mensaje: String, causa: Throwable? = null) : Exception(mensaje, causa)
