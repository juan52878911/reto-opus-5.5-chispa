package com.chispa.sdk

import ai.onnxruntime.OnnxJavaType
import ai.onnxruntime.OnnxTensor

/**
 * Un `.chispa` con el ONNX exportado en fp16 sin `keep_io_types` deja la salida como `tensor(float16)`: se lee como
 * float32 sea cual sea el tipo de la salida (float32, float16 o bfloat16), y cualquier otro tipo es un error claro.
 */
internal fun leerComoFloat32(t: OnnxTensor, nombre: String): FloatArray = when (val tipo = t.info.type) {
    OnnxJavaType.FLOAT -> FloatArray(t.floatBuffer.remaining()).also { t.floatBuffer.get(it) }
    OnnxJavaType.FLOAT16 -> mediosAFloat32(bitsDe(t))
    OnnxJavaType.BFLOAT16 -> bfloat16AFloat32(bitsDe(t))
    else -> throw ErrorChispa("$nombre: tipo de salida $tipo no soportado (se espera float32, float16 o bfloat16)")
}

private fun bitsDe(t: OnnxTensor): ShortArray = ShortArray(t.shortBuffer.remaining()).also { t.shortBuffer.get(it) }

internal fun mediosAFloat32(bits: ShortArray): FloatArray = FloatArray(bits.size) { medioAFloat32(bits[it]) }

internal fun bfloat16AFloat32(bits: ShortArray): FloatArray =
    FloatArray(bits.size) { java.lang.Float.intBitsToFloat((bits[it].toInt() and 0xFFFF) shl 16) }

/** IEEE 754 binary16 → float32 (con subnormales, ±Inf y NaN), sin `Float.float16ToFloat` (Java 20+). */
internal fun medioAFloat32(h: Short): Float {
    val x = h.toInt() and 0xFFFF
    val signo = (x ushr 15) shl 31
    val exp = (x ushr 10) and 0x1F
    val man = x and 0x3FF
    val bits = when {
        exp == 0x1F -> signo or 0x7F800000 or (man shl 13) // Inf o NaN
        exp == 0 && man == 0 -> signo // ±0
        exp == 0 -> { // subnormal: se normaliza
            var e = 127 - 15 + 1
            var m = man
            while ((m and 0x400) == 0) { m = m shl 1; e-- }
            signo or (e shl 23) or ((m and 0x3FF) shl 13)
        }
        else -> signo or ((exp + 127 - 15) shl 23) or (man shl 13)
    }
    return java.lang.Float.intBitsToFloat(bits)
}
