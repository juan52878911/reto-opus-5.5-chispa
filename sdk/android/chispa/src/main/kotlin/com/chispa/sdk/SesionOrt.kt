package com.chispa.sdk

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.LongBuffer

/**
 * El ONNX int8 de L2 sobre ONNX Runtime Mobile. Entradas `input_ids` y `attention_mask` (int64, [1, n]); salida `S`
 * (float32, [1, K, d]). Como en el servidor, las llamadas a Run se serializan.
 */
class SesionOrt(rutaOnnx: String, proveedor: ProveedorOrt = PROVEEDOR_ORT_POR_DEFECTO) : SesionRanuras {
    private val entorno = OrtEnvironment.getEnvironment()
    private val sesion: OrtSession

    /** El proveedor con el que quedó la sesión (CPU si el pedido falló). */
    val proveedorEfectivo: ProveedorOrt

    init {
        val (s, p) = abrirConRespaldo(proveedor, "L2") { prov ->
            opcionesOrt(prov).use { entorno.createSession(rutaOnnx, it) }
        }
        sesion = s
        proveedorEfectivo = p
    }

    @Synchronized
    override fun ranuras(ids: LongArray): Ranuras {
        require(ids.isNotEmpty()) { "L2: mensaje sin tokens" }
        val n = ids.size.toLong()
        val forma = longArrayOf(1, n)
        val mascara = LongArray(ids.size) { 1L }
        return OnnxTensor.createTensor(entorno, LongBuffer.wrap(ids), forma).use { tid ->
            OnnxTensor.createTensor(entorno, LongBuffer.wrap(mascara), forma).use { tm ->
                sesion.run(mapOf("input_ids" to tid, "attention_mask" to tm)).use { res ->
                    val t = res.get("S").get() as OnnxTensor
                    val sh = t.info.shape // [1, K, d]
                    if (sh.size != 3 || sh[0] != 1L) throw ErrorChispa("L2: forma de S ${sh.toList()}")
                    val datos = leerComoFloat32(t, "L2") // float32, o float16/bfloat16 si el ONNX se exportó sin keep_io_types
                    if (datos.size.toLong() != sh[1] * sh[2]) throw ErrorChispa("L2: S trae ${datos.size} valores y su forma dice ${sh.toList()}")
                    Ranuras(datos, sh[1].toInt())
                }
            }
        }
    }

    override fun close() {
        sesion.close()
    }
}
