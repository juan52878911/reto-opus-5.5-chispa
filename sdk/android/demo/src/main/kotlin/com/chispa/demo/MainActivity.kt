package com.chispa.demo

import android.app.Activity
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.ViewGroup
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import com.chispa.sdk.Chispa
import com.chispa.sdk.Opcion
import com.chispa.sdk.Pregunta
import java.util.Locale

/** «WhatsApp sin conexión»: escribes un mensaje y la intención aparece con su confianza, sin red. */
class MainActivity : Activity() {
    private val pregunta = Pregunta(
        "¿Qué quiere el cliente en este mensaje de WhatsApp?",
        listOf(
            Opcion("compra", "quiere comprar o preguntar por un producto"),
            Opcion("soporte", "pide ayuda o soporte con algo que ya tiene"),
            Opcion("queja", "presenta una queja o reclamo"),
            Opcion("saludo", "solo saluda o conversa"),
        ),
    )
    private var chispa: Chispa? = null

    override fun onCreate(estado: Bundle?) {
        super.onCreate(estado)
        val caja = EditText(this).apply { hint = "Escribe un mensaje de cliente…"; minLines = 3 }
        val salida = TextView(this).apply { textSize = 22f; setPadding(0, 32, 0, 0) }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 32)
            addView(caja, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            addView(salida)
        })

        try {
            chispa = Chispa.abrir(this, "modelo.chispa") // sin tokenizador: L0 → L1 (L2 pide el tokenizador de e5)
            salida.text = "Capas: ${chispa!!.capas.joinToString(" → ")}"
        } catch (e: Exception) {
            salida.text = "No se pudo abrir modelo.chispa: ${e.message}"
        }

        caja.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun afterTextChanged(s: Editable?) {
                val c = chispa ?: return
                val texto = s?.toString()?.trim().orEmpty()
                if (texto.isEmpty()) return
                val r = c.decidir(texto, listOf(pregunta)).first()
                salida.text = if (r.respuesta.isEmpty()) {
                    "Sin intención clara"
                } else {
                    String.format(Locale.US, "%s · %.0f %% (%s, %.1f ms)%s", r.respuesta, 100 * r.confianza, r.capa, r.ms,
                        if (r.escalar) " · dudosa" else "")
                }
            }
        })
    }

    override fun onDestroy() {
        chispa?.close()
        super.onDestroy()
    }
}
