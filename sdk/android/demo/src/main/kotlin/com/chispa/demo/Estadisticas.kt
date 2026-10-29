package com.chispa.demo

import kotlin.math.ceil

/** Percentiles por rango más cercano (el mismo criterio que suele usarse para p99 de latencia). */
object Estadisticas {
    /** [p] en (0, 1]; [ordenado] ascendente y no vacío. */
    fun percentil(ordenado: DoubleArray, p: Double): Double {
        require(ordenado.isNotEmpty()) { "sin muestras" }
        val i = ceil(p * ordenado.size).toInt().coerceIn(1, ordenado.size) - 1
        return ordenado[i]
    }
}
