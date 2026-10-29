package chispamovil

import (
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"strconv"
	"strings"

	"chispa/format/chispa3"
)

// Torre de L2 al vuelo en móvil: ORT corre en la app, no en Go. Aquí vive todo lo demás, con la misma regla que
// server/decide/l2.go (textoTorre, opcionesConsulta, claveTorre, cuantizarTorre): la app pide los textos, calcula h con el
// ONNX de la sección TORR (OnnxTorre) y los ids de IdsPasaje, y los devuelve con InstalarTorresL2.
// torre_test.go compara los textos y la caché con los del servidor sobre las mismas preguntas.

const (
	sepTorre   = " · "
	idEOS      = 2 // </s> de XLM-R
	maxDimTorr = 4096
	maxDin     = 1024 // torres instaladas; al pasarse, se desalojan las menos usadas
)

// prefijoTorre es la regla por versión de TORR: el prefijo que la sección debe traer. Una versión futura puede traer otro.
var prefijoTorre = map[uint32]string{1: "passage: "}

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
// la sección conservando </s>) en int32 little endian, 4 bytes por id. nil sin tokenizador, sin TORR o sin tokens.
func (c *Chispa) IdsPasaje(texto string) []byte {
	if c.tok == nil || c.torre == nil {
		return nil
	}
	ids := c.tok.TokenizarCon(c.torre.Prefijo, strings.TrimPrefix(texto, c.torre.Prefijo))
	if len(ids) == 0 {
		return nil
	}
	if ml := c.torre.MaxLen; ml > 0 && len(ids) > ml {
		ids = append(ids[:ml-1:ml-1], idEOS)
	}
	b := make([]byte, 4*len(ids))
	for i, id := range ids {
		binary.LittleEndian.PutUint32(b[4*i:], uint32(id))
	}
	return b
}

func textoTorre(preg string, o opcion) string {
	return strings.Join([]string{"passage: " + preg, o.ID, o.Description}, sepTorre)
}

// opcionesConsulta: una torre por opción en choice; en noul y score una sola (la «true», o el nivel mayor).
func opcionesConsulta(p pregunta) []opcion {
	switch p.Kind {
	case "choice":
		return p.Opciones
	case "noul":
		for _, o := range p.Opciones {
			if o.ID == "true" {
				return []opcion{o}
			}
		}
		return []opcion{{ID: "true"}}
	}
	ult, max := len(p.Opciones)-1, -1
	for i, o := range p.Opciones {
		if n, err := strconv.Atoi(o.ID); err == nil && n > max {
			ult, max = i, n
		}
	}
	if ult < 0 {
		return nil
	}
	return p.Opciones[ult : ult+1]
}

func claveTorre(preg string, o opcion) string {
	h := chispa3.HashEsquema(preg, []string{o.ID, o.Description})
	return string(h[:])
}

func cuantizarTorre(h []float32) torreL2 {
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
	return torreL2{q, float32(esc)}
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
		k := claveTorre(p.Texto, o)
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

// TextosTorreL2 da los textos de torre de la pregunta («passage: pregunta · opción · descripción», JSON []string), en
// el orden de InstalarTorresL2. "[]" si ya hay torres (ESQUEMAS o instaladas), si el fichero no trae L2 o si la pregunta no vale.
func (c *Chispa) TextosTorreL2(preguntaJSON string) string {
	p, err := leerPregunta(preguntaJSON)
	if err != nil || !c.tieneL2 || c.TorresL2(preguntaJSON) {
		return "[]"
	}
	ops := opcionesConsulta(p)
	textos := make([]string, len(ops))
	for i, o := range ops {
		textos[i] = textoTorre(p.Texto, o)
	}
	b, _ := json.Marshal(textos)
	return string(b)
}

// InstalarTorresL2 recibe las n torres (n·d float32 little endian, una por texto de TextosTorreL2), las cuantiza y las
// cachea con claveTorre; false si no cuadran (n, d, valores no finitos) o no hay L2.
func (c *Chispa) InstalarTorresL2(preguntaJSON string, torres []byte, n int) bool {
	p, err := leerPregunta(preguntaJSON)
	if err != nil || !c.tieneL2 {
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
	for _, o := range ops {
		claves[claveTorre(p.Texto, o)] = true
	}
	// LRU: se desalojan las más antiguas, nunca las de esta instalación ni las de otro hilo recién instaladas.
	for len(c.dyn)+n > maxDin {
		var viejo string
		var min uint64
		for k := range c.dyn {
			if claves[k] {
				continue
			}
			if u := c.dynUso[k]; viejo == "" || u < min {
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
		k := claveTorre(p.Texto, o)
		c.dynTic++
		c.dyn[k], c.dynUso[k] = nuevas[i], c.dynTic
	}
	return true
}
