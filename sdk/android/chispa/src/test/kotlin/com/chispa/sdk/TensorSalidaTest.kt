package com.chispa.sdk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** float16/bfloat16 → float32 sin dispositivo ni ONNX Runtime (los bits de IEEE 754 binary16 son los de numpy `float16`). */
class TensorSalidaTest {
    @Test
    fun medioAFloat32ValoresConocidos() {
        assertEquals(1f, medioAFloat32(0x3C00.toShort()), 0f)
        assertEquals(-2f, medioAFloat32(0xC000.toShort()), 0f)
        assertEquals(0.5f, medioAFloat32(0x3800.toShort()), 0f)
        assertEquals(65504f, medioAFloat32(0x7BFF.toShort()), 0f) // el mayor finito
        assertEquals(0f, medioAFloat32(0x0000.toShort()), 0f)
        assertEquals(-0f, medioAFloat32(0x8000.toShort()), 0f)
        assertEquals(Math.scalb(1f, -24), medioAFloat32(0x0001.toShort()), 0f) // el menor subnormal
        assertEquals(Math.scalb(1023f, -24), medioAFloat32(0x03FF.toShort()), 0f)
        assertEquals(Float.POSITIVE_INFINITY, medioAFloat32(0x7C00.toShort()), 0f)
        assertEquals(Float.NEGATIVE_INFINITY, medioAFloat32(0xFC00.toShort()), 0f)
        assertTrue(medioAFloat32(0x7E00.toShort()).isNaN())
    }

    @Test
    fun mediosAFloat32ConservaLongitudYOrden() {
        val r = mediosAFloat32(shortArrayOf(0x3C00.toShort(), 0xC000.toShort(), 0x3800.toShort()))
        assertEquals(listOf(1f, -2f, 0.5f), r.toList())
    }

    @Test
    fun bfloat16AFloat32() {
        val r = bfloat16AFloat32(shortArrayOf(0x3F80.toShort(), 0xC000.toShort()))
        assertEquals(listOf(1f, -2f), r.toList())
    }
}
