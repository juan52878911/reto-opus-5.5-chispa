package com.chispa.demo

import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.util.Log
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Salida del resultado: logcat (etiqueta fija), carpeta externa de la app (adb pull) y Descargas (Android 10+). */
object Exportar {
    private const val TROZO = 3000 // logcat corta las líneas hacia 4 KB

    /** Una línea por escenario y el JSON completo en trozos `RESULTADO_JSON i/n <texto>`. */
    fun logcat(res: ResultadoMedida) {
        for (e in res.escenarios) Log.i(Medidor.ETIQUETA, e.linea())
        val js = res.json.toString()
        val trozos = js.chunked(TROZO)
        trozos.forEachIndexed { i, t -> Log.i(Medidor.ETIQUETA, "RESULTADO_JSON ${i + 1}/${trozos.size} $t") }
    }

    /** Escribe el JSON y devuelve las rutas donde quedó (la de adb pull primero). */
    fun guardar(ctx: Context, res: ResultadoMedida): List<String> {
        val nombre = "chispa-medir-" + SimpleDateFormat("yyyyMMdd-HHmmss", Locale.US).format(Date()) + ".json"
        val bytes = res.json.toString(2).toByteArray(Charsets.UTF_8)
        val rutas = ArrayList<String>()
        val ext = ctx.getExternalFilesDir(null)
        if (ext != null) {
            val f = File(ext, nombre)
            f.writeBytes(bytes)
            rutas += f.absolutePath
        }
        if (Build.VERSION.SDK_INT >= 29) {
            try {
                val v = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, nombre)
                    put(MediaStore.Downloads.MIME_TYPE, "application/json")
                    put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                }
                val uri = ctx.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v)
                if (uri != null) {
                    ctx.contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
                    rutas += "Descargas/$nombre"
                }
            } catch (e: Exception) {
                Log.w(Medidor.ETIQUETA, "no se pudo escribir en Descargas: ${e.message}")
            }
        }
        return rutas
    }
}
