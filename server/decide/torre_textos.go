package decide

import (
	"math"
	"strconv"
	"strings"

	"chispa/format/chispa3"
)

const sepTorre = " · "

// TextoTorre es la regla única de texto de torre (texto_opcion de model/l2/modelo.py): «passage: pregunta · opción ·
// descripción». La usan el servidor y el motor móvil.
func TextoTorre(pregunta string, o Opcion) string {
	return strings.Join([]string{"passage: " + pregunta, o.ID, o.Description}, sepTorre)
}

// TextosTorre son los textos de torre de una pregunta, en el orden de OpcionesConsulta.
func TextosTorre(p Pregunta) []string {
	ops := OpcionesConsulta(p)
	out := make([]string, len(ops))
	for i, o := range ops {
		out[i] = TextoTorre(p.Texto, o)
	}
	return out
}

// ClaveTorre es la clave de caché de una torre: HashEsquema(pregunta, [opción, descripción]). Las torres se cachean una a
// una, no por esquema entero, por dos razones: (1) el orden de las opciones de la petición no tiene por qué ser el del
// primer cálculo, y un vector cacheado por posición se emparejaría con la opción equivocada; (2) la torre depende también
// de la descripción, que HashEsquema(pregunta, opciones) (la clave de ESQUEMAS) no recoge. ClaveEsquema (FNV-128, no
// criptográfico, ordena las opciones y mete Kind) no sirve para esto.
func ClaveTorre(pregunta string, o Opcion) string {
	h := chispa3.HashEsquema(pregunta, []string{o.ID, o.Description})
	return string(h[:])
}

// OpcionesConsulta son las opciones que llevan torre: una por opción en choice; en noul y score una sola, la de la
// consulta (texto_consulta del export): «true» en noul y el nivel máximo en score. Vacío si score no trae opciones.
func OpcionesConsulta(p Pregunta) []Opcion {
	switch p.Kind {
	case KindChoice:
		return p.Opciones
	case KindNoul:
		for _, o := range p.Opciones {
			if o.ID == "true" {
				return []Opcion{o}
			}
		}
		return []Opcion{{ID: "true"}}
	}
	if len(p.Opciones) == 0 {
		return nil
	}
	ult, max := len(p.Opciones)-1, -1 // el nivel mayor si los ids son numéricos; si no, la última
	for i, o := range p.Opciones {
		if n, err := strconv.Atoi(o.ID); err == nil && n > max {
			ult, max = i, n
		}
	}
	return p.Opciones[ult : ult+1]
}

// CuantizarTorre cuantiza h a int8 con escala max|h|/127 (1 si h es cero): devuelve los valores y la escala.
func CuantizarTorre(h []float32) ([]byte, float32) {
	t := cuantizarTorre(h)
	return t.v, t.e
}

func cuantizarTorre(h []float32) torreDin {
	var m float64
	for _, x := range h {
		m = math.Max(m, math.Abs(float64(x)))
	}
	esc := m / 127
	if m == 0 {
		esc = 1
	}
	q := make([]byte, len(h))
	for i, x := range h {
		q[i] = byte(int8(math.Max(-127, math.Min(127, math.Round(float64(x)/esc)))))
	}
	return torreDin{q, float32(esc)}
}

// Alias internos para el resto del paquete (l2c.go y los tests).
func claveTorre(pregunta string, o Opcion) string { return ClaveTorre(pregunta, o) }
