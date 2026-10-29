package com.chispa.sdk

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.LongBuffer

/**
 * El ONNX de la torre (sección TORR) sobre ONNX Runtime Mobile, abierto desde sus bytes. Entradas `input_ids` y
 * `attention_mask` (int64, [1, n]); salida `h` (float32, [1, d]). Las llamadas a Run se serializan.
 */
class SesionTorreOrt(onnx: ByteArray, proveedor: ProveedorOrt = PROVEEDOR_ORT_POR_DEFECTO) : SesionTorre {
    private val entorno = OrtEnvironment.getEnvironment()
    private val sesion: OrtSession

    /** El proveedor con el que quedó la sesión (CPU si el pedido falló). */
    val proveedorEfectivo: ProveedorOrt

    init {
        val (s, p) = abrirConRespaldo(proveedor, "torre") { prov ->
            opcionesOrt(prov).use { entorno.createSession(onnx, it) }
        }
        sesion = s
        proveedorEfectivo = p
    }

    @Synchronized
    override fun embeber(ids: LongArray): FloatArray {
        require(ids.isNotEmpty()) { "torre: texto sin tokens" }
        val forma = longArrayOf(1, ids.size.toLong())
        val mascara = LongArray(ids.size) { 1L }
        return OnnxTensor.createTensor(entorno, LongBuffer.wrap(ids), forma).use { tid ->
            OnnxTensor.createTensor(entorno, LongBuffer.wrap(mascara), forma).use { tm ->
                sesion.run(mapOf("input_ids" to tid, "attention_mask" to tm)).use { res ->
                    val t = res.get("h").get() as OnnxTensor
                    val sh = t.info.shape // [1, d]
                    if (sh.size != 2 || sh[0] != 1L) throw ErrorChispa("torre: forma de h ${sh.toList()}")
                    val h = FloatArray(t.floatBuffer.remaining())
                    t.floatBuffer.get(h)
                    h
                }
            }
        }
    }

    override fun close() {
        sesion.close()
    }
}
