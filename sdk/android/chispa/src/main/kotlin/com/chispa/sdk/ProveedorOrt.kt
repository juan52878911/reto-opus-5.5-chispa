package com.chispa.sdk

import ai.onnxruntime.OrtSession

/** Proveedor de ejecución de ONNX Runtime para las sesiones de L2 y de la torre. Si el elegido falla, se cae a [CPU]. */
enum class ProveedorOrt { CPU, XNNPACK, NNAPI }

/** El proveedor por defecto en Android. */
val PROVEEDOR_ORT_POR_DEFECTO = ProveedorOrt.XNNPACK

/**
 * Crea unas `SessionOptions` con el [proveedor] (XNNPACK con `intra_op_num_threads` = [hilos], o NNAPI por defecto).
 * `addXnnpack` recibe `Map<String, String>` (los valores son cadenas); `addNnapi()` y `addXnnpack` lanzan `OrtException`
 * si el proveedor no está compilado en el AAR.
 */
internal fun opcionesOrt(proveedor: ProveedorOrt, hilos: Int = hilosPorDefecto()): OrtSession.SessionOptions {
    val o = OrtSession.SessionOptions()
    try {
        when (proveedor) {
            ProveedorOrt.CPU -> Unit
            ProveedorOrt.XNNPACK -> o.addXnnpack(mapOf("intra_op_num_threads" to hilos.toString()))
            ProveedorOrt.NNAPI -> o.addNnapi()
        }
    } catch (e: Throwable) {
        o.close()
        throw e
    }
    return o
}

internal fun hilosPorDefecto(): Int = Runtime.getRuntime().availableProcessors().coerceIn(1, 4)

internal fun avisarRespaldoOrt(mensaje: String, e: Throwable) {
    try {
        android.util.Log.w("Chispa", mensaje, e)
    } catch (_: RuntimeException) {
    }
}

/**
 * Abre con [proveedor] y, si [crear] lanza, lo avisa y reintenta con CPU. Devuelve la sesión y el proveedor que de verdad
 * quedó. Si CPU también falla, la excepción sube.
 */
internal fun <T> abrirConRespaldo(
    proveedor: ProveedorOrt,
    etiqueta: String,
    aviso: (String, Throwable) -> Unit = ::avisarRespaldoOrt,
    crear: (ProveedorOrt) -> T,
): Pair<T, ProveedorOrt> {
    if (proveedor == ProveedorOrt.CPU) return crear(ProveedorOrt.CPU) to ProveedorOrt.CPU
    return try {
        crear(proveedor) to proveedor
    } catch (e: Exception) {
        aviso("$etiqueta: ORT con $proveedor falló (${e.message}); sigo con CPU", e)
        crear(ProveedorOrt.CPU) to ProveedorOrt.CPU
    }
}
