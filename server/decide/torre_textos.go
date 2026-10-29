package decide

import "chispa/runtime/torre"

// Las reglas puras de las torres viven en runtime/torre (sin red, para que el motor móvil no arrastre net/http); aquí se
// reexportan con los nombres de siempre.

// TextoTorre es la regla única de texto de torre (ver torre.Texto).
func TextoTorre(pregunta string, o Opcion) string { return torre.Texto(pregunta, torre.Opcion(o)) }

func aTorre(p Pregunta) torre.Pregunta {
	k := p.Kind
	if k == KindMulti { // una torre por opción, como choice (runtime/torre no conoce multi)
		k = KindChoice
	}
	return torre.Pregunta{Texto: p.Texto, Kind: k, Opciones: aOpcionesTorre(p.Opciones)}
}

func aOpcionesTorre(os []Opcion) []torre.Opcion {
	out := make([]torre.Opcion, len(os))
	for i, o := range os {
		out[i] = torre.Opcion{ID: o.ID, Description: o.Description}
	}
	return out
}

func deOpcionesTorre(os []torre.Opcion) []Opcion {
	if os == nil {
		return nil
	}
	out := make([]Opcion, len(os))
	for i, o := range os {
		out[i] = Opcion{ID: o.ID, Description: o.Description}
	}
	return out
}

// TextosTorre son los textos de torre de una pregunta, en el orden de OpcionesConsulta.
func TextosTorre(p Pregunta) []string { return torre.Textos(aTorre(p)) }

// ClaveTorre es la clave de caché de una torre (ver torre.Clave).
func ClaveTorre(pregunta string, o Opcion) string { return torre.Clave(pregunta, torre.Opcion(o)) }

// OpcionesConsulta son las opciones que llevan torre (ver torre.OpcionesConsulta).
func OpcionesConsulta(p Pregunta) []Opcion { return deOpcionesTorre(torre.OpcionesConsulta(aTorre(p))) }

// CuantizarTorre cuantiza h a int8 con escala max|h|/127 (1 si h es cero): devuelve los valores y la escala.
func CuantizarTorre(h []float32) ([]byte, float32) { return torre.Cuantizar(h) }

func cuantizarTorre(h []float32) torreDin {
	v, e := torre.Cuantizar(h)
	return torreDin{v, e}
}

// Alias internos para el resto del paquete (l2c.go y los tests).
func claveTorre(pregunta string, o Opcion) string { return ClaveTorre(pregunta, o) }
