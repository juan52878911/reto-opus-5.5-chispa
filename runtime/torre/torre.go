// Package torre reúne las reglas puras de las torres de L2 (textos, opciones de consulta, clave de caché y
// cuantización) que comparten el servidor (server/decide) y el motor móvil (sdk/movil/chispamovil). Sin red ni
// dependencias más allá de format/chispa3: así el motor móvil no arrastra net/http ni crypto/tls.
package torre

import (
	"math"
	"strconv"
	"strings"

	"chispa/format/chispa3"
)

const (
	KindChoice = "choice"
	KindScore  = "score"
	KindNoul   = "noul"
)

type Opcion struct {
	ID          string `json:"id"`
	Description string `json:"description,omitempty"`
}

// Pregunta es lo mínimo de una pregunta que necesitan estas reglas.
type Pregunta struct {
	Texto    string
	Kind     string
	Opciones []Opcion
}

const sepTorre = " · "

// Texto es la regla única de texto de torre (texto_opcion de model/l2/modelo.py): «passage: pregunta · opción ·
// descripción». La usan el servidor y el motor móvil.
func Texto(pregunta string, o Opcion) string {
	return strings.Join([]string{"passage: " + pregunta, o.ID, o.Description}, sepTorre)
}

// Textos son los textos de torre de una pregunta, en el orden de OpcionesConsulta.
func Textos(p Pregunta) []string {
	ops := OpcionesConsulta(p)
	out := make([]string, len(ops))
	for i, o := range ops {
		out[i] = Texto(p.Texto, o)
	}
	return out
}

// Clave es la clave de caché de una torre: HashEsquema(pregunta, [opción, descripción]). Las torres se cachean una a
// una, no por esquema entero, por dos razones: (1) el orden de las opciones de la petición no tiene por qué ser el del
// primer cálculo, y un vector cacheado por posición se emparejaría con la opción equivocada; (2) la torre depende también
// de la descripción, que HashEsquema(pregunta, opciones) (la clave de ESQUEMAS) no recoge. ClaveEsquema (FNV-128, no
// criptográfico, ordena las opciones y mete Kind) no sirve para esto.
func Clave(pregunta string, o Opcion) string {
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
		if n, ok := canonico(o.ID); ok && n > max {
			ult, max = i, n
		}
	}
	return p.Opciones[ult : ult+1]
}

// canonico devuelve el entero de id si está en forma canónica (strconv.Itoa(n) == id).
func canonico(id string) (int, bool) {
	n, err := strconv.Atoi(id)
	return n, err == nil && strconv.Itoa(n) == id
}

// Cuantizar cuantiza h a int8 con escala max|h|/127 (1 si h es cero): devuelve los valores y la escala.
func Cuantizar(h []float32) ([]byte, float32) {
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
	return q, float32(esc)
}
