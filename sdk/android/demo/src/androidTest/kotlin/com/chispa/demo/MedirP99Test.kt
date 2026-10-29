package com.chispa.demo

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Medida corta en el dispositivo; falla si el p99 de algún escenario supera el umbral (Fase 3: 150 ms).
 *
 *     ./gradlew :demo:connectedDebugAndroidTest \
 *         -Pandroid.testInstrumentationRunnerArguments.p99Max=150 \
 *         -Pandroid.testInstrumentationRunnerArguments.n=200
 *
 * Sin `modelo.chispa` (asset, o `adb push` a la carpeta externa de la app) se salta: no hay nada que medir.
 */
@RunWith(AndroidJUnit4::class)
class MedirP99Test {
    @Test
    fun p99DentroDelUmbral() {
        val args = InstrumentationRegistry.getArguments()
        val umbral = args.getString("p99Max")?.toDoubleOrNull() ?: 150.0
        val n = args.getString("n")?.toIntOrNull() ?: 200
        val ctx = InstrumentationRegistry.getInstrumentation().targetContext
        assumeTrue("no hay ${Medidor.MODELO}", Medidor.localizar(ctx, Medidor.MODELO) != null)

        val res = Medidor(ctx, ConfigMedida(n = n, calentamiento = 50, umbralP99Ms = umbral)).correr()
        Exportar.logcat(res)
        assertTrue("no se midió ningún escenario", res.escenarios.isNotEmpty())
        for (e in res.escenarios) {
            assertTrue("${e.nombre}: ${e.errores} errores (${e.nota})", e.errores == 0)
            assertTrue("${e.nombre}: p99 ${e.p99} ms > $umbral ms", e.p99 <= umbral)
        }
    }
}
