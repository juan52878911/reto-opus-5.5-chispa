package chispa3

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"math"
	"sort"
	"strings"
	"sync"
	"unicode"
	"unicode/utf8"
)

// ---- L0TF ----

// L0 TF-IDF de caracteres con regresión logística multinomial (T4.5c): reproduce
// `TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, lowercase=True)` +
// `LogisticRegression(C=10)` de sklearn (`model/lineas_base/correr.py`). El analizador está fijo en la versión 1.
//
// Disposición (little endian, sin relleno):
//
//	u32 versión (1) · u32 V · u32 C · u32 dtype (1 = f32, 2 = f16) ·
//	C×(u16 len · bytes UTF-8) etiquetas, estrictamente crecientes (el orden de classes_) ·
//	C×f32 intercepciones · V×f32 idf · (V+1)×u32 desplazamientos del vocabulario (desde 0, estrictamente crecientes) ·
//	blob con los V n-gramas en UTF-8, estrictamente crecientes por bytes (2 a 5 puntos de código cada uno) ·
//	V·C coeficientes del dtype, por n-grama (coef[f·C + c]).
//
// El vocabulario va en cadenas y no en hashes: la búsqueda es exacta (binaria, sin copiar), sin colisiones que
// mezclen coeficientes de n-gramas distintos, y cuesta unos pocos bytes por n-grama frente a los C·dtype de sus coeficientes.
// Con 2 clases, sklearn guarda una sola fila (sigmoide): el escritor la expande a [0, w] e intercepción [0, b].
const (
	L0TFVersion = 1
	L0TFF32     = 1
	L0TFF16     = 2
	maxL0TFV    = 1 << 24
	maxL0TFC    = 1 << 16
	minNGrama   = 2
	maxNGrama   = 5
)

// DatosL0TF es el contenido de la sección en memoria. Coef son V·C valores, un n-grama tras otro.
// Con F16 se redondean al valor f16 más cercano al codificar (los de la lectura ya son exactos).
type DatosL0TF struct {
	Etiquetas []string
	Vocab     []string
	IDF       []float32
	Inter     []float32
	Coef      []float32
	F16       bool
}

func (d *DatosL0TF) validar() error {
	v, c := len(d.Vocab), len(d.Etiquetas)
	if c < 2 || c > maxL0TFC || v < 1 || v > maxL0TFV {
		return fmt.Errorf("%w: L0TF V=%d C=%d", ErrContenido, v, c)
	}
	if len(d.IDF) != v || len(d.Inter) != c || uint64(len(d.Coef)) != uint64(v)*uint64(c) {
		return fmt.Errorf("%w: L0TF tamaños idf=%d inter=%d coef=%d", ErrContenido, len(d.IDF), len(d.Inter), len(d.Coef))
	}
	for i, n := range d.Etiquetas {
		if len(n) > math.MaxUint16 || !utf8.ValidString(n) || (i > 0 && d.Etiquetas[i-1] >= n) {
			return fmt.Errorf("%w: L0TF etiqueta %d", ErrContenido, i)
		}
	}
	for i, g := range d.Vocab {
		if r := utf8.RuneCountInString(g); r < minNGrama || r > maxNGrama || !utf8.ValidString(g) || (i > 0 && d.Vocab[i-1] >= g) {
			return fmt.Errorf("%w: L0TF n-grama %d", ErrContenido, i)
		}
	}
	for _, x := range d.IDF {
		if !(x > 0) || !finito32(x) {
			return fmt.Errorf("%w: L0TF idf %v", ErrContenido, x)
		}
	}
	for _, x := range d.Inter {
		if !finito32(x) {
			return fmt.Errorf("%w: L0TF intercepción no finita", ErrContenido)
		}
	}
	for _, x := range d.Coef {
		if !finito32(x) || (d.F16 && !finito32(f16aF32(f32aF16(x)))) {
			return fmt.Errorf("%w: L0TF coeficiente %v", ErrContenido, x)
		}
	}
	return nil
}

// CodificarL0TF serializa la sección.
func CodificarL0TF(d *DatosL0TF) ([]byte, error) {
	if err := d.validar(); err != nil {
		return nil, err
	}
	le := binary.LittleEndian
	dt, tam := uint32(L0TFF32), 4
	if d.F16 {
		dt, tam = L0TFF16, 2
	}
	b := make([]byte, 0, 16+len(d.Coef)*tam+len(d.Vocab)*16)
	for _, v := range []uint32{L0TFVersion, uint32(len(d.Vocab)), uint32(len(d.Etiquetas)), dt} {
		b = le.AppendUint32(b, v)
	}
	for _, n := range d.Etiquetas {
		b = le.AppendUint16(b, uint16(len(n)))
		b = append(b, n...)
	}
	for _, x := range d.Inter {
		b = le.AppendUint32(b, math.Float32bits(x))
	}
	for _, x := range d.IDF {
		b = le.AppendUint32(b, math.Float32bits(x))
	}
	var fin uint64
	b = le.AppendUint32(b, 0)
	for _, g := range d.Vocab {
		fin += uint64(len(g))
		if fin > math.MaxUint32 {
			return nil, fmt.Errorf("%w: L0TF vocabulario de más de 4 GiB", ErrContenido)
		}
		b = le.AppendUint32(b, uint32(fin))
	}
	for _, g := range d.Vocab {
		b = append(b, g...)
	}
	for _, x := range d.Coef {
		if d.F16 {
			b = le.AppendUint16(b, f32aF16(x))
		} else {
			b = le.AppendUint32(b, math.Float32bits(x))
		}
	}
	return b, nil
}

// L0TFModelo es la sección validada, sin copiar los datos.
type L0TFModelo struct {
	Etiquetas []string
	v, c      int
	f16       bool
	inter     []float64
	idf       []byte // V×f32
	offs      []byte // (V+1)×u32
	blob      []byte
	coef      []byte
}

// DecodificarL0TF valida la sección entera (rangos, orden del vocabulario, valores finitos).
func DecodificarL0TF(b []byte) (*L0TFModelo, error) {
	l := &lector{b: b}
	if v := l.u32(); l.err == nil && v != L0TFVersion {
		return nil, fmt.Errorf("%w: L0TF versión %d", ErrContenido, v)
	}
	v, c, dt := uint64(l.u32()), uint64(l.u32()), l.u32()
	if l.err != nil {
		return nil, l.err
	}
	if c < 2 || c > maxL0TFC || v < 1 || v > maxL0TFV || (dt != L0TFF32 && dt != L0TFF16) {
		return nil, fmt.Errorf("%w: L0TF V=%d C=%d dtype=%d", ErrContenido, v, c, dt)
	}
	m := &L0TFModelo{v: int(v), c: int(c), f16: dt == L0TFF16}
	m.Etiquetas = make([]string, 0, min(int(c), len(l.b)/2))
	for j := uint64(0); j < c && l.err == nil; j++ {
		ln := l.toma(2)
		if ln == nil {
			break
		}
		n := l.toma(uint64(binary.LittleEndian.Uint16(ln)))
		if l.err == nil && (!utf8.Valid(n) || (j > 0 && m.Etiquetas[j-1] >= string(n))) {
			l.err = fmt.Errorf("%w: L0TF etiqueta %d", ErrContenido, j)
		}
		m.Etiquetas = append(m.Etiquetas, string(n))
	}
	inter := l.toma(c * 4)
	m.idf = l.toma(v * 4)
	m.offs = l.toma((v + 1) * 4)
	if l.err != nil {
		return nil, l.err
	}
	le := binary.LittleEndian
	m.inter = make([]float64, c)
	for i := range m.inter {
		x := math.Float32frombits(le.Uint32(inter[4*i:]))
		if !finito32(x) {
			return nil, fmt.Errorf("%w: L0TF intercepción no finita", ErrContenido)
		}
		m.inter[i] = float64(x)
	}
	for i := uint64(0); i < v; i++ {
		if x := math.Float32frombits(le.Uint32(m.idf[4*i:])); !(x > 0) || !finito32(x) {
			return nil, fmt.Errorf("%w: L0TF idf %v", ErrContenido, x)
		}
	}
	if le.Uint32(m.offs) != 0 {
		return nil, fmt.Errorf("%w: L0TF desplazamientos", ErrContenido)
	}
	fin := uint64(le.Uint32(m.offs[4*v:]))
	m.blob = l.toma(fin)
	tam := uint64(4)
	if m.f16 {
		tam = 2
	}
	m.coef = l.toma(v * c * tam) // v·c ≤ 2^40: no desborda
	if l.err != nil {
		return nil, l.err
	}
	if len(l.b) != 0 {
		return nil, fmt.Errorf("%w: L0TF con %d bytes sobrantes", ErrContenido, len(l.b))
	}
	var prev []byte
	for i := 0; i < m.v; i++ {
		a, z := le.Uint32(m.offs[4*i:]), le.Uint32(m.offs[4*i+4:])
		if a >= z || uint64(z) > fin {
			return nil, fmt.Errorf("%w: L0TF desplazamiento %d", ErrContenido, i)
		}
		g := m.blob[a:z]
		if r := utf8.RuneCount(g); r < minNGrama || r > maxNGrama || !utf8.Valid(g) || (i > 0 && bytes.Compare(prev, g) >= 0) {
			return nil, fmt.Errorf("%w: L0TF n-grama %d", ErrContenido, i)
		}
		prev = g
	}
	if fin != uint64(len(m.blob)) {
		return nil, fmt.Errorf("%w: L0TF vocabulario", ErrContenido)
	}
	if m.f16 {
		for i := 0; i < len(m.coef); i += 2 {
			if le.Uint16(m.coef[i:])>>10&0x1f == 0x1f {
				return nil, fmt.Errorf("%w: L0TF coeficiente no finito", ErrContenido)
			}
		}
	} else {
		for i := 0; i < len(m.coef); i += 4 {
			if !finito32(math.Float32frombits(le.Uint32(m.coef[i:]))) {
				return nil, fmt.Errorf("%w: L0TF coeficiente no finito", ErrContenido)
			}
		}
	}
	return m, nil
}

// L0TF devuelve la sección L0TF validada; ErrNoHay si el fichero no la tiene.
func (f *Fichero) L0TF() (*L0TFModelo, error) {
	b, err := f.Bytes(L0TF)
	if err != nil {
		return nil, err
	}
	return DecodificarL0TF(b)
}

func (m *L0TFModelo) NumNGramas() int { return m.v }
func (m *L0TFModelo) NumClases() int  { return m.c }

// Datos expande el modelo (para recodificarlo): idéntico bit a bit al leído.
func (m *L0TFModelo) Datos() *DatosL0TF {
	le := binary.LittleEndian
	d := &DatosL0TF{Etiquetas: append([]string(nil), m.Etiquetas...), F16: m.f16,
		Vocab: make([]string, m.v), IDF: make([]float32, m.v), Inter: make([]float32, m.c), Coef: make([]float32, m.v*m.c)}
	for i := range d.Vocab {
		d.Vocab[i] = string(m.nGrama(i))
		d.IDF[i] = math.Float32frombits(le.Uint32(m.idf[4*i:]))
	}
	for i := range d.Inter {
		d.Inter[i] = float32(m.inter[i])
	}
	for i := range d.Coef {
		d.Coef[i] = m.coefAt(i)
	}
	return d
}

func (m *L0TFModelo) nGrama(i int) []byte {
	le := binary.LittleEndian
	return m.blob[le.Uint32(m.offs[4*i:]):le.Uint32(m.offs[4*i+4:])]
}

func (m *L0TFModelo) coefAt(i int) float32 {
	if m.f16 {
		return tablaF16()[binary.LittleEndian.Uint16(m.coef[2*i:])]
	}
	return math.Float32frombits(binary.LittleEndian.Uint32(m.coef[4*i:]))
}

// buscar devuelve el índice del n-grama o -1.
func (m *L0TFModelo) buscar(g string) int {
	i := sort.Search(m.v, func(i int) bool { return string(m.nGrama(i)) >= g })
	if i < m.v && string(m.nGrama(i)) == g {
		return i
	}
	return -1
}

// Probs devuelve P(clase | texto) en el orden de Etiquetas, como predict_proba de sklearn.
func (m *L0TFModelo) Probs(texto string) []float64 {
	idx := m.nGramas(texto)
	sort.Slice(idx, func(i, j int) bool { return idx[i] < idx[j] })
	le := binary.LittleEndian
	z := append([]float64(nil), m.inter...)
	// Una pasada para la norma l2 y otra para acumular los logits.
	type par struct {
		f int
		x float64
	}
	var ps []par
	var norma float64
	for i := 0; i < len(idx); {
		j := i
		for j < len(idx) && idx[j] == idx[i] {
			j++
		}
		x := (1 + math.Log(float64(j-i))) * float64(math.Float32frombits(le.Uint32(m.idf[4*idx[i]:])))
		ps = append(ps, par{int(idx[i]), x})
		norma += x * x
		i = j
	}
	if norma > 0 {
		norma = math.Sqrt(norma)
		for _, p := range ps {
			x, base := p.x/norma, p.f*m.c
			if m.f16 {
				t := tablaF16()
				for c := range z {
					z[c] += x * float64(t[le.Uint16(m.coef[2*(base+c):])])
				}
			} else {
				for c := range z {
					z[c] += x * float64(math.Float32frombits(le.Uint32(m.coef[4*(base+c):])))
				}
			}
		}
	}
	mx := z[0]
	for _, x := range z {
		mx = max(mx, x)
	}
	var s float64
	for c := range z {
		z[c] = math.Exp(z[c] - mx)
		s += z[c]
	}
	for c := range z {
		z[c] /= s
	}
	return z
}

// nGramas devuelve los índices (con repeticiones) de los n-gramas del texto que están en el vocabulario.
func (m *L0TFModelo) nGramas(texto string) []int32 {
	var out []int32
	var offs []int
	for _, w := range strings.FieldsFunc(minusculasPy(texto), esEspacioPy) {
		ws := " " + w + " "
		offs = offs[:0]
		for i := range ws {
			offs = append(offs, i)
		}
		l := len(offs)
		offs = append(offs, len(ws))
	porN:
		for n := minNGrama; n <= maxNGrama; n++ {
			// Como _char_wb_ngrams: una palabra de l ≤ n puntos de código cuenta una sola vez y corta los n mayores.
			for o := 0; ; o++ {
				if i := m.buscar(ws[offs[o]:offs[min(o+n, l)]]); i >= 0 {
					out = append(out, int32(i))
				}
				if o+n >= l {
					if o == 0 {
						break porN
					}
					break
				}
			}
		}
	}
	return out
}

// esEspacioPy es str.isspace de Python: unicode.IsSpace más los separadores U+001C a U+001F.
func esEspacioPy(r rune) bool { return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f) }

func cased(r rune) bool { return unicode.IsUpper(r) || unicode.IsLower(r) || unicode.IsTitle(r) }

func caseIgnorable(r rune) bool {
	return unicode.In(r, unicode.Mn, unicode.Me, unicode.Cf, unicode.Lm, unicode.Sk) || strings.ContainsRune("'.:·’‘․‧﹓﹒﹕＇．：", r)
}

// minusculasPy es str.lower() de Python: la minúscula simple de cada punto de código, salvo U+0130 (→ i + U+0307) y la
// sigma final (Σ → ς si sigue a una letra con caja y no la precede otra).
func minusculasPy(s string) string {
	var b strings.Builder
	b.Grow(len(s))
	rs := []rune(s)
	for i, r := range rs {
		switch {
		case r == 0x130:
			b.WriteString("i̇")
		case r == 'Σ':
			antes, despues := false, false
			for j := i - 1; j >= 0; j-- {
				if !caseIgnorable(rs[j]) {
					antes = cased(rs[j])
					break
				}
			}
			for j := i + 1; j < len(rs); j++ {
				if !caseIgnorable(rs[j]) {
					despues = cased(rs[j])
					break
				}
			}
			if antes && !despues {
				b.WriteRune('ς')
			} else {
				b.WriteRune('σ')
			}
		default:
			b.WriteRune(unicode.ToLower(r))
		}
	}
	return b.String()
}

var (
	f16Una  sync.Once
	f16Tabl []float32
)

func tablaF16() []float32 {
	f16Una.Do(func() {
		f16Tabl = make([]float32, 1<<16)
		for i := range f16Tabl {
			f16Tabl[i] = f16aF32(uint16(i))
		}
	})
	return f16Tabl
}

// f16aF32 convierte un half IEEE 754 (los infinitos y NaN dan ±Inf/NaN).
func f16aF32(h uint16) float32 {
	s := uint32(h>>15) << 31
	e, f := uint32(h>>10)&0x1f, uint32(h)&0x3ff
	switch {
	case e == 0x1f:
		return math.Float32frombits(s | 0x7f800000 | f<<13)
	case e == 0:
		x := float32(f) / (1 << 24)
		if s != 0 {
			x = -x
		}
		return x
	}
	return math.Float32frombits(s | (e+112)<<23 | f<<13)
}

// f32aF16 redondea al half más cercano (empates al par), saturando a ±Inf.
func f32aF16(x float32) uint16 {
	b := math.Float32bits(x)
	s := uint16(b>>16) & 0x8000
	e := int32(b>>23&0xff) - 127 + 15
	f := b & 0x7fffff
	switch {
	case b>>23&0xff == 0xff:
		if f != 0 {
			return s | 0x7e00
		}
		return s | 0x7c00
	case e >= 0x1f:
		return s | 0x7c00
	case e <= 0:
		if e < -10 {
			return s
		}
		f |= 0x800000
		sh := uint(14 - e)
		h := f >> sh
		if r := f & (1<<sh - 1); r > 1<<(sh-1) || (r == 1<<(sh-1) && h&1 == 1) {
			h++
		}
		return s | uint16(h)
	}
	h := uint32(e)<<10 | f>>13
	if r := f & 0x1fff; r > 0x1000 || (r == 0x1000 && h&1 == 1) {
		h++ // el acarreo puede llegar a Inf, que es lo correcto
	}
	return s | uint16(h)
}
