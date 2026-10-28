package com.chispa.sdk

/** Una capa con su umbral: se acepta su respuesta si su confianza top-1 es ≥ [tau]. */
class CapaConTau(val capa: Capa, val tau: Double)

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
 * La cascada de `server/decide/cascada.go`: pasa por las capas en orden mientras la confianza top-1 sea < τ. Si una
 * falla o no opina, sigue con la siguiente. Si ninguna alcanza su τ, escala: la respuesta es la de mayor confianza
 * vista (pista para quien reciba la escalada) y la capa es la última de la cascada.
 */
class Cascada(private val capas: List<CapaConTau>, private val reloj: () -> Long = System::nanoTime) {
    init {
        require(capas.isNotEmpty()) { "la cascada necesita al menos una capa" }
    }

    fun decidir(texto: String, pregunta: Pregunta): Respuesta {
        val t0 = reloj()
        fun ms() = (reloj() - t0) / 1e6
        var mejor = SalidaCapa.SIN_OPINION
        for (c in capas) {
            val r = try {
                c.capa.decidir(texto, pregunta)
            } catch (e: Exception) {
                SalidaCapa.SIN_OPINION
            }
            if (r.confianza > mejor.confianza) mejor = r
            if (r.opina && r.confianza >= c.tau) {
                return Respuesta(r.respuesta, r.confianza, r.probs, c.capa.nombre, false, ms())
            }
        }
        return Respuesta(mejor.respuesta, mejor.confianza, mejor.probs, capas.last().capa.nombre, true, ms())
    }

    companion object {
        /**
         * Arma la cascada con las capas del [motor] (L0 y L1 si el fichero las trae) y L2 si además hay [l2].
         * Con CALIB, el τ de L1 y L2 es su `tau_escalate`.
         */
        fun armar(motor: Motor, l2: CapaL2? = null, tauL0: Double = TauPorDefecto.L0): Cascada {
            val presentes = motor.capas()
            val tauCalib = if (motor.tieneCalib()) motor.tauEscalate() else null
            val capas = ArrayList<CapaConTau>()
            if ("L0" in presentes) capas.add(CapaConTau(CapaL0(motor), tauL0))
            if ("L1" in presentes) capas.add(CapaConTau(CapaL1(motor), tauCalib ?: TauPorDefecto.L1))
            if ("L2" in presentes && l2 != null) capas.add(CapaConTau(l2, tauCalib ?: TauPorDefecto.L2))
            if (capas.isEmpty()) throw ErrorChispa("el fichero no trae ninguna capa utilizable (capas: $presentes)")
            return Cascada(capas)
        }
    }
}
