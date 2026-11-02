// Package torre reúne las reglas puras de las torres de L2 (textos, opciones de consulta, clave de caché y
// cuantización) que comparten el servidor (server/decide) y el motor móvil (sdk/movil/chispamovil). Sin red ni
// dependencias más allá de format/chispa3: así el motor móvil no arrastra net/http ni crypto/tls.
package torre

import (
	"crypto/sha256"
	"math"
	"strconv"
	"strings"
	"unicode"

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

// TextoTorre es la regla única de texto de torre, por versión de META.texto_torre (ver chispa3.TextoTorreV1/V2SinID):
//   - v1 (y versión vacía): «passage: pregunta · id · descripción» (texto_opcion de model/l2/modelo.py).
//   - v2_sin_id: si strip(descripción) no está vacía, «passage: pregunta · descripción» (la descripción tal cual); si lo
//     está, el texto v1 exacto.
//
// strip solo decide si la descripción está vacía (espacios Unicode, como str.strip de Python). Esta función no ve el resto de
// opciones: la regla de descripciones repetidas (v2 con id si dos o más opciones de la pregunta comparten descripción) la
// aplica TextoOpcion, que es la que usan el servidor y el motor móvil.
func TextoTorre(version, pregunta, id, descripcion string) string {
	if version == chispa3.TextoTorreV2SinID && !vacia(descripcion) {
		return "passage: " + pregunta + sepTorre + descripcion
	}
	return strings.Join([]string{"passage: " + pregunta, id, descripcion}, sepTorre)
}

// esEspacioPy es la definición de espacio de str.strip de Python (unicode.IsSpace más U+001C..U+001F).
func esEspacioPy(r rune) bool { return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f) }

// strip es str.strip() de Python.
func strip(s string) string { return strings.TrimFunc(s, esEspacioPy) }

// vacia dice si strip(s) == "".
func vacia(s string) bool { return strip(s) == "" }

// TextoOpcion es el texto de torre de la opción o de una pregunta cuyas opciones son todas (las de la pregunta, no solo las
// que llevan torre). En v2_sin_id, las opciones cuya descripción (tras strip, no vacía) se repite en dos o más opciones de la
// pregunta usan el texto v1 (con id): sin id las torres de esas opciones serían iguales; solo esas.
func TextoOpcion(version, pregunta string, o Opcion, todas []Opcion) string {
	if version == chispa3.TextoTorreV2SinID && descripcionRepetida(o, todas) {
		version = chispa3.TextoTorreV1
	}
	return TextoTorre(version, pregunta, o.ID, o.Description)
}

// descripcionRepetida dice si la descripción de o (tras strip, no vacía) la tiene otra opción de todas además de la propia.
// Se cuenta por posición, no por id: dos opciones con el mismo id y la misma descripción también cuentan como repetidas.
func descripcionRepetida(o Opcion, todas []Opcion) bool {
	d := strip(o.Description)
	if d == "" {
		return false
	}
	n := 0
	for _, x := range todas {
		if strip(x.Description) == d {
			n++
		}
	}
	return n >= 2
}

// DescripcionesRepetidas devuelve los ids de las opciones de la pregunta cuya descripción (tras strip, no vacía) se repite, en
// el orden de las opciones. Sirve para avisar al entrenar y para tests.
func DescripcionesRepetidas(opciones []Opcion) []string {
	var ids []string
	for _, o := range opciones {
		if descripcionRepetida(o, opciones) {
			ids = append(ids, o.ID)
		}
	}
	return ids
}

// Texto es el texto de torre de la opción o de la pregunta p (ver TextoOpcion).
func Texto(version string, p Pregunta, o Opcion) string {
	return TextoOpcion(version, p.Texto, o, p.Opciones)
}

// Textos son los textos de torre de una pregunta, en el orden de OpcionesConsulta.
func Textos(version string, p Pregunta) []string {
	ops := OpcionesConsulta(p)
	out := make([]string, len(ops))
	for i, o := range ops {
		out[i] = Texto(version, p, o)
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

// ClaveTexto es la clave de caché de una torre a partir de su texto efectivo (TextoOpcion): dos opciones con el mismo texto
// tienen la misma torre y dos con textos distintos no comparten clave aunque coincidan pregunta, id y descripción (la regla de
// descripciones repetidas de v2 hace que el texto dependa de las demás opciones). Es lo que usan el servidor y el motor móvil.
func ClaveTexto(texto string) string {
	h := sha256.Sum256([]byte(texto))
	return string(h[:])
}

// OpcionesConsulta son las opciones que llevan torre: una por opción en choice; en noul y score una sola, la de la
// consulta (texto_consulta del export): «true» en noul y el nivel máximo (K) en score. Vacío si los ids de score no son exactamente 1..K.
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
	// score: la consulta es el nivel máximo, y solo hay torre si los ids son exactamente 1..K (como tok.NivelesScore).
	k := len(p.Opciones)
	for _, o := range p.Opciones {
		if n, ok := canonico(o.ID); ok && n == k {
			if !idsUnoAK(p.Opciones) {
				return nil
			}
			return []Opcion{o}
		}
	}
	return nil
}

// idsUnoAK dice si los ids son exactamente 1..K canónicos, sin repetidos y en cualquier orden.
func idsUnoAK(ops []Opcion) bool {
	vistos := make([]bool, len(ops)+1)
	for _, o := range ops {
		n, ok := canonico(o.ID)
		if !ok || n < 1 || n > len(ops) || vistos[n] {
			return false
		}
		vistos[n] = true
	}
	return len(ops) > 0
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
