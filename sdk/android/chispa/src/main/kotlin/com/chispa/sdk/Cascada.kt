package com.chispa.sdk

private const val ETIQUETA_LOG = "Chispa"

/** Registro por defecto de un error de capa. Fuera de Android (tests en la JVM) `Log` lanza y se ignora. */
internal fun registrarErrorCapa(capa: String, e: Throwable) {
    try {
        android.util.Log.w(ETIQUETA_LOG, "la capa $capa falló: ${e.message}", e)
    } catch (_: RuntimeException) {
    }
}

/**
 * Una capa con su umbral: se acepta su respuesta si su confianza es ≥ [tau]. La confianza ya la calcula el motor por tipo:
 * la top-1 en choice/noul/score y la de la opción más dudosa en multi (todas las decisiones de la capa deben pasar τ).
 */
class CapaConTau(
    val capa: Capa,
    val tau: Double,
    /** τ de la capa cuando su salida trae [SalidaCapa.esquemaNuevo]; null = el mismo [tau]. */
    val tauEsquemaNuevo: Double? = null,
)

/** τ por defecto de cada capa (los de `ConfigPorDefecto` del servidor). Con CALIB, L1 y L2 usan `tau_escalate`. */
object TauPorDefecto {
    const val L0 = 0.80
    const val L1 = 0.80
    const val L2 = 0.70

    fun de(nombre: String): Double = when (nombre) {
        "L0" -> L0
        "L1" -> L1
        else -> L2
    }
}

/**
 * La cascada de `server/decide/cascada.go`: pasa por las capas en orden mientras la confianza top-1 sea < τ (cada capa recibe lo que
 * dijeron las anteriores: L2c usa las probabilidades de L0). Si una
 * falla o no opina, sigue con la siguiente. Si ninguna alcanza su τ, escala: la respuesta es la de mayor confianza
 * vista (pista para quien reciba la escalada) y la capa es [CAPA_ESCALAR], como `CapaEscalar` del servidor.
 */
class Cascada(
    private val capas: List<CapaConTau>,
    private val reloj: () -> Long = System::nanoTime,
    /** Recibe el nombre de la capa y el error cuando una capa lanza (por defecto, `Log.w`). */
    private val alErrorCapa: (String, Throwable) -> Unit = ::registrarErrorCapa,
) {
    init {
        require(capas.isNotEmpty()) { "la cascada necesita al menos una capa" }
    }

    fun decidir(texto: String, pregunta: Pregunta): Respuesta {
        val t0 = reloj()
        fun ms() = (reloj() - t0) / 1e6
        var mejor = SalidaCapa.SIN_OPINION
        val previas = LinkedHashMap<String, SalidaCapa>()
        for (c in capas) {
            val r = try {
                c.capa.decidir(texto, pregunta, previas)
            } catch (e: Exception) {
                try {
                    alErrorCapa(c.capa.nombre, e)
                } catch (_: Throwable) {
                    // registrar nunca debe romper la decisión
                }
                SalidaCapa.SIN_OPINION
            }
            previas[c.capa.nombre] = r
            if (r.confianza > mejor.confianza) mejor = r
            val tau = if (r.esquemaNuevo && c.tauEsquemaNuevo != null) c.tauEsquemaNuevo else c.tau
            if (r.opina && r.confianza >= tau) {
                return Respuesta(r.respuesta, r.confianza, r.probs, c.capa.nombre, false, ms(), r.respuestas.orEmpty())
            }
        }
        return Respuesta(mejor.respuesta, mejor.confianza, mejor.probs, CAPA_ESCALAR, true, ms(), mejor.respuestas.orEmpty())
    }

    companion object {
        /** La capa de una respuesta escalada (`CapaEscalar` en `server/decide/cascada.go`). */
        const val CAPA_ESCALAR = "escalar"

        /**
         * Arma la cascada con las capas del [motor] (L0 y L1 si el fichero las trae) y L2 si además hay [l2].
         * Con CALIB, el τ de L1 y L2 es su `tau_escalate`; con CONJ (L2c) el de L2 es `tau_l2c` si el fichero lo trae
         * (`aplicarTauL2c` del servidor). Con `tau_l2_esquema_nuevo`, L2 lo usa en lugar de ese τ cuando sus torres salieron al vuelo.
         */
        fun armar(
            motor: Motor,
            l2: CapaL2? = null,
            tauL0: Double = TauPorDefecto.L0,
            alErrorCapa: (String, Throwable) -> Unit = ::registrarErrorCapa,
        ): Cascada {
            val presentes = motor.capas()
            val tauCalib = if (motor.tieneCalib()) motor.tauEscalate() else null
            val capas = ArrayList<CapaConTau>()
            if ("L0" in presentes) capas.add(CapaConTau(CapaL0(motor), tauL0))
            if ("L1" in presentes) capas.add(CapaConTau(CapaL1(motor), tauCalib ?: TauPorDefecto.L1))
            val tauL2c = if (motor.tieneConj()) motor.tauL2c().takeIf { it >= 0 } else null
            if ("L2" in presentes && l2 != null) {
                val tauNuevo = motor.tauL2EsquemaNuevo().takeIf { it >= 0 }
                capas.add(CapaConTau(l2, tauL2c ?: tauCalib ?: TauPorDefecto.L2, tauNuevo))
            }
            if (capas.isEmpty()) throw ErrorChispa("el fichero no trae ninguna capa utilizable (capas: $presentes)")
            return Cascada(capas, alErrorCapa = alErrorCapa)
        }
    }
}
