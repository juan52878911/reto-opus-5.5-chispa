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
//	u32 versión(1, 2 o 3) · u32 dim · u32 n · n entradas con hash estrictamente creciente
//
// Entrada (hash = ClaveConj: HashEsquema de la pregunta y los ids de las opciones ordenados, la misma clave que CONJ):
//
//	[32]byte hash · u32 C · C×(u16 len · id UTF-8) estrictamente crecientes · C×u32 k · C×f32 escala · C×dim×int8 media
//
// La media va en int8 con escala máx|x|/127 por opción (como las torres de ESQUEMAS): 4× menos que f32 y el error de
// cuantización (≤ 0,4 % por componente) queda muy por debajo del ruido de unos pocos ejemplos. Una opción sin ejemplos
// lleva k=0, escala 0 y ceros.
//
// Versión 2 (misma cabecera con versión = 2): cada entrada añade al final u32 K · C×K×f32 normas (K = 0 ⇒ sin normas, y no
// siguen los f32). normas[c·K+j] es la norma de la ranura j de la media SIN normalizar de L2c de la clase c (‖(1/n)·Σ S_i,j‖ ≤ 1);
// CONJ guarda las ranuras ya normalizadas y con ellas el runtime reconstruye la media de modelo.py (Proto·escala·norma). El escritor
// emite la versión 2 solo si alguna entrada trae normas (si no, los bytes son los de la versión 1); el lector acepta las dos.
//
// Versión 3 (versión = 3): igual que la 2 y cada entrada añade, tras las normas, u32 M · M×u32 n_l2 (M = 0 ⇒ sin n_l2; si no, M = C).
// n_l2[c] es el número de ejemplos del soporte de CONJ (SOPORTE de L2) de la clase c, que puede ser un subconjunto de los que ve L1 (k);
// es el n de modelo.py en el peso κ/(κ+n) de L2c (L1 sigue con k). n_l2[c] = 0 ⇒ sin dato: L2c usa k. Las versiones 1 y 2 se leen
// igual (sin n_l2). La 2 no puede ampliarse en sitio: sus entradas no llevan longitud y un lector de la 2 rechazaría los bytes de más.
// El escritor emite la versión 3 solo si alguna entrada trae NL2 (si no, los bytes son los de la 1 o la 2).
const (
	Sopl1Version  = 1 // versión sin normas
	Sopl1Version2 = 2 // con normas por ranura
	Sopl1Version3 = 3 // con normas y n_l2
	maxSoplK      = 256
	maxSoplDim    = 4096
	maxSoplN      = 1 << 16
	maxSoplC      = 1 << 16
	soplFijoEntr  = 32 + 4
)

// EntradaSopl1 es el soporte de una pregunta. Media son C·dim bytes int8 en crudo (en la lectura apunta a la sección).
type EntradaSopl1 struct {
	Hash   [32]byte
	Ids    []string // estrictamente crecientes
	K      []uint32
	Escala []float32
	Media  []int8
	// Ranuras (K) y Normas (versión 2): ranuras por clase y C·K normas de la media sin normalizar de L2c. Ranuras = 0 / Normas nil = sin normas.
	Ranuras int
	Normas  []float32
	// NL2 (versión 3): C ejemplos del soporte de CONJ por clase (n de modelo.py); nil = sin dato (L2c usa K).
	NL2 []uint32
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
	if e.Ranuras < 0 || e.Ranuras > maxSoplK || len(e.Normas) != c*e.Ranuras {
		return fmt.Errorf("%w: SOPL1 normas K=%d con %d valores para C=%d", ErrContenido, e.Ranuras, len(e.Normas), c)
	}
	for _, x := range e.Normas {
		if !(x >= 0) || x > 1.001 || !finito32(x) {
			return fmt.Errorf("%w: SOPL1 norma de ranura %v", ErrContenido, x)
		}
	}
	if e.NL2 != nil && len(e.NL2) != c {
		return fmt.Errorf("%w: SOPL1 n_l2 con %d valores para C=%d", ErrContenido, len(e.NL2), c)
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
	ver := uint32(Sopl1Version)
	for i := range s {
		if s[i].NL2 != nil {
			ver = Sopl1Version3
		} else if s[i].Ranuras > 0 {
			ver = max(ver, Sopl1Version2)
		}
	}
	b := le.AppendUint32(nil, ver)
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
		if ver >= Sopl1Version2 {
			b = le.AppendUint32(b, uint32(e.Ranuras))
			for _, x := range e.Normas {
				b = le.AppendUint32(b, math.Float32bits(x))
			}
		}
		if ver == Sopl1Version3 {
			b = le.AppendUint32(b, uint32(len(e.NL2)))
			for _, n := range e.NL2 {
				b = le.AppendUint32(b, n)
			}
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
	ver := l.u32()
	if l.err == nil && (ver < Sopl1Version || ver > Sopl1Version3) {
		return nil, fmt.Errorf("%w: SOPL1 versión %d", ErrContenido, ver)
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
		if ver >= Sopl1Version2 {
			kk := l.u32()
			if l.err != nil {
				return nil, l.err
			}
			if kk > maxSoplK || uint64(nc)*uint64(kk)*4 > uint64(len(l.b)) {
				return nil, fmt.Errorf("%w: SOPL1 K=%d", ErrContenido, kk)
			}
			e.Ranuras = int(kk)
			if kk > 0 {
				e.Normas = make([]float32, int(nc)*int(kk))
				for j := range e.Normas {
					e.Normas[j] = l.f32()
				}
				if l.err != nil {
					return nil, l.err
				}
			}
		}
		if ver == Sopl1Version3 {
			m := l.u32()
			if l.err != nil {
				return nil, l.err
			}
			if m != 0 && m != nc {
				return nil, fmt.Errorf("%w: SOPL1 n_l2 M=%d para C=%d", ErrContenido, m, nc)
			}
			if m > 0 {
				e.NL2 = make([]uint32, m)
				for j := range e.NL2 {
					e.NL2[j] = l.u32()
				}
				if l.err != nil {
					return nil, l.err
				}
			}
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

// NormasDe devuelve las K normas de ranura de la clase id (versión 2); nil si la entrada no las trae o no tiene la clase.
func (e *EntradaSopl1) NormasDe(id string) []float32 {
	c := sort.SearchStrings(e.Ids, id)
	if e.Ranuras == 0 || c == len(e.Ids) || e.Ids[c] != id {
		return nil
	}
	return e.Normas[c*e.Ranuras : (c+1)*e.Ranuras]
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
// y el peso de la descripción es κ/(κ+n) = LambdaClase. lambda nil ⇒ 0 (apagado: el comportamiento de antes del soporte);
// k ≤ 0 ⇒ 0; λ = 0 ⇒ 1 (solo ejemplos); λ = +∞ ⇒ 0 (solo descripción).
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
// h es la torre de la descripción (norma 1) y M_k la ranura k de la clase en CONJ, desescalada y multiplicada por normas[k]: en
// el entrenamiento M_k es la media SIN normalizar de las ranuras de los ejemplos (norma ≤ 1) y CONJ solo guarda su normalizada,
// de modo que normas (SOPL1 v2, ver EntradaSopl1.NormasDe) devuelve a la media su norma y la fórmula coincide con modelo.py. normas
// nil (SOPL1 v1 o sin SOPL1 v2) usa la media normalizada: con n ≥ 2 da a los ejemplos algo más de peso que modelo.py; con n = 1
// coincide. λ = 0 devuelve la media normalizada, es decir, los prototipos de CONJ tal cual.
func (e *EntradaConj) ProtosMezclados(c int, h []float32, lambda float64, normas []float32) []float32 {
	out := make([]float32, e.K*e.D)
	for j := 0; j < e.K; j++ {
		esc := float64(e.Escala[c*e.K+j])
		if len(normas) == e.K {
			esc *= float64(normas[j])
		}
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
		n, _ := sop.NL2De(id) // el n del soporte de CONJ (v3) o k; L1 sigue con k
		vec, esc, ok := torre(i)
		if !ok || len(vec) != e.D {
			continue
		}
		if out == nil {
			out = SimprotoActual(e, S, ids)
		}
		out[i] = simprotoF(S, e.ProtosMezclados(c, TorreFloat(vec, esc), LambdaClase(n, kappa), sop.NormasDe(id)), e.D)
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

// NL2De es el n del soporte de CONJ de la clase id (versión 3), el de modelo.py para L2c; si la entrada no lo trae (o es 0), el k de L1.
func (e *EntradaSopl1) NL2De(id string) (n int, ok bool) {
	k, ok := e.KDe(id)
	if !ok {
		return 0, false
	}
	if e.NL2 != nil {
		if c := sort.SearchStrings(e.Ids, id); e.NL2[c] > 0 {
			return int(e.NL2[c]), true
		}
	}
	return k, true
}

// KDe es el número de ejemplos de la opción id; ok=false si la entrada no la trae.
func (e *EntradaSopl1) KDe(id string) (k int, ok bool) {
	c := sort.SearchStrings(e.Ids, id)
	if c == len(e.Ids) || e.Ids[c] != id {
		return 0, false
	}
	return int(e.K[c]), true
}
