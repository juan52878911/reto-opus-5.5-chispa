package com.chispa.demo

import org.junit.Assert.assertEquals
import org.junit.Test

class EstadisticasTest {
    private val cien = DoubleArray(100) { (it + 1).toDouble() }

    @Test fun percentiles() {
        assertEquals(50.0, Estadisticas.percentil(cien, 0.50), 0.0)
        assertEquals(95.0, Estadisticas.percentil(cien, 0.95), 0.0)
        assertEquals(99.0, Estadisticas.percentil(cien, 0.99), 0.0)
    }

    @Test fun unaMuestra() {
        assertEquals(7.0, Estadisticas.percentil(doubleArrayOf(7.0), 0.99), 0.0)
    }
}
