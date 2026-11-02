package chispamovil

import (
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"strings"

	"chispa/format/chispa3"

	"chispa/runtime/torre"
)

// Torre de L2 al vuelo en móvil: ORT corre en la app, no en Go. Aquí vive todo lo demás, con la misma regla que
// runtime/torre (Textos, OpcionesConsulta, Clave, Cuantizar), la misma que usa server/decide: la app pide los textos, calcula h con el
// ONNX de la sección TORR (OnnxTorre) y los ids de IdsPasaje, y los devuelve con InstalarTorresL2.
// torre_test.go comprueba como comportamiento que móvil y servidor piden los mismos textos y deciden igual.

const (
	sepTorre   = " · "
	maxDimTorr = 4096
	maxDin     = 1024 // torres instaladas; al pasarse, se desalojan las menos usadas
)

// prefijoTorre es la regla por versión de TORR: el prefijo que la sección debe traer. Una versión futura puede traer otro.
var prefijoTorre = map[uint32]string{1: "passage: ", 2: "passage: "} // TORR v2 = v1 + versión del texto de torre

// validarPrefijoTorre rechaza una sección TORR cuya versión no se conoce o cuyo prefijo no es el de su versión.
func validarPrefijoTorre(f *chispa3.Fichero, prefijo string) error {
	b, err := f.Bytes(chispa3.TORR)
	if err != nil {
		return fmt.Errorf("sección TORR: %w", err)
	}
	return validarPrefijoVersion(binary.LittleEndian.Uint32(b), prefijo)
}

func validarPrefijoVersion(v uint32, prefijo string) error {
	esperado, ok := prefijoTorre[v]
	if !ok {
		return fmt.Errorf("TORR v%d: versión desconocida", v)
	}
	if prefijo != esperado {
		return fmt.Errorf("TORR v%d: prefijo %q no válido; se espera %q", v, prefijo, esperado)
	}
	return nil
}

// TieneTorre dice si el fichero trae la sección TORR.
func (c *Chispa) TieneTorre() bool { return c.torre != nil }

// OnnxTorre devuelve el ONNX de la torre (bytes de la sección TORR), o nil sin TORR. Solo vale mientras el fichero esté abierto.
func (c *Chispa) OnnxTorre() []byte {
	if c.torre == nil {
		return nil
	}
	return c.torre.ONNX
}

// DimTorre es la dimensión d de h (0 sin TORR).
func (c *Chispa) DimTorre() int {
	if c.torre == nil {
		return 0
	}
	return c.torre.Dim
}

// IdsPasaje devuelve los ids de e5 de un texto de torre (con «passage: » una sola vez, <s> y </s>, truncado a MaxLen de
// la sección, que corta el tokenizador conservando </s>) en int32 little endian, 4 bytes por id. nil sin tokenizador, sin TORR o sin tokens.
func (c *Chispa) IdsPasaje(texto string) []byte {
	if c.tok == nil || c.torre == nil {
		return nil
	}
	ids := c.tok.TokenizarMax(c.torre.Prefijo, strings.TrimPrefix(texto, c.torre.Prefijo), c.torre.MaxLen)
	if len(ids) == 0 {
		return nil
	}
	b := make([]byte, 4*len(ids))
	for i, id := range ids {
		binary.LittleEndian.PutUint32(b[4*i:], uint32(id))
	}
	return b
}

// aTorre pasa la pregunta al tipo de runtime/torre, dueño de la regla de torres.
func aTorre(p pregunta) torre.Pregunta {
	k := p.Kind
	if k == "multi" { // una torre por opción, como choice (runtime/torre no conoce multi)
		k = "choice"
	}
	d := torre.Pregunta{Texto: p.Texto, Kind: k, Opciones: make([]torre.Opcion, len(p.Opciones))}
	for i, o := range p.Opciones {
		d.Opciones[i] = torre.Opcion{ID: o.ID, Description: o.Description}
	}
	return d
}

func opcionesConsulta(p pregunta) []torre.Opcion { return torre.OpcionesConsulta(aTorre(p)) }

func cuantizarTorre(h []float32) torreL2 {
	v, e := torre.Cuantizar(h)
	return torreL2{v, e}
}

// claveTorre es la clave de la torre instalada de la opción o: sale del texto efectivo (torre.ClaveTexto), que en v2 depende
// de las demás opciones de la pregunta; así dos preguntas con la misma opción y textos distintos no se pisan.
func (c *Chispa) claveTorre(p pregunta, o torre.Opcion) string {
	return torre.ClaveTexto(torre.TextoOpcion(c.textoTorre, p.Texto, o, aTorre(p).Opciones))
}

// torresNuevas son las torres que instaló la app para este esquema; error si falta alguna.
func (c *Chispa) torresNuevas(p pregunta) ([]torreL2, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	ops := opcionesConsulta(p)
	if len(ops) == 0 {
		return nil, errors.New("sin torres para este esquema")
	}
	ts := make([]torreL2, len(ops))
	for i, o := range ops {
		k := c.claveTorre(p, o)
		t, ok := c.dyn[k]
		if !ok {
			return nil, errors.New("sin torres para este esquema")
		}
		c.dynTic++
		c.dynUso[k] = c.dynTic
		ts[i] = t
	}
	return ts, nil
}

// TextoTorre es la versión efectiva del texto de torre del fichero (la de TORR): «v1» o «v2_sin_id». Vacío si el motor está
// degradado (TorreAlVueloMotivo() != ""): no hay versión efectiva fiable y no se calculan torres al vuelo.
func (c *Chispa) TextoTorre() string {
	if c != nil && c.torreMotivo != "" {
		return ""
	}
	if c == nil || c.textoTorre == "" {
		return chispa3.TextoTorreV1
	}
	return c.textoTorre
}

// TextosTorreL2 da los textos de torre de la pregunta («passage: pregunta · opción · descripción» en v1; «passage: pregunta ·
// descripción» en v2_sin_id si la opción la tiene, ver TextoTorre; JSON []string), en
// el orden de InstalarTorresL2. "[]" si ya hay torres (ESQUEMAS o instaladas), si el fichero no trae L2, si la pregunta no vale o
// si el motor está degradado (TorreAlVueloMotivo() != "": el texto de torre del fichero es inconsistente).
func (c *Chispa) TextosTorreL2(preguntaJSON string) string {
	p, err := leerPregunta(preguntaJSON)
	if err != nil || !c.tieneL2 || c.torreMotivo != "" || scoreInvalido(p) || c.sinOpinionMulti(p, false) || c.TorresL2(preguntaJSON) {
		return "[]"
	}
	b, _ := json.Marshal(torre.Textos(c.textoTorre, aTorre(p)))
	return string(b)
}

// InstalarTorresL2 recibe las n torres (n·d float32 little endian, una por texto de TextosTorreL2), las cuantiza y las
// cachea con claveTorre; false si no cuadran (n, d, valores no finitos), no hay L2 o el motor está degradado (TorreAlVueloMotivo() != "").
func (c *Chispa) InstalarTorresL2(preguntaJSON string, torres []byte, n int) bool {
	p, err := leerPregunta(preguntaJSON)
	if err != nil || !c.tieneL2 || c.torreMotivo != "" || scoreInvalido(p) {
		return false
	}
	ops := opcionesConsulta(p)
	if n <= 0 || n != len(ops) || len(torres)%(4*n) != 0 {
		return false
	}
	d := len(torres) / (4 * n)
	if d == 0 || d > maxDimTorr || (c.torre != nil && d != c.torre.Dim) {
		return false
	}
	nuevas := make([]torreL2, n)
	for i := range nuevas {
		h := make([]float32, d)
		for j := range h {
			h[j] = math.Float32frombits(binary.LittleEndian.Uint32(torres[4*(i*d+j):]))
			if math.IsNaN(float64(h[j])) || math.IsInf(float64(h[j]), 0) {
				return false
			}
		}
		nuevas[i] = cuantizarTorre(h)
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.dyn == nil {
		c.dyn, c.dynUso = map[string]torreL2{}, map[string]uint64{}
	}
	claves := make(map[string]bool, n)
	nuevasReales := 0
	for _, o := range ops {
		k := c.claveTorre(p, o)
		if !claves[k] {
			claves[k] = true
			if _, ya := c.dyn[k]; !ya {
				nuevasReales++
			}
		}
	}
	// LRU: se desalojan las más antiguas, nunca las de esta instalación ni las que otro hilo usó o instaló en las últimas
	// n marcas (las de una instalación recién hecha, a la espera de su PuntuarL2). Si no queda a quién desalojar, c.dyn
	// se pasa de maxDin hasta que esas entradas envejezcan.
	for len(c.dyn)+nuevasReales > maxDin {
		var viejo string
		var min uint64
		for k := range c.dyn {
			u := c.dynUso[k]
			if claves[k] || u+uint64(n) > c.dynTic {
				continue
			}
			if viejo == "" || u < min {
				viejo, min = k, u
			}
		}
		if viejo == "" {
			break
		}
		delete(c.dyn, viejo)
		delete(c.dynUso, viejo)
	}
	for i, o := range ops {
		k := c.claveTorre(p, o)
		c.dynTic++
		c.dyn[k], c.dynUso[k] = nuevas[i], c.dynTic
	}
	return true
}
