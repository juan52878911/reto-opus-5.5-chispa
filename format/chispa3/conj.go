package chispa3

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"math"
	"sort"
	"unicode/utf8"
)

// ---- CONJ ----

// Cabeza conjunta L0 + L2 por esquema (T2.6b). Disposición (little endian):
//
//	u32 versión (1) · u32 n · n entradas, con hash estrictamente creciente
//
// Entrada:
//
//	[32]byte hash (HashEsquema de la pregunta y los ids de las opciones ordenados) ·
//	u32 cabeza (1 = lr) · u32 K ranuras · u32 d · u32 C clases · u32 nw ·
//	f32 T · f32 β (los de L2: P_L2 = softmax((maxsim + β·simproto)/T)) ·
//	3×f32 esc (desviaciones de log P_L0, simproto y log P_L2) · nw×f32 pesos ·
//	C×(u16 len · bytes UTF-8) clases, estrictamente crecientes ·
//	C·K×f32 escala · C·K·d×int8 prototipos (cada ranura q·escala ≈ prototipo normalizado)
const (
	ConjVersion  = 1
	CabezaLR     = 1
	ConjPesosLR  = 6
	maxConjN     = 1 << 16
	maxConjK     = 64
	maxConjD     = 4096
	maxConjC     = 1 << 16
	conjFijoEntr = 32 + 5*4 + 2*4 + 3*4
)

// EntradaConj es la cabeza de un esquema. Proto son C·K·d bytes int8 en crudo (en la lectura apunta a la sección).
type EntradaConj struct {
	Hash    [32]byte
	Cabeza  uint32
	K, D    int
	T, Beta float32
	Esc     [3]float32
	W       []float32
	Clases  []string
	Escala  []float32 // C·K
	Proto   []byte    // C·K·d
}

func finito32(x float32) bool { return !math.IsNaN(float64(x)) && !math.IsInf(float64(x), 0) }

func (e *EntradaConj) validar() error {
	c := len(e.Clases)
	if e.Cabeza != CabezaLR || len(e.W) != ConjPesosLR {
		return fmt.Errorf("%w: CONJ cabeza %d con %d pesos", ErrContenido, e.Cabeza, len(e.W))
	}
	if e.K < 1 || e.K > maxConjK || e.D < 1 || e.D > maxConjD || c < 1 || c > maxConjC {
		return fmt.Errorf("%w: CONJ K=%d d=%d C=%d", ErrContenido, e.K, e.D, c)
	}
	if !(e.T > 0) || !finito32(e.T) || !finito32(e.Beta) {
		return fmt.Errorf("%w: CONJ T=%v β=%v", ErrContenido, e.T, e.Beta)
	}
	for _, x := range e.Esc {
		if !(x > 0) || !finito32(x) {
			return fmt.Errorf("%w: CONJ esc %v", ErrContenido, x)
		}
	}
	for _, x := range e.W {
		if !finito32(x) {
			return fmt.Errorf("%w: CONJ peso no finito", ErrContenido)
		}
	}
	for i, n := range e.Clases {
		if len(n) > math.MaxUint16 || !utf8.ValidString(n) || (i > 0 && e.Clases[i-1] >= n) {
			return fmt.Errorf("%w: CONJ clase %d", ErrContenido, i)
		}
	}
	if len(e.Escala) != c*e.K || len(e.Proto) != c*e.K*e.D {
		return fmt.Errorf("%w: CONJ prototipos de tamaño %d/%d", ErrContenido, len(e.Escala), len(e.Proto))
	}
	for _, x := range e.Escala {
		if !(x >= 0) || !finito32(x) {
			return fmt.Errorf("%w: CONJ escala %v", ErrContenido, x)
		}
	}
	return nil
}

// CodificarConj serializa las entradas (ordena por hash).
func CodificarConj(es []EntradaConj) ([]byte, error) {
	if len(es) > maxConjN {
		return nil, fmt.Errorf("%w: CONJ con %d entradas", ErrContenido, len(es))
	}
	s := append([]EntradaConj(nil), es...)
	sort.Slice(s, func(i, j int) bool { return bytes.Compare(s[i].Hash[:], s[j].Hash[:]) < 0 })
	le := binary.LittleEndian
	b := le.AppendUint32(nil, ConjVersion)
	b = le.AppendUint32(b, uint32(len(s)))
	for i := range s {
		e := &s[i]
		if err := e.validar(); err != nil {
			return nil, err
		}
		if i > 0 && s[i-1].Hash == e.Hash {
			return nil, fmt.Errorf("%w: CONJ hash repetido", ErrContenido)
		}
		b = append(b, e.Hash[:]...)
		for _, v := range []uint32{e.Cabeza, uint32(e.K), uint32(e.D), uint32(len(e.Clases)), uint32(len(e.W))} {
			b = le.AppendUint32(b, v)
		}
		for _, v := range append([]float32{e.T, e.Beta}, append(e.Esc[:], e.W...)...) {
			b = le.AppendUint32(b, math.Float32bits(v))
		}
		for _, n := range e.Clases {
			b = le.AppendUint16(b, uint16(len(n)))
			b = append(b, n...)
		}
		for _, v := range e.Escala {
			b = le.AppendUint32(b, math.Float32bits(v))
		}
		b = append(b, e.Proto...)
	}
	return b, nil
}

// Conj es la sección CONJ validada.
type Conj struct {
	es []EntradaConj
}

type lector struct {
	b   []byte
	err error
}

func (l *lector) toma(n uint64) []byte {
	if l.err != nil {
		return nil
	}
	if n > uint64(len(l.b)) {
		l.err = fmt.Errorf("%w: sección truncada", ErrContenido)
		return nil
	}
	x := l.b[:n:n]
	l.b = l.b[n:]
	return x
}

func (l *lector) u32() uint32 {
	if x := l.toma(4); x != nil {
		return binary.LittleEndian.Uint32(x)
	}
	return 0
}

func (l *lector) f32() float32 { return math.Float32frombits(l.u32()) }

func DecodificarConj(b []byte) (*Conj, error) {
	l := &lector{b: b}
	if v := l.u32(); l.err == nil && v != ConjVersion {
		return nil, fmt.Errorf("%w: CONJ versión %d", ErrContenido, v)
	}
	n := l.u32()
	if l.err != nil {
		return nil, l.err
	}
	// Cada entrada mide al menos conjFijoEntr bytes: acota n antes de reservar.
	if n > maxConjN || uint64(n)*conjFijoEntr > uint64(len(l.b)) {
		return nil, fmt.Errorf("%w: CONJ con %d entradas", ErrContenido, n)
	}
	c := &Conj{es: make([]EntradaConj, 0, n)}
	for i := uint32(0); i < n; i++ {
		var e EntradaConj
		copy(e.Hash[:], l.toma(32))
		e.Cabeza = l.u32()
		k, d, nc, nw := l.u32(), l.u32(), l.u32(), l.u32()
		if l.err != nil {
			return nil, l.err
		}
		if k > maxConjK || d > maxConjD || nc > maxConjC || nw > ConjPesosLR {
			return nil, fmt.Errorf("%w: CONJ K=%d d=%d C=%d nw=%d", ErrContenido, k, d, nc, nw)
		}
		e.K, e.D = int(k), int(d)
		e.T, e.Beta = l.f32(), l.f32()
		for j := range e.Esc {
			e.Esc[j] = l.f32()
		}
		e.W = make([]float32, nw)
		for j := range e.W {
			e.W[j] = l.f32()
		}
		e.Clases = make([]string, 0, min(int(nc), len(l.b)/2))
		for j := uint32(0); j < nc && l.err == nil; j++ {
			ln := l.toma(2)
			if ln == nil {
				break
			}
			e.Clases = append(e.Clases, string(l.toma(uint64(binary.LittleEndian.Uint16(ln)))))
		}
		ck := uint64(nc) * uint64(k)
		if l.err == nil && ck*4+ck*uint64(d) > uint64(len(l.b)) {
			l.err = fmt.Errorf("%w: sección truncada", ErrContenido)
		}
		if l.err != nil {
			return nil, l.err
		}
		e.Escala = make([]float32, ck)
		for j := range e.Escala {
			e.Escala[j] = l.f32()
		}
		e.Proto = l.toma(ck * uint64(d))
		if l.err != nil {
			return nil, l.err
		}
		if err := e.validar(); err != nil {
			return nil, err
		}
		if i > 0 && bytes.Compare(c.es[i-1].Hash[:], e.Hash[:]) >= 0 {
			return nil, fmt.Errorf("%w: CONJ hashes no crecientes", ErrContenido)
		}
		c.es = append(c.es, e)
	}
	if len(l.b) != 0 {
		return nil, fmt.Errorf("%w: CONJ con %d bytes sobrantes", ErrContenido, len(l.b))
	}
	return c, nil
}

func (c *Conj) Len() int { return len(c.es) }

// Buscar devuelve la cabeza de un esquema.
func (c *Conj) Buscar(h [32]byte) (*EntradaConj, bool) {
	i := sort.Search(len(c.es), func(i int) bool { return bytes.Compare(c.es[i].Hash[:], h[:]) >= 0 })
	if i == len(c.es) || c.es[i].Hash != h {
		return nil, false
	}
	return &c.es[i], true
}

// Conj devuelve la sección CONJ validada; ErrNoHay si el fichero no la tiene.
func (f *Fichero) Conj() (*Conj, error) {
	b, err := f.Bytes(CONJ)
	if err != nil {
		return nil, err
	}
	return DecodificarConj(b)
}
