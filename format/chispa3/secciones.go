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
	// TauL2EsquemaNuevo es el τ de L2 para preguntas cuyas torres no están en ESQUEMAS (salen al vuelo); nil = L2 usa su τ de siempre.
	TauL2EsquemaNuevo *float64 `json:"tau_l2_esquema_nuevo,omitempty"`
	// L1LambdaCalib es el λ de encogimiento del soporte (SOPL1) con el que se calibró el τ de L1; nil = calibrado sin encogimiento.
	L1LambdaCalib *float64 `json:"l1_lambda_calib,omitempty"`
	// TiposL2 es el espacio de nombres de L2 y L2c (mismo formato que Tipos: choice, noul, scoreK, scoreK#j, multi_l2@…); nil = L2 lee Tipos.
	// L1 lee siempre Tipos.
	TiposL2 map[string]ParamsTipo `json:"tipos_l2,omitempty"`
	// TauEscalateL2 es el tau_escalate de L2; nil = L2 usa TauEscalate.
	TauEscalateL2 *float64 `json:"tau_escalate_l2,omitempty"`
}

// ParaL2 devuelve la CALIB tal como la ve L2: con TiposL2 en lugar de Tipos y TauEscalateL2 en lugar de TauEscalate si el fichero los trae.
// Sin ellos devuelve c tal cual (los ficheros anteriores deciden igual).
func (c Calib) ParaL2() Calib {
	if c.TiposL2 != nil {
		c.Tipos = c.TiposL2
	}
	if c.TauEscalateL2 != nil {
		c.TauEscalate = *c.TauEscalateL2
	}
	return c
}

// MarshalJSON escribe tipos_l2 siempre que TiposL2 no sea nil, también vacío ({}): un mapa vacío significa
// «L2 no mira tipos», distinto de la ausencia del campo.
func (c Calib) MarshalJSON() ([]byte, error) {
	type plano Calib
	return json.Marshal(struct {
		plano
		TiposL2 *map[string]ParamsTipo `json:"tipos_l2,omitempty"`
	}{plano: plano(c), TiposL2: func() *map[string]ParamsTipo {
		if c.TiposL2 == nil {
			return nil
		}
		return &c.TiposL2
	}()})
}

func (c Calib) validar() error {
	if !(c.TauEscalate >= 0 && c.TauEscalate <= 1) {
		return fmt.Errorf("%w: CALIB.tau_escalate %v", ErrContenido, c.TauEscalate)
	}
	if c.TauL2c != nil && !(*c.TauL2c >= 0 && *c.TauL2c <= 1) {
		return fmt.Errorf("%w: CALIB.tau_l2c %v", ErrContenido, *c.TauL2c)
	}
	if c.TauL2EsquemaNuevo != nil && !(*c.TauL2EsquemaNuevo >= 0 && *c.TauL2EsquemaNuevo <= 1) {
		return fmt.Errorf("%w: CALIB.tau_l2_esquema_nuevo %v", ErrContenido, *c.TauL2EsquemaNuevo)
	}
	if c.TauEscalateL2 != nil && !(*c.TauEscalateL2 >= 0 && *c.TauEscalateL2 <= 1) {
		return fmt.Errorf("%w: CALIB.tau_escalate_l2 %v", ErrContenido, *c.TauEscalateL2)
	}
	if c.L1LambdaCalib != nil && !(*c.L1LambdaCalib >= 0) {
		return fmt.Errorf("%w: CALIB.l1_lambda_calib %v", ErrContenido, *c.L1LambdaCalib)
	}
	for campo, m := range map[string]map[string]ParamsTipo{"tipos": c.Tipos, "tipos_l2": c.TiposL2} {
		for k, p := range m {
			if !(p.T > 0) || math.IsInf(p.T, 0) || math.IsNaN(p.A) || math.IsInf(p.A, 0) ||
				math.IsNaN(p.B) || math.IsInf(p.B, 0) || !(p.Theta >= 0 && p.Theta <= 1) {
				return fmt.Errorf("%w: CALIB.%s[%q] fuera de rango", ErrContenido, campo, k)
			}
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

// ESQUEMAS v2: la primera palabra es versión<<16 | dim (en v1 es dim ≤ 4096, o sea versión 0 = v1) y las claves son
// HashEsquema2 (16 bytes). Resto igual: u32 (versión<<16|dim) · u32 n · n×[16]byte clave (estrictamente crecientes) ·
// n×f32 escala · n×dim×int8.
const EsquemasVersion2 = 2

// EntradaEsquema es una torre de opción cuantizada: vector int8 y su escala.
type EntradaEsquema struct {
	Hash   [32]byte
	Escala float32
	Vec    []int8
}

// CodificarEsquemas serializa las entradas (ordena por hash; todas con la misma dimensión).
func CodificarEsquemas(dim int, es []EntradaEsquema) ([]byte, error) {
	cs := make([]entradaClave, len(es))
	for i, e := range es {
		cs[i] = entradaClave{e.Hash[:], e.Escala, e.Vec}
	}
	return codificarEsquemas(dim, 32, 0, cs)
}

// EntradaEsquema2 es una torre de ESQUEMAS v2: la clave es HashEsquema2.
type EntradaEsquema2 struct {
	Hash   [16]byte
	Escala float32
	Vec    []int8
}

// CodificarEsquemas2 serializa ESQUEMAS v2 (ordena por clave).
func CodificarEsquemas2(dim int, es []EntradaEsquema2) ([]byte, error) {
	cs := make([]entradaClave, len(es))
	for i, e := range es {
		cs[i] = entradaClave{e.Hash[:], e.Escala, e.Vec}
	}
	return codificarEsquemas(dim, 16, EsquemasVersion2, cs)
}

type entradaClave struct {
	hash   []byte
	escala float32
	vec    []int8
}

func codificarEsquemas(dim, w int, ver uint32, es []entradaClave) ([]byte, error) {
	if dim < 1 || dim > maxEsqDim || len(es) > maxEsqN {
		return nil, fmt.Errorf("%w: ESQUEMAS dim=%d n=%d", ErrContenido, dim, len(es))
	}
	s := append([]entradaClave(nil), es...)
	sort.Slice(s, func(i, j int) bool { return bytes.Compare(s[i].hash, s[j].hash) < 0 })
	n := len(s)
	b := make([]byte, 8+n*(w+4+dim))
	binary.LittleEndian.PutUint32(b[0:], ver<<16|uint32(dim))
	binary.LittleEndian.PutUint32(b[4:], uint32(n))
	hs, ss, vs := 8, 8+w*n, 8+(w+4)*n
	for i, e := range s {
		if len(e.vec) != dim || !(e.escala >= 0) || math.IsInf(float64(e.escala), 0) {
			return nil, fmt.Errorf("%w: ESQUEMAS entrada %d", ErrContenido, i)
		}
		if i > 0 && bytes.Equal(s[i-1].hash, e.hash) {
			return nil, fmt.Errorf("%w: ESQUEMAS hash repetido", ErrContenido)
		}
		copy(b[hs+w*i:], e.hash)
		binary.LittleEndian.PutUint32(b[ss+4*i:], math.Float32bits(e.escala))
		for j, v := range e.vec {
			b[vs+i*dim+j] = byte(v)
		}
	}
	return b, nil
}

// Esquemas es la tabla de torres de opción, validada, sobre los bytes de la sección (sin copiar).
type Esquemas struct {
	dim, n int
	ver    int // 1 (claves de 32 bytes, HashEsquema) o 2 (16 bytes, HashEsquema2)
	w      int // ancho de la clave
	b      []byte
}

func DecodificarEsquemas(b []byte) (*Esquemas, error) {
	if len(b) < 8 {
		return nil, fmt.Errorf("%w: ESQUEMAS truncado", ErrContenido)
	}
	w0 := binary.LittleEndian.Uint32(b[0:])
	ver, w := 1, 32
	switch w0 >> 16 {
	case 0:
	case EsquemasVersion2:
		ver, w = 2, 16
	default:
		return nil, fmt.Errorf("%w: ESQUEMAS versión %d", ErrContenido, w0>>16)
	}
	dim := uint64(w0 & 0xffff)
	n := uint64(binary.LittleEndian.Uint32(b[4:]))
	if dim < 1 || dim > maxEsqDim || n > maxEsqN {
		return nil, fmt.Errorf("%w: ESQUEMAS dim=%d n=%d", ErrContenido, dim, n)
	}
	if want := 8 + n*(uint64(w)+4+dim); want != uint64(len(b)) { // ≤ 8 + 2^24·4132: no desborda
		return nil, fmt.Errorf("%w: ESQUEMAS mide %d y debería medir %d", ErrContenido, len(b), want)
	}
	e := &Esquemas{dim: int(dim), n: int(n), ver: ver, w: w, b: b}
	ss := 8 + w*e.n
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

func (e *Esquemas) hash(i int) []byte { return e.b[8+e.w*i : 8+e.w*i+e.w] }

func (e *Esquemas) Dim() int { return e.dim }
func (e *Esquemas) Len() int { return e.n }

// Version es la versión de la sección (1 o 2): el runtime elige la función de clave con ella.
func (e *Esquemas) Version() int { return e.ver }

// Buscar devuelve el vector (bytes int8 en crudo, sin copiar) y la escala de un hash v1 (HashEsquema).
// En una sección v2 no encuentra nada: las claves de las dos versiones no se mezclan.
func (e *Esquemas) Buscar(h [32]byte) (vec []byte, escala float32, ok bool) {
	if e.ver != 1 {
		return nil, 0, false
	}
	return e.buscar(h[:])
}

// Buscar2 es Buscar con una clave HashEsquema2; no encuentra nada en una sección v1.
func (e *Esquemas) Buscar2(h [16]byte) (vec []byte, escala float32, ok bool) {
	if e.ver != 2 {
		return nil, 0, false
	}
	return e.buscar(h[:])
}

func (e *Esquemas) buscar(h []byte) (vec []byte, escala float32, ok bool) {
	i := sort.Search(e.n, func(i int) bool { return bytes.Compare(e.hash(i), h) >= 0 })
	if i == e.n || !bytes.Equal(e.hash(i), h) {
		return nil, 0, false
	}
	vs := 8 + (e.w+4)*e.n + i*e.dim
	return e.b[vs : vs+e.dim : vs+e.dim], math.Float32frombits(binary.LittleEndian.Uint32(e.b[8+e.w*e.n+4*i:])), true
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
