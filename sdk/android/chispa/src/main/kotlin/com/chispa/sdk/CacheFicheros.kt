package com.chispa.sdk

import java.io.File
import java.io.InputStream
import java.security.MessageDigest
import java.util.UUID

/**
 * Ficheros que el SDK deja en disco (ONNX de L2 extraído, asset copiado): nombrados por el hash de su contenido y escritos
 * en un temporal con rename atómico, de modo que un fichero con su nombre definitivo siempre está completo.
 */
internal object CacheFicheros {
    fun sha256Hex(bytes: ByteArray): String = hex(MessageDigest.getInstance("SHA-256").digest(bytes))

    fun sha256Hex(f: File): String {
        val md = MessageDigest.getInstance("SHA-256")
        f.inputStream().use { entrada ->
            val buf = ByteArray(1 shl 16)
            while (true) {
                val n = entrada.read(buf)
                if (n < 0) break
                md.update(buf, 0, n)
            }
        }
        return hex(md.digest())
    }

    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }

    /** Escribe [destino] con [escribir] sobre un temporal propio y lo renombra; si `renameTo` falla, borra y reintenta una vez. */
    fun escribirAtomico(destino: File, escribir: (File) -> Unit) {
        destino.parentFile?.mkdirs()
        val tmp = File(destino.path + ".${UUID.randomUUID()}.tmp")
        try {
            escribir(tmp)
            if (!tmp.renameTo(destino)) {
                destino.delete()
                if (!tmp.renameTo(destino)) throw ErrorChispa("no se pudo mover ${tmp.name} a ${destino.path}")
            }
        } finally {
            tmp.delete() // no queda nada si el rename tuvo éxito (ya no existe)
        }
    }

    fun copiarAtomico(origen: InputStream, destino: File) =
        escribirAtomico(destino) { tmp -> tmp.outputStream().use { origen.copyTo(it) } }

    /** `chispa-l2-<hash>.onnx` en [dir]; el hash es el de la sección L2 del motor (o, si no lo da, el del [modelo]). Extrae solo si falta. */
    fun rutaOnnxL2(motor: Motor, dir: File, modelo: File): String {
        val hash = motor.hashSeccion(SECCION_L2).ifEmpty { sha256Hex(modelo) }
        val onnx = File(dir, "chispa-l2-$hash.onnx")
        if (!onnx.isFile || onnx.length() == 0L) escribirAtomico(onnx) { motor.extraerL2(it.absolutePath) }
        return onnx.absolutePath
    }
}
