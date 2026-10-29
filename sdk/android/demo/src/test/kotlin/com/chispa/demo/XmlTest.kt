package com.chispa.demo

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertTrue
import org.junit.Test

/** Todos los XML de la demo (manifiesto y recursos) deben estar bien formados: un «--» en un comentario rompe el build. */
class XmlTest {
    @Test
    fun losXmlDeLaDemoSonValidos() {
        // Gradle corre los tests unitarios con el directorio del módulo como directorio de trabajo.
        // Se saltan los ocultos: un empaquetado hecho en macOS deja copias AppleDouble («._AndroidManifest.xml») que no son XML.
        val xmls = File("src/main").walkTopDown()
            .filter { it.isFile && it.extension == "xml" && !it.name.startsWith(".") }.toList()
        assertTrue("no encontré AndroidManifest.xml", xmls.any { it.name == "AndroidManifest.xml" })
        val fabrica = DocumentBuilderFactory.newInstance()
        for (f in xmls) fabrica.newDocumentBuilder().parse(f)
    }
}
