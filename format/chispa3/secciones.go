package chispa3

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"sort"
)

// ---- META ----

// Meta es el contenido de la sección META (JSON).
type Meta struct {
	Version   int               `json:"version"`
	Tareas    []string          `json:"tareas"`
	Licencias map[string]string `json:"licencias"`
	Dorado    string            `json:"dorado"` // sha256 hex del dorado
}

func (m Meta) Codificar() ([]byte, error) {
	if err := m.validar(); err != nil {
		return nil, err
	}
	return json.Marshal(m)
}

func (m Meta) validar() error {
	if m.Version < 1 {
		return fmt.Errorf("%w: META.version %d", ErrContenido, m.Version)
	}
	if m.Dorado != "" && !esSHAHex(m.Dorado) {
		return fmt.Errorf("%w: META.dorado no es un sha256 hex", ErrContenido)
	}
	return nil
}

func esSHAHex(s string) bool {
	if len(s) != 64 {
		return false
	}
	for _, c := range s {
		if !(c >= '0' && c <= '9' || c >= 'a' && c <= 'f') {
			return false
		}
	}
	return true
}

func decodificarJSON(b []byte, dst any) error {
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if err := d.Decode(dst); err != nil {
		return fmt.Errorf("%w: %v", ErrContenido, err)
	}
	if d.More() {
		return fmt.Errorf("%w: datos tras el JSON", ErrContenido)
	}
	return nil
}

func DecodificarMeta(b []byte) (Meta, error) {
	var m Meta
	if err := decodificarJSON(b, &m); err != nil {
		return Meta{}, err
	}
	return m, m.validar()
}

func (f *Fichero) Meta() (Meta, error) {
	b, err := f.Bytes(META)
	if err != nil {
		return Meta{}, err
	}
	return DecodificarMeta(b)
}

// ---- CALIB ----

// ParamsTipo son T, a, b y θ de un tipo de pregunta.
type ParamsTipo struct {
	T     float64 `json:"T"` // temperatura, > 0
	A     float64 `json:"a"`
	B     float64 `json:"b"`
	Theta float64 `json:"theta"` // umbral en [0,1]
}

// Calib es el contenido de la sección CALIB (JSON).
type Calib struct {
	Tipos       map[string]ParamsTipo `json:"tipos"`
	TauEscalate float64               `json:"tau_escalate"` // en [0,1]
	// TauL2c es el τ de la cabeza conjunta (L2c), fuera de pliegue; nil = el fichero no lo trae y L2c usa TauEscalate.
	TauL2c *float64 `json:"tau_l2c,omitempty"`
}

func (c Calib) validar() error {
	if !(c.TauEscalate >= 0 && c.TauEscalate <= 1) {
		return fmt.Errorf("%w: CALIB.tau_escalate %v", ErrContenido, c.TauEscalate)
	}
	if c.TauL2c != nil && !(*c.TauL2c >= 0 && *c.TauL2c <= 1) {
		return fmt.Errorf("%w: CALIB.tau_l2c %v", ErrContenido, *c.TauL2c)
	}
	for k, p := range c.Tipos {
		if !(p.T > 0) || math.IsInf(p.T, 0) || math.IsNaN(p.A) || math.IsInf(p.A, 0) ||
			math.IsNaN(p.B) || math.IsInf(p.B, 0) || !(p.Theta >= 0 && p.Theta <= 1) {
			return fmt.Errorf("%w: CALIB.tipos[%q] fuera de rango", ErrContenido, k)
		}
	}
	return nil
}

func (c Calib) Codificar() ([]byte, error) {
	if err := c.validar(); err != nil {
		return nil, err
	}
	return json.Marshal(c)
}

func DecodificarCalib(b []byte) (Calib, error) {
	var c Calib
	if err := decodificarJSON(b, &c); err != nil {
		return Calib{}, err
	}
	return c, c.validar()
}

func (f *Fichero) Calib() (Calib, error) {
	b, err := f.Bytes(CALIB)
	if err != nil {
		return Calib{}, err
	}
	return DecodificarCalib(b)
}

// ---- ESQUEMAS ----

// Disposición (little endian), de estructura de arrays para que los vectores sean contiguos:
//
//	u32 dim · u32 n · n×[32]byte hash (estrictamente crecientes) · n×f32 escala · n×dim×int8
const (
	maxEsqDim = 4096
	maxEsqN   = 1 << 24
)

// HashEsquema es el hash de una pregunta y sus opciones (con prefijos de longitud, sin ambigüedad).
func HashEsquema(pregunta string, opciones []string) [32]byte {
	h := sha256.New()
	var n [8]byte
	w := func(s string) {
		binary.LittleEndian.PutUint64(n[:], uint64(len(s)))
		h.Write(n[:])
		h.Write([]byte(s))
	}
	w(pregunta)
	binary.LittleEndian.PutUint64(n[:], uint64(len(opciones)))
	h.Write(n[:])
	for _, o := range opciones {
		w(o)
	}
	var out [32]byte
	h.Sum(out[:0])
	return out
}

// EntradaEsquema es una torre de opción cuantizada: vector int8 y su escala.
type EntradaEsquema struct {
	Hash   [32]byte
	Escala float32
	Vec    []int8
}

// CodificarEsquemas serializa las entradas (ordena por hash; todas con la misma dimensión).
func CodificarEsquemas(dim int, es []EntradaEsquema) ([]byte, error) {
	if dim < 1 || dim > maxEsqDim || len(es) > maxEsqN {
		return nil, fmt.Errorf("%w: ESQUEMAS dim=%d n=%d", ErrContenido, dim, len(es))
	}
	s := append([]EntradaEsquema(nil), es...)
	sort.Slice(s, func(i, j int) bool { return bytes.Compare(s[i].Hash[:], s[j].Hash[:]) < 0 })
	n := len(s)
	b := make([]byte, 8+n*(32+4+dim))
	binary.LittleEndian.PutUint32(b[0:], uint32(dim))
	binary.LittleEndian.PutUint32(b[4:], uint32(n))
	hs, ss, vs := 8, 8+32*n, 8+36*n
	for i, e := range s {
		if len(e.Vec) != dim || !(e.Escala >= 0) || math.IsInf(float64(e.Escala), 0) {
			return nil, fmt.Errorf("%w: ESQUEMAS entrada %d", ErrContenido, i)
		}
		if i > 0 && s[i-1].Hash == e.Hash {
			return nil, fmt.Errorf("%w: ESQUEMAS hash repetido", ErrContenido)
		}
		copy(b[hs+32*i:], e.Hash[:])
		binary.LittleEndian.PutUint32(b[ss+4*i:], math.Float32bits(e.Escala))
		for j, v := range e.Vec {
			b[vs+i*dim+j] = byte(v)
		}
	}
	return b, nil
}

// Esquemas es la tabla de torres de opción, validada, sobre los bytes de la sección (sin copiar).
type Esquemas struct {
	dim, n int
	b      []byte
}

func DecodificarEsquemas(b []byte) (*Esquemas, error) {
	if len(b) < 8 {
		return nil, fmt.Errorf("%w: ESQUEMAS truncado", ErrContenido)
	}
	dim := uint64(binary.LittleEndian.Uint32(b[0:]))
	n := uint64(binary.LittleEndian.Uint32(b[4:]))
	if dim < 1 || dim > maxEsqDim || n > maxEsqN {
		return nil, fmt.Errorf("%w: ESQUEMAS dim=%d n=%d", ErrContenido, dim, n)
	}
	if want := 8 + n*(36+dim); want != uint64(len(b)) { // ≤ 8 + 2^24·4132: no desborda
		return nil, fmt.Errorf("%w: ESQUEMAS mide %d y debería medir %d", ErrContenido, len(b), want)
	}
	e := &Esquemas{dim: int(dim), n: int(n), b: b}
	ss := 8 + 32*e.n
	for i := 0; i < e.n; i++ {
		if i > 0 && bytes.Compare(e.hash(i-1), e.hash(i)) >= 0 {
			return nil, fmt.Errorf("%w: ESQUEMAS hashes no crecientes", ErrContenido)
		}
		s := math.Float32frombits(binary.LittleEndian.Uint32(b[ss+4*i:]))
		if !(s >= 0) || math.IsInf(float64(s), 0) {
			return nil, fmt.Errorf("%w: ESQUEMAS escala %d", ErrContenido, i)
		}
	}
	return e, nil
}

func (e *Esquemas) hash(i int) []byte { return e.b[8+32*i : 8+32*i+32] }

func (e *Esquemas) Dim() int { return e.dim }
func (e *Esquemas) Len() int { return e.n }

// Buscar devuelve el vector (bytes int8 en crudo, sin copiar) y la escala de un hash.
func (e *Esquemas) Buscar(h [32]byte) (vec []byte, escala float32, ok bool) {
	i := sort.Search(e.n, func(i int) bool { return bytes.Compare(e.hash(i), h[:]) >= 0 })
	if i == e.n || !bytes.Equal(e.hash(i), h[:]) {
		return nil, 0, false
	}
	vs := 8 + 36*e.n + i*e.dim
	return e.b[vs : vs+e.dim : vs+e.dim], math.Float32frombits(binary.LittleEndian.Uint32(e.b[8+32*e.n+4*i:])), true
}

func (f *Fichero) Esquemas() (*Esquemas, error) {
	b, err := f.Bytes(ESQUEMAS)
	if err != nil {
		return nil, err
	}
	return DecodificarEsquemas(b)
}

// ---- L1 y L2 ----

// La sección L1 es el .chispa-l1 de runtime/l1 (versión 1) tal cual: sus offsets absolutos (desde el
// inicio de su fichero) son ya relativos al inicio de la sección, así que l1.Desde(f.L1()) funciona
// sin cambios. El sha256 de la sección sustituye al del cuerpo.
const (
	l1Cabecera  = 256
	l1Secciones = 9
)

var l1Magia = []byte{'C', 'H', 'L', '1', 0, 0, 0, 0}

// ValidarL1 comprueba la cabecera del .chispa-l1 y que sus 9 secciones caigan dentro de b.
func ValidarL1(b []byte) error {
	if len(b) < l1Cabecera || !bytes.Equal(b[:8], l1Magia) {
		return fmt.Errorf("%w: L1 no es un .chispa-l1", ErrContenido)
	}
	le := binary.LittleEndian
	if v := le.Uint32(b[8:]); v != 1 {
		return fmt.Errorf("%w: L1 versión %d", ErrContenido, v)
	}
	if le.Uint32(b[12:]) == 0 || le.Uint32(b[16:]) == 0 {
		return fmt.Errorf("%w: L1 dim o vocabulario cero", ErrContenido)
	}
	tam := uint64(len(b))
	for i := 0; i < l1Secciones; i++ {
		o, l := le.Uint64(b[36+16*i:]), le.Uint64(b[44+16*i:])
		if o < l1Cabecera || o > tam || l > tam-o {
			return fmt.Errorf("%w: L1 sección %d fuera de rango", ErrContenido, i)
		}
	}
	return nil
}

// L1 devuelve el .chispa-l1 (validada su cabecera), listo para l1.Desde.
func (f *Fichero) L1() ([]byte, error) {
	b, err := f.Bytes(L1)
	if err != nil {
		return nil, err
	}
	if err := ValidarL1(b); err != nil {
		return nil, err
	}
	return b, nil
}

// L2 devuelve el ONNX int8 como blob.
func (f *Fichero) L2() ([]byte, error) { return f.Bytes(L2) }
