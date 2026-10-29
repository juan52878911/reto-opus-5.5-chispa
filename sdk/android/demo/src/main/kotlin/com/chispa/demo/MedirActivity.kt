package com.chispa.demo

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Log
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.io.File

/**
 * Pantalla «Medir»: N decisiones por escenario y p50/p95/p99. El modelo sale de un fichero elegido, de la carpeta
 * externa de la app o de `assets/` (ver [Medidor.localizar]). Se puede lanzar sin tocar nada:
 * `adb shell am start -n com.chispa.demo/.MedirActivity --ei n 1000 --ez auto true`.
 */
class MedirActivity : Activity() {
    private lateinit var estado: TextView
    private lateinit var salida: TextView
    private lateinit var cajaN: EditText
    private lateinit var botonMedir: Button
    private lateinit var botonCompartir: Button
    @Volatile private var cancelar = false
    @Volatile private var ultimo: ResultadoMedida? = null
    private var hilo: Thread? = null

    override fun onCreate(estadoGuardado: Bundle?) {
        super.onCreate(estadoGuardado)
        estado = TextView(this).apply { textSize = 14f }
        salida = TextView(this).apply { textSize = 13f; typeface = android.graphics.Typeface.MONOSPACE; setTextIsSelectable(true) }
        cajaN = EditText(this).apply {
            setText((intent.getIntExtra("n", 1000)).toString())
            inputType = android.text.InputType.TYPE_CLASS_NUMBER
        }
        val elegirModelo = Button(this).apply { text = "Elegir .chispa"; setOnClickListener { elegir(PEDIR_MODELO) } }
        val elegirTok = Button(this).apply { text = "Elegir tokenizador (.chispa-tok)"; setOnClickListener { elegir(PEDIR_TOKENIZADOR) } }
        botonMedir = Button(this).apply { text = "Medir"; setOnClickListener { medir() } }
        botonCompartir = Button(this).apply { text = "Compartir JSON"; isEnabled = false; setOnClickListener { compartir() } }
        val raiz = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 32)
            addView(TextView(this@MedirActivity).apply { text = "Decisiones por escenario (N):" })
            addView(cajaN)
            addView(elegirModelo)
            addView(elegirTok)
            addView(botonMedir)
            addView(botonCompartir)
            addView(estado)
        }
        raiz.addView(ScrollView(this).apply { addView(salida) }, ViewGroup.LayoutParams.MATCH_PARENT, 0)
        (raiz.getChildAt(raiz.childCount - 1).layoutParams as LinearLayout.LayoutParams).weight = 1f
        setContentView(raiz)
        estado.text = resumenFicheros()
        if (intent.getBooleanExtra("auto", false)) medir()
    }

    private fun resumenFicheros(): String {
        fun donde(n: String) = Medidor.localizar(this, n)?.let { if (File(it).isAbsolute) it else "assets/$it" } ?: "no hay"
        return "Modelo: ${donde(Medidor.MODELO)}\nTokenizador: ${donde(Medidor.TOKENIZADOR)}\n" +
            "Esquema few-shot: ${donde(Medidor.ESQUEMA_JSON)}"
    }

    private fun elegir(codigo: Int) {
        val i = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*"
        }
        startActivityForResult(i, codigo)
    }

    @Deprecated("API clásica de Activity; la demo no usa AndroidX")
    override fun onActivityResult(codigo: Int, resultado: Int, datos: Intent?) {
        super.onActivityResult(codigo, resultado, datos)
        val uri: Uri = datos?.data ?: return
        if (resultado != RESULT_OK) return
        val destino = when (codigo) {
            PEDIR_MODELO -> Medidor.MODELO
            PEDIR_TOKENIZADOR -> Medidor.TOKENIZADOR
            else -> return
        }
        estado.text = "Copiando ${nombreDe(uri)}…"
        Thread {
            val msg = try {
                val d = File(File(filesDir, "elegido").apply { mkdirs() }, destino)
                // Temporal + renombrado: chispamovil tiene el .chispa mapeado en memoria y truncarlo en sitio daría SIGBUS;
                // con rename el inodo viejo sigue vivo para el mapeo y los siguientes aperturas ven el nuevo.
                val tmp = File(d.path + ".${java.util.UUID.randomUUID()}.tmp")
                try {
                    contentResolver.openInputStream(uri)!!.use { i -> tmp.outputStream().use { i.copyTo(it) } }
                    java.nio.file.Files.move(tmp.toPath(), d.toPath(), java.nio.file.StandardCopyOption.REPLACE_EXISTING, java.nio.file.StandardCopyOption.ATOMIC_MOVE)
                } finally {
                    tmp.delete()
                }
                resumenFicheros()
            } catch (e: Exception) {
                "No se pudo copiar: ${e.message}"
            }
            runOnUiThread { estado.text = msg }
        }.start()
    }

    private fun nombreDe(uri: Uri): String =
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
            if (it.moveToFirst()) it.getString(0) else null
        } ?: uri.lastPathSegment.orEmpty()

    private fun medir() {
        if (hilo?.isAlive == true) {
            cancelar = true
            return
        }
        val n = cajaN.text.toString().toIntOrNull()?.coerceAtLeast(1) ?: 1000
        cancelar = false
        botonMedir.text = "Cancelar"
        salida.text = ""
        hilo = Thread {
            try {
                val res = Medidor(this, ConfigMedida(n = n)).correr(
                    progreso = { runOnUiThread { estado.text = it } },
                    cancelado = { cancelar },
                )
                ultimo = res
                Exportar.logcat(res)
                val rutas = Exportar.guardar(this, res)
                runOnUiThread {
                    salida.text = formatear(res)
                    estado.text = "Listo. JSON en: " + rutas.joinToString(", ") + "\nlogcat: adb logcat -s ${Medidor.ETIQUETA}"
                    botonCompartir.isEnabled = true
                }
            } catch (e: Throwable) {
                Log.e(Medidor.ETIQUETA, "medida fallida", e)
                runOnUiThread { estado.text = "Falló: ${e.message}\n${resumenFicheros()}" }
            } finally {
                runOnUiThread { botonMedir.text = "Medir" }
            }
        }.also { it.start() }
    }

    private fun formatear(res: ResultadoMedida): String {
        val d = res.json.getJSONObject("dispositivo")
        val o = res.json.getJSONObject("ort")
        val sb = StringBuilder()
        sb.append("${d.getString("fabricante")} ${d.getString("modelo")} · Android ${d.getString("android")} (API ${d.getInt("sdk_int")})\n")
        sb.append("ABI ${d.getJSONArray("abi")} · ${d.getInt("cpus")} CPU · RAM ${d.getLong("ram_total_mb")} MB\n")
        sb.append("ORT: pedidos ${o.getJSONArray("proveedores_pedidos")}, usados ${o.getJSONArray("proveedores_usados")}; disponibles ${o.getJSONArray("proveedores_disponibles")}\n\n")
        for (e in res.escenarios) {
            sb.append(e.linea()).append("\n  1.ª llamada ${"%.1f".format(e.primeraMs)} ms\n")
            e.nota?.let { sb.append("  $it\n") }
        }
        val notas = res.json.getJSONArray("notas")
        for (i in 0 until notas.length()) sb.append("\n⚠ ").append(notas.getString(i))
        return sb.toString()
    }

    private fun compartir() {
        val res = ultimo ?: return
        val i = Intent(Intent.ACTION_SEND).apply {
            type = "application/json"
            putExtra(Intent.EXTRA_SUBJECT, "Chispa · medida de latencia")
            putExtra(Intent.EXTRA_TEXT, res.json.toString(2))
        }
        startActivity(Intent.createChooser(i, "Compartir JSON"))
    }

    override fun onDestroy() {
        cancelar = true
        super.onDestroy()
    }

    private companion object {
        const val PEDIR_MODELO = 1
        const val PEDIR_TOKENIZADOR = 2
    }
}
