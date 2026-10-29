package com.chispa.demo

import android.app.ActivityManager
import android.content.Context
import android.os.Build
import android.os.Debug
import com.chispa.sdk.Cascada
import com.chispa.sdk.CapaConTau
import com.chispa.sdk.CapaL1
import com.chispa.sdk.Chispa
import com.chispa.sdk.ErrorChispa
import com.chispa.sdk.MotorNativo
import com.chispa.sdk.Opcion
import com.chispa.sdk.Pregunta
import com.chispa.sdk.ProveedorOrt
import com.chispa.sdk.Respuesta
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.Locale

/** Parámetros de una medida. */
data class ConfigMedida(
    val n: Int = 1000,
    val calentamiento: Int = 100,
    val umbralP99Ms: Double = 150.0,
    /** Proveedores de ORT a medir, uno tras otro (la cascada se reabre con cada uno). */
    val proveedores: List<ProveedorOrt> = ProveedorOrt.values().toList(),
)

/** Latencias de un escenario, en ms por decisión. */
class ResultadoEscenario(
    val nombre: String,
    val esquema: String,
    val capa: String,
    val n: Int,
    val p50: Double,
    val p95: Double,
    val p99: Double,
    val max: Double,
    val media: Double,
    val decisionesPorSegundo: Double,
    val primeraMs: Double,
    val porCapa: Map<String, Int>,
    val errores: Int,
    val nota: String?,
    /** Proveedor con el que quedó la sesión de L2 ("CPU" si el pedido falló; "n/a" sin L2 o en L1 solo). */
    val proveedor: String = "n/a",
    val proveedorPedido: String = "n/a",
) {
    fun toJson(): JSONObject {
        val capas = JSONObject()
        for ((k, v) in porCapa) capas.put(k, v)
        return JSONObject()
            .put("nombre", nombre).put("esquema", esquema).put("capa", capa).put("n", n)
            .put("p50_ms", redondear(p50)).put("p95_ms", redondear(p95)).put("p99_ms", redondear(p99))
            .put("max_ms", redondear(max)).put("media_ms", redondear(media))
            .put("decisiones_por_s", redondear(decisionesPorSegundo))
            .put("primera_llamada_ms", redondear(primeraMs))
            .put("capa_que_respondio", capas)
            .put("errores", errores)
            .put("proveedor", proveedor).put("proveedor_pedido", proveedorPedido)
            .put("nota", nota ?: JSONObject.NULL)
    }

    fun conProveedor(efectivo: String, pedido: String) = ResultadoEscenario(
        nombre, esquema, capa, n, p50, p95, p99, max, media, decisionesPorSegundo, primeraMs, porCapa, errores, nota,
        efectivo, pedido,
    )

    fun linea(): String = String.format(
        Locale.US, "%s: p50 %.1f · p95 %.1f · p99 %.1f ms · %.0f dec/s · capas %s%s", nombre, p50, p95, p99,
        decisionesPorSegundo, porCapa, if (errores > 0) " · $errores errores" else "",
    )

    private fun redondear(x: Double) = Math.round(x * 1000.0) / 1000.0
}

class ResultadoMedida(val escenarios: List<ResultadoEscenario>, val json: JSONObject)

/**
 * La medida de latencia de la demo: N decisiones (tras calentar) con textos en español, sobre un esquema nuevo
 * (zero-shot) y sobre el del `.chispa` (few-shot), por capa. Solo usa la API pública del SDK
 * (`Chispa.abrir`, `Cascada`, `CapaL1`, `MotorNativo`, `Pregunta`).
 */
class Medidor(private val ctx: Context, private val cfg: ConfigMedida = ConfigMedida()) {

    /** [progreso] recibe líneas de estado; [cancelado] se consulta entre decisiones. */
    fun correr(progreso: (String) -> Unit = {}, cancelado: () -> Boolean = { false }): ResultadoMedida {
        val rutaModelo = aFichero(ctx, MODELO)
            ?: throw ErrorChispa("no hay $MODELO (asset, fichero elegido ni carpeta externa de la app)")
        val rutaTok = aFichero(ctx, TOKENIZADOR)
        val fewShot = esquemaDelModelo(ctx)
        val notas = ArrayList<String>()

        val resultados = ArrayList<ResultadoEscenario>()
        val motorL1 = MotorNativo.abrir(rutaModelo)
        try {
            val soloL1 = Cascada(listOf(CapaConTau(CapaL1(motorL1), 0.0)))
            var capasVistas = emptyList<String>()
            for ((i, prov) in cfg.proveedores.withIndex()) {
                if (cancelado()) break
                val chispa: Chispa = try {
                    Chispa.abrir(ctx, rutaModelo, rutaTokenizador = rutaTok, proveedorOrt = prov)
                } catch (e: Exception) {
                    if (rutaTok == null) throw e
                    notas += "tokenizador no utilizable (${e.message}): cascada sin L2"
                    Chispa.abrir(ctx, rutaModelo, proveedorOrt = prov)
                }
                try {
                    val capas = chispa.capas
                    capasVistas = capas
                    val efectivo = chispa.proveedorOrt?.name ?: "n/a"
                    if (efectivo != "n/a" && efectivo != prov.name) notas += "$prov no disponible: la sesión de L2 quedó en $efectivo"
                    val nombreCascada = "cascada " + capas.joinToString("→") + " [$prov]"
                    for ((esquema, pregunta) in listOf("zero-shot" to ZERO_SHOT, "few-shot" to fewShot)) {
                        // L1 solo no usa ORT: se mide una vez, con el primer proveedor
                        if (i == 0) {
                            if (cancelado()) break
                            resultados += medir("$esquema · L1 solo", esquema, "L1", cfg, progreso, cancelado) {
                                soloL1.decidir(it, pregunta)
                            }
                        }
                        if (cancelado()) break
                        resultados += medir("$esquema · $nombreCascada", esquema, nombreCascada, cfg, progreso, cancelado) {
                            chispa.decidir(it, listOf(pregunta)).first()
                        }.conProveedor(efectivo, prov.name)
                    }
                } finally {
                    chispa.close()
                }
            }
            if ("L2" !in capasVistas) notas += "sin L2 (falta el tokenizador e5, o el .chispa no trae L2/ESQUEMAS): la cascada no mide L2 ni proveedores"
            return ResultadoMedida(resultados, informe(resultados, capasVistas, rutaModelo, rutaTok, notas))
        } finally {
            motorL1.close()
        }
    }

    private fun informe(
        res: List<ResultadoEscenario>, capas: List<String>, modelo: String, tok: String?, notas: List<String>,
    ): JSONObject {
        val am = ctx.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val mi = ActivityManager.MemoryInfo().also { am.getMemoryInfo(it) }
        val disponibles = try {
            ai.onnxruntime.OrtEnvironment.getAvailableProviders().map { it.name }
        } catch (e: Throwable) {
            listOf("desconocido: ${e.message}")
        }
        val dispositivo = JSONObject()
            .put("fabricante", Build.MANUFACTURER).put("modelo", Build.MODEL).put("dispositivo", Build.DEVICE)
            .put("soc", if (Build.VERSION.SDK_INT >= 31) Build.SOC_MODEL else JSONObject.NULL)
            .put("android", Build.VERSION.RELEASE).put("sdk_int", Build.VERSION.SDK_INT)
            .put("abi", JSONArray(Build.SUPPORTED_ABIS.toList()))
            .put("cpus", Runtime.getRuntime().availableProcessors())
            .put("ram_total_mb", mi.totalMem / (1024 * 1024))
            .put("ram_disponible_mb", mi.availMem / (1024 * 1024))
            .put("pss_proceso_mb", Debug.getPss() / 1024)
        // Cada escenario de cascada trae `proveedor` (el efectivo) y `proveedor_pedido`; L0 y L1 son Go puro (sin ORT).
        val usados = res.map { it.proveedor }.filter { it != "n/a" }.distinct()
        val ort = JSONObject()
            .put("proveedores_disponibles", JSONArray(disponibles))
            .put("proveedores_pedidos", JSONArray(cfg.proveedores.map { it.name }))
            .put("proveedores_usados", JSONArray(usados))
            .put("nota", "XNNPACK, NNAPI y CPU se miden por separado; si uno falla al crear la sesión, el escenario dice CPU")
        val config = JSONObject()
            .put("n", cfg.n).put("calentamiento", cfg.calentamiento).put("umbral_p99_ms", cfg.umbralP99Ms)
            .put("modelo", File(modelo).name).put("modelo_bytes", File(modelo).length())
            .put("tokenizador", tok?.let { File(it).name } ?: JSONObject.NULL)
            .put("capas_cascada", JSONArray(capas))
            .put("textos_distintos", Textos.ES.size)
        val esc = JSONArray()
        for (r in res) esc.put(r.toJson())
        return JSONObject()
            .put("etiqueta", ETIQUETA).put("version", 1)
            .put("fecha_ms", System.currentTimeMillis())
            .put("dispositivo", dispositivo).put("ort", ort).put("config", config)
            .put("escenarios", esc).put("notas", JSONArray(notas))
    }

    companion object {
        const val ETIQUETA = "ChispaMedir"
        const val MODELO = "modelo.chispa"
        const val TOKENIZADOR = "e5.chispa-tok"
        const val ESQUEMA_JSON = "esquema.json"

        /** Un esquema que el `.chispa` no puede traer: el motor tiene que calcular sus torres. */
        val ZERO_SHOT = Pregunta(
            "¿Con qué área de la empresa hay que contactar a esta persona del mensaje?",
            listOf(
                Opcion("ventas_comerciales", "equipo que atiende cotizaciones, precios y nuevos pedidos"),
                Opcion("cartera_y_cobros", "equipo que revisa pagos, cobros duplicados y reembolsos"),
                Opcion("logistica_envios", "equipo que gestiona entregas, direcciones y paquetes demorados"),
                Opcion("soporte_tecnico", "equipo que arregla fallos de la aplicación, claves y accesos"),
                Opcion("atencion_general", "recepción: saludos, horarios y preguntas generales"),
            ),
        )

        /** El esquema por defecto del `.chispa`; el de verdad se da en `esquema.json` (question, kind, options[{id,description}]). */
        val FEW_SHOT_POR_DEFECTO = Pregunta(
            "¿Qué quiere el cliente en este mensaje de WhatsApp?",
            listOf(
                Opcion("compra", "quiere comprar o preguntar por un producto"),
                Opcion("soporte", "pide ayuda o soporte con algo que ya tiene"),
                Opcion("queja", "presenta una queja o reclamo"),
                Opcion("saludo", "solo saluda o conversa"),
            ),
        )

        /** Dónde se busca un fichero: elegido en pantalla, carpeta externa de la app (adb push) y filesDir. */
        private fun carpetas(ctx: Context): List<File> =
            listOfNotNull(File(ctx.filesDir, "elegido"), ctx.getExternalFilesDir(null), ctx.filesDir)

        /** Ruta absoluta si hay fichero con ese nombre; el nombre del asset si solo está en `assets/`; null si no hay nada. */
        fun localizar(ctx: Context, nombre: String): String? {
            for (d in carpetas(ctx)) {
                val f = File(d, nombre)
                if (f.isFile && f.length() > 0) return f.absolutePath
            }
            return try {
                ctx.assets.open(nombre).close()
                nombre
            } catch (e: IOException) {
                null
            }
        }

        /** Como [localizar], pero siempre una ruta absoluta (el motor mapea el fichero): copia el asset a `filesDir/chispa/`. */
        fun aFichero(ctx: Context, nombre: String): String? {
            val ruta = localizar(ctx, nombre) ?: return null
            if (File(ruta).isAbsolute) return ruta
            val destino = File(ctx.filesDir, "chispa/$nombre")
            val tam = try {
                ctx.assets.openFd(nombre).use { it.length }
            } catch (e: IOException) {
                -1L
            }
            if (destino.isFile && tam >= 0 && destino.length() == tam) return destino.absolutePath
            destino.parentFile?.mkdirs()
            val tmp = File(destino.path + ".tmp")
            ctx.assets.open(nombre).use { i -> tmp.outputStream().use { i.copyTo(it) } }
            if (!tmp.renameTo(destino)) throw ErrorChispa("no se pudo copiar el asset $nombre")
            return destino.absolutePath
        }

        /** `esquema.json` si existe; si no, el de por defecto. */
        fun esquemaDelModelo(ctx: Context): Pregunta {
            val ruta = localizar(ctx, ESQUEMA_JSON) ?: return FEW_SHOT_POR_DEFECTO
            val texto = if (File(ruta).isAbsolute) File(ruta).readText() else ctx.assets.open(ruta).bufferedReader().use { it.readText() }
            return leerPregunta(texto)
        }

        fun leerPregunta(json: String): Pregunta {
            val o = JSONObject(json)
            val ops = o.getJSONArray("options")
            val opciones = List(ops.length()) {
                val x = ops.getJSONObject(it)
                Opcion(x.getString("id"), x.optString("description").ifEmpty { null })
            }
            return Pregunta(o.getString("question"), opciones, o.optString("kind", "choice"))
        }

        private fun medir(
            nombre: String, esquema: String, capa: String, cfg: ConfigMedida,
            progreso: (String) -> Unit, cancelado: () -> Boolean, decidir: (String) -> Respuesta,
        ): ResultadoEscenario {
            val textos = Textos.ES
            progreso("$nombre: calentando (${cfg.calentamiento})…")
            // La primera llamada de un esquema nuevo calcula torres (zero-shot): se mide aparte y no entra en los percentiles.
            val t0 = System.nanoTime()
            var errores = 0
            var nota: String? = null
            try {
                decidir(textos[0])
            } catch (e: Exception) {
                errores++
                nota = "primera llamada falló: ${e.message}"
            }
            val primera = (System.nanoTime() - t0) / 1e6
            for (i in 1 until cfg.calentamiento) {
                if (cancelado()) break
                try {
                    decidir(textos[i % textos.size])
                } catch (e: Exception) {
                    // los fallos se cuentan en la fase medida
                }
            }
            progreso("$nombre: midiendo (${cfg.n})…")
            val ms = DoubleArray(cfg.n)
            val porCapa = java.util.TreeMap<String, Int>()
            var hechas = 0
            val inicio = System.nanoTime()
            for (i in 0 until cfg.n) {
                if (cancelado()) break
                val t = System.nanoTime()
                try {
                    // paso 7: recorre los textos en otro orden que el calentamiento
                    val r = decidir(textos[(i * 7 + 3) % textos.size])
                    porCapa[r.capa] = (porCapa[r.capa] ?: 0) + 1
                } catch (e: Exception) {
                    errores++
                    nota = "error: ${e.message}"
                }
                ms[hechas++] = (System.nanoTime() - t) / 1e6
            }
            val total = (System.nanoTime() - inicio) / 1e9
            if (hechas == 0) {
                return ResultadoEscenario(nombre, esquema, capa, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, primera, porCapa, errores, nota ?: "cancelado")
            }
            val orden = ms.copyOf(hechas).also { it.sort() }
            return ResultadoEscenario(
                nombre, esquema, capa, hechas,
                Estadisticas.percentil(orden, 0.50), Estadisticas.percentil(orden, 0.95), Estadisticas.percentil(orden, 0.99),
                orden.last(), orden.average(), hechas / total, primera, porCapa, errores, nota,
            )
        }
    }
}
