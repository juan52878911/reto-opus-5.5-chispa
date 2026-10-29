package chispa3

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"math"
	"sort"
	"unicode/utf8"
)

// ---- SOPL1 ----

// SOPL1 es el soporte few-shot por pregunta y opción: cuántos ejemplos tiene cada opción (k) y la media de sus
// embeddings de L1. Con ella el runtime encoge el prototipo de la descripción hacia los ejemplos,
// p = normaliza((1−w)·p_desc + w·media), w = k/(k+λ) (PesoSoporte). El k de la sección también sirve a la mezcla de
// L2 (CONJ no lo guarda; la media de L2 sale de sus prototipos). Disposición (little endian):
//
//	u32 versión(1) · u32 dim · u32 n · n entradas con hash estrictamente creciente
//
// Entrada (hash = ClaveConj: HashEsquema de la pregunta y los ids de las opciones ordenados, la misma clave que CONJ):
//
//	[32]byte hash · u32 C · C×(u16 len · id UTF-8) estrictamente crecientes · C×u32 k · C×f32 escala · C×dim×int8 media
//
// La media va en int8 con escala máx|x|/127 por opción (como las torres de ESQUEMAS): 4× menos que f32 y el error de
// cuantización (≤ 0,4 % por componente) queda muy por debajo del ruido de unos pocos ejemplos. Una opción sin ejemplos
// lleva k=0, escala 0 y ceros.
const (
	Sopl1Version = 1
	maxSoplDim   = 4096
	maxSoplN     = 1 << 16
	maxSoplC     = 1 << 16
	soplFijoEntr = 32 + 4
)

// EntradaSopl1 es el soporte de una pregunta. Media son C·dim bytes int8 en crudo (en la lectura apunta a la sección).
type EntradaSopl1 struct {
	Hash   [32]byte
	Ids    []string // estrictamente crecientes
	K      []uint32
	Escala []float32
	Media  []int8
}

// CuantizarMedia cuantiza una media a int8 con escala máx|x|/127 (0 si es toda ceros), redondeo a par.
func CuantizarMedia(m []float32) (escala float32, q []int8) {
	q = make([]int8, len(m))
	var mx float32
	for _, x := range m {
		mx = max(mx, x, -x)
	}
	if mx == 0 {
		return 0, q
	}
	escala = mx / 127
	for i, x := range m {
		q[i] = int8(math.Max(-127, math.Min(127, math.RoundToEven(float64(x/escala)))))
	}
	return escala, q
}

func (e *EntradaSopl1) validar(dim int) error {
	c := len(e.Ids)
	if c < 1 || c > maxSoplC || len(e.K) != c || len(e.Escala) != c || len(e.Media) != c*dim {
		return fmt.Errorf("%w: SOPL1 entrada con C=%d k=%d escala=%d media=%d", ErrContenido, c, len(e.K), len(e.Escala), len(e.Media))
	}
	for i, n := range e.Ids {
		if len(n) > math.MaxUint16 || !utf8.ValidString(n) || (i > 0 && e.Ids[i-1] >= n) {
			return fmt.Errorf("%w: SOPL1 id %d", ErrContenido, i)
		}
	}
	for _, x := range e.Escala {
		if !(x >= 0) || !finito32(x) {
			return fmt.Errorf("%w: SOPL1 escala %v", ErrContenido, x)
		}
	}
	return nil
}

// CodificarSopl1 serializa las entradas (ordena por hash; todas con la misma dimensión).
func CodificarSopl1(dim int, es []EntradaSopl1) ([]byte, error) {
	if dim < 1 || dim > maxSoplDim || len(es) > maxSoplN {
		return nil, fmt.Errorf("%w: SOPL1 dim=%d n=%d", ErrContenido, dim, len(es))
	}
	s := append([]EntradaSopl1(nil), es...)
	sort.Slice(s, func(i, j int) bool { return bytes.Compare(s[i].Hash[:], s[j].Hash[:]) < 0 })
	le := binary.LittleEndian
	b := le.AppendUint32(nil, Sopl1Version)
	b = le.AppendUint32(b, uint32(dim))
	b = le.AppendUint32(b, uint32(len(s)))
	for i := range s {
		e := &s[i]
		if err := e.validar(dim); err != nil {
			return nil, err
		}
		if i > 0 && s[i-1].Hash == e.Hash {
			return nil, fmt.Errorf("%w: SOPL1 hash repetido", ErrContenido)
		}
		b = append(b, e.Hash[:]...)
		b = le.AppendUint32(b, uint32(len(e.Ids)))
		for _, n := range e.Ids {
			b = le.AppendUint16(b, uint16(len(n)))
			b = append(b, n...)
		}
		for _, k := range e.K {
			b = le.AppendUint32(b, k)
		}
		for _, x := range e.Escala {
			b = le.AppendUint32(b, math.Float32bits(x))
		}
		for _, v := range e.Media {
			b = append(b, byte(v))
		}
	}
	return b, nil
}

// Sopl1 es la sección SOPL1 validada.
type Sopl1 struct {
	dim int
	es  []EntradaSopl1
}

func DecodificarSopl1(b []byte) (*Sopl1, error) {
	l := &lector{b: b}
	if v := l.u32(); l.err == nil && v != Sopl1Version {
		return nil, fmt.Errorf("%w: SOPL1 versión %d", ErrContenido, v)
	}
	dim, n := l.u32(), l.u32()
	if l.err != nil {
		return nil, l.err
	}
	if dim < 1 || dim > maxSoplDim || n > maxSoplN || uint64(n)*soplFijoEntr > uint64(len(l.b)) {
		return nil, fmt.Errorf("%w: SOPL1 dim=%d n=%d", ErrContenido, dim, n)
	}
	s := &Sopl1{dim: int(dim), es: make([]EntradaSopl1, 0, n)}
	for i := uint32(0); i < n; i++ {
		var e EntradaSopl1
		copy(e.Hash[:], l.toma(32))
		nc := l.u32()
		if l.err != nil {
			return nil, l.err
		}
		if nc < 1 || nc > maxSoplC || uint64(nc)*(2+4+4+uint64(dim)) > uint64(len(l.b)) {
			return nil, fmt.Errorf("%w: SOPL1 C=%d", ErrContenido, nc)
		}
		e.Ids = make([]string, 0, nc)
		for j := uint32(0); j < nc && l.err == nil; j++ {
			ln := l.toma(2)
			if ln == nil {
				break
			}
			e.Ids = append(e.Ids, string(l.toma(uint64(binary.LittleEndian.Uint16(ln)))))
		}
		if l.err != nil {
			return nil, l.err
		}
		e.K = make([]uint32, nc)
		for j := range e.K {
			e.K[j] = l.u32()
		}
		e.Escala = make([]float32, nc)
		for j := range e.Escala {
			e.Escala[j] = l.f32()
		}
		m := l.toma(uint64(nc) * uint64(dim))
		if l.err != nil {
			return nil, l.err
		}
		e.Media = make([]int8, len(m))
		for j, v := range m {
			e.Media[j] = int8(v)
		}
		if err := e.validar(int(dim)); err != nil {
			return nil, err
		}
		if i > 0 && bytes.Compare(s.es[i-1].Hash[:], e.Hash[:]) >= 0 {
			return nil, fmt.Errorf("%w: SOPL1 hashes no crecientes", ErrContenido)
		}
		s.es = append(s.es, e)
	}
	if len(l.b) != 0 {
		return nil, fmt.Errorf("%w: SOPL1 con %d bytes sobrantes", ErrContenido, len(l.b))
	}
	return s, nil
}

func (s *Sopl1) Len() int { return len(s.es) }
func (s *Sopl1) Dim() int { return s.dim }

// Buscar devuelve el soporte de una pregunta por su ClaveConj.
func (s *Sopl1) Buscar(h [32]byte) (*EntradaSopl1, bool) {
	i := sort.Search(len(s.es), func(i int) bool { return bytes.Compare(s.es[i].Hash[:], h[:]) >= 0 })
	if i == len(s.es) || s.es[i].Hash != h {
		return nil, false
	}
	return &s.es[i], true
}

// Opcion devuelve k y la media de L1 (float32, desescalada) de la opción id; ok=false si la entrada no la trae.
func (e *EntradaSopl1) Opcion(id string, dim int) (k int, media []float32, ok bool) {
	c := sort.SearchStrings(e.Ids, id)
	if c == len(e.Ids) || e.Ids[c] != id {
		return 0, nil, false
	}
	media = make([]float32, dim)
	for j, v := range e.Media[c*dim : (c+1)*dim] {
		media[j] = float32(v) * e.Escala[c]
	}
	return int(e.K[c]), media, true
}

// Sopl1 devuelve la sección SOPL1; ErrNoHay si el fichero no la trae.
func (f *Fichero) Sopl1() (*Sopl1, error) {
	b, err := f.Bytes(SOPL1)
	if err != nil {
		return nil, err
	}
	return DecodificarSopl1(b)
}

// PesoSoporte es el peso de los ejemplos w = k/(k+λ) = 1 − λ_c. Equivalencia con model/l2/formula-shrinkage.md: κ ≡ nuestra λ
// y el peso de la descripción es κ/(κ+n) = LambdaClase. lambda nil o infinito ⇒ 0 (sin mezcla: el comportamiento de antes del soporte);
// k ≤ 0 ⇒ 0; λ = 0 ⇒ 1.
func PesoSoporte(k int, lambda *float64) float64 {
	if lambda == nil || math.IsInf(*lambda, 1) || k <= 0 {
		return 0
	}
	return float64(k) / (float64(k) + *lambda)
}

// Mezclar devuelve normaliza((1−w)·desc + w·media) = normaliza(λ_c·desc + (1−λ_c)·media), con la media SIN normalizar (como la
// fórmula de G.8: la normalización va después de mezclar). Con w = 0 devuelve desc tal cual (sin renormalizar, para no
// mover ni un bit del comportamiento anterior). Si la mezcla es el vector cero, devuelve desc.
func Mezclar(desc, media []float32, w float64) []float32 {
	if w <= 0 {
		return desc
	}
	out := make([]float32, len(desc))
	var n float64
	for i := range desc {
		v := (1-w)*float64(desc[i]) + w*float64(media[i])
		out[i] = float32(v)
		n += v * v
	}
	if n == 0 {
		return desc
	}
	n = 1 / math.Sqrt(n)
	for i := range out {
		out[i] = float32(float64(out[i]) * n)
	}
	return out
}

// LambdaClase es el peso de la descripción λ_c = κ/(κ+n_c) de la fórmula de shrinkage de G.8 (model/l2/formula-shrinkage.md),
// con κ ≡ la λ de la config (l2_shrinkage_lambda / AbrirConSoporte); PesoSoporte es el peso de los ejemplos, 1−λ_c.
// κ = 0 ⇒ 0 (solo ejemplos); κ = +∞ ⇒ 1 (solo descripción). kappa nil ⇒ 0.
func LambdaClase(n int, kappa *float64) float64 {
	if kappa == nil || n < 0 {
		return 0
	}
	if math.IsInf(*kappa, 1) {
		return 1
	}
	return *kappa / (*kappa + float64(n))
}

// ProtosMezclados son los prototipos de la clase c de e tras el shrinkage de G.8, K×D contiguos:
//
//	Q_k = λ·h + (1−λ)·M_k  (el mismo h en las K ranuras)  ·  P_k = Q_k/‖Q_k‖  (por ranura; si ‖Q_k‖ = 0, queda en 0)
//
// h es la torre de la descripción (norma 1) y M_k la ranura k de la clase en CONJ, desescalada. Diferencia conocida con el
// entrenamiento: allí M_k es la media SIN normalizar de las ranuras de los ejemplos (norma ≤ 1) y CONJ solo guarda su
// normalizada (norma 1), así que con n ≥ 2 el runtime da a la media algo más de peso del que da modelo.py; con n = 1 coincide.
// λ = 0 devuelve la media normalizada, es decir, los prototipos de CONJ tal cual.
func (e *EntradaConj) ProtosMezclados(c int, h []float32, lambda float64) []float32 {
	out := make([]float32, e.K*e.D)
	for j := 0; j < e.K; j++ {
		esc := float64(e.Escala[c*e.K+j])
		m := e.Proto[(c*e.K+j)*e.D : (c*e.K+j+1)*e.D]
		q := out[j*e.D : (j+1)*e.D]
		var n float64
		for t := range q {
			v := lambda*float64(h[t]) + (1-lambda)*float64(int8(m[t]))*esc
			q[t] = float32(v)
			n += v * v
		}
		if n > 0 {
			n = 1 / math.Sqrt(n)
			for t := range q {
				q[t] = float32(float64(q[t]) * n)
			}
		}
	}
	return out
}

// simprotoF es simproto(S, P) = mean_k max_k' (S_k · P_k') con P en float32 (K'×D contiguos).
func simprotoF(S [][]float32, P []float32, d int) float64 {
	var tot float64
	for _, s := range S {
		best := math.Inf(-1)
		for off := 0; off+d <= len(P); off += d {
			var x float64
			for t, v := range P[off : off+d] {
				x += float64(v) * float64(s[t])
			}
			best = math.Max(best, x)
		}
		tot += best
	}
	return tot / float64(len(S))
}

// SimprotoMezclado es el simproto de la cabeza de L2c con shrinkage (el que comparten el servidor y el SDK móvil): para cada
// opción con k > 0 en sop, simproto contra los ProtosMezclados con λ_c = LambdaClase(k, kappa); el resto de opciones lleva el de
// CONJ sin tocar. La similitud de la opción (sim_opción, el MaxSim de la torre) no cambia: la fórmula solo mezcla los prototipos.
// Devuelve nil si no hay nada que mezclar (kappa nil, sop nil, ninguna opción con soporte o torre): quien llama usa el de siempre.
// torre(i) da la torre de la descripción de la opción i (int8 y escala); sin ella esa opción no se mezcla.
func SimprotoMezclado(e *EntradaConj, sop *EntradaSopl1, kappa *float64, ids []string, S [][]float32,
	torre func(i int) (vec []byte, escala float32, ok bool)) []float64 {
	if e == nil || sop == nil || kappa == nil || len(S) == 0 || len(S[0]) != e.D {
		return nil
	}
	var out []float64
	for i, id := range ids {
		k, ok := sop.KDe(id)
		c := sort.SearchStrings(e.Clases, id)
		if !ok || k <= 0 || c == len(e.Clases) || e.Clases[c] != id {
			continue
		}
		vec, esc, ok := torre(i)
		if !ok || len(vec) != e.D {
			continue
		}
		if out == nil {
			out = SimprotoActual(e, S, ids)
		}
		out[i] = simprotoF(S, e.ProtosMezclados(c, TorreFloat(vec, esc), LambdaClase(k, kappa)), e.D)
	}
	return out
}

// TorreFloat desescala una torre int8.
func TorreFloat(vec []byte, escala float32) []float32 {
	h := make([]float32, len(vec))
	for i, q := range vec {
		h[i] = float32(int8(q)) * escala
	}
	return h
}

// KDe es el número de ejemplos de la opción id; ok=false si la entrada no la trae.
func (e *EntradaSopl1) KDe(id string) (k int, ok bool) {
	c := sort.SearchStrings(e.Ids, id)
	if c == len(e.Ids) || e.Ids[c] != id {
		return 0, false
	}
	return int(e.K[c]), true
}
