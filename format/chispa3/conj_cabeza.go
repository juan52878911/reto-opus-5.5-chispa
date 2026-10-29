package chispa3

import (
	"math"
	"sort"
	"sync"
)

// Cabeza de CONJ (la «L2 conjunta»): el cálculo que comparten el servidor (server/decide) y el núcleo móvil
// (sdk/movil/chispamovil). Las similitudes de L2 las pone quien llama (ORT o el ONNX del servidor).

// Softplus es log(1+eˣ), estable para x grande.
func Softplus(x float64) float64 {
	if x > 30 {
		return x
	}
	return math.Log1p(math.Exp(x))
}

// MaxSim de una torre vec (int8, por su escala) contra las ranuras S: max_k softplus(h·s_k). Es la similitud de
// L2 (server/decide/l2.go y el SDK móvil).
func MaxSim(S [][]float32, vec []byte, escala float32) float64 {
	best := math.Inf(-1)
	for _, s := range S {
		var d float64
		for j, q := range vec {
			d += float64(int8(q)) * float64(s[j])
		}
		best = math.Max(best, Softplus(d*float64(escala)))
	}
	return best
}

// epsConj es el recorte de log(p) de la cabeza (EPS de model/l2/conjunta.py).
const epsConj = 1e-6

// ClaveConj es el hash del esquema en CONJ: la pregunta y los ids de las opciones, ordenados.
func ClaveConj(texto string, ids []string) [32]byte {
	s := append([]string(nil), ids...)
	sort.Strings(s)
	return HashEsquema(texto, s)
}

// ProbsCabeza calcula las probabilidades de la cabeza `lr` (las de `conjunta.Cabeza.probs`) para las opciones ids,
// en su orden. S son las ranuras de L2 con soporte; sims, el MaxSim de L2 por opción; l0, las probabilidades de
// L0 por id de opción.
func (e *EntradaConj) ProbsCabeza(ids []string, S [][]float32, sims []float64, l0 map[string]float64) []float64 {
	n := len(ids)
	sp := SimprotoActual(e, S, ids)
	// P_L2 con soporte: softmax((MaxSim + β·simproto) / T).
	l2 := make([]float64, n)
	mx := math.Inf(-1)
	for i := range l2 {
		l2[i] = (sims[i] + float64(e.Beta)*sp[i]) / float64(e.T)
		mx = math.Max(mx, l2[i])
	}
	var z float64
	for i := range l2 {
		l2[i] = math.Exp(l2[i] - mx)
		z += l2[i]
	}
	p0 := make([]float64, n)
	for i := range l2 {
		l2[i] /= z
		p0[i] = l0[ids[i]]
	}
	return softmaxLogits(logitsLR(e, p0, sp, l2))
}

func softmaxLogits(lg []float64) []float64 {
	mx := math.Inf(-1)
	for _, v := range lg {
		mx = math.Max(mx, v)
	}
	var z float64
	ex := make([]float64, len(lg))
	for i, v := range lg {
		ex[i] = math.Exp(v - mx)
		z += ex[i]
	}
	for i := range ex {
		ex[i] /= z
	}
	return ex
}

func recortarLog(x float64) float64 {
	if x < epsConj {
		x = epsConj
	} else if x > 1 {
		x = 1
	}
	return math.Log(x)
}

func centrar(x []float64) {
	var m float64
	for _, v := range x {
		m += v
	}
	m /= float64(len(x))
	for i := range x {
		x[i] -= m
	}
}

// logitsLR: logit_c = w · [a_c/esc0, b_c/esc1, c_c/esc2, top0, top2, top0·top2], con a = log P_L0 y c = log P_L2
// centrados por fila, b = simproto centrado, y top* la marca de la clase máxima.
func logitsLR(e *EntradaConj, p0, sp, p2 []float64) []float64 {
	n := len(p0)
	a, b, c := make([]float64, n), append([]float64(nil), sp...), make([]float64, n)
	for i := range a {
		a[i], c[i] = recortarLog(p0[i]), recortarLog(p2[i])
	}
	centrar(a)
	centrar(b)
	centrar(c)
	m0, m2 := math.Inf(-1), math.Inf(-1)
	for i := range p0 {
		m0, m2 = math.Max(m0, p0[i]), math.Max(m2, p2[i])
	}
	w := func(i int) float64 { return float64(e.W[i]) }
	lg := make([]float64, n)
	for i := range lg {
		var t0, t2 float64
		if p0[i] == m0 {
			t0 = 1
		}
		if p2[i] == m2 {
			t2 = 1
		}
		lg[i] = w(0)*a[i]/float64(e.Esc[0]) + w(1)*b[i]/float64(e.Esc[1]) + w(2)*c[i]/float64(e.Esc[2]) +
			w(3)*t0 + w(4)*t2 + w(5)*t0*t2
	}
	return lg
}

func Simproto(e *EntradaConj, S [][]float32, ids []string) []float64 {
	out := make([]float64, len(ids))
	if len(S) == 0 {
		return out
	}
	pk := protosEmpaquetados(e)
	w := pk.w
	qs := make([]int64, len(S)*w)
	esc := make([]float64, len(S))
	for k, s := range S {
		esc[k] = cuantizarRanura(s, qs[k*w:(k+1)*w])
	}
	best := make([]float64, len(S))
	for i, id := range ids {
		c := sort.SearchStrings(e.Clases, id)
		if c == len(e.Clases) || e.Clases[c] != id {
			continue
		}
		for k := range best {
			best[k] = math.Inf(-1)
		}
		for j := 0; j < e.K; j++ {
			p := pk.p[(c*e.K+j)*w : (c*e.K+j+1)*w]
			sc := float64(e.Escala[c*e.K+j])
			k := 0
			for ; k+4 <= len(S); k += 4 {
				d := dot3x4(p, qs[k*w:(k+1)*w], qs[(k+1)*w:(k+2)*w], qs[(k+2)*w:(k+3)*w], qs[(k+3)*w:(k+4)*w])
				for t, v := range d {
					best[k+t] = max(best[k+t], float64(v)*esc[k+t]*sc)
				}
			}
			for ; k < len(S); k++ {
				best[k] = max(best[k], float64(dot3(p, qs[k*w:(k+1)*w]))*esc[k]*sc)
			}
		}
		var tot float64
		for _, b := range best {
			tot += b
		}
		out[i] = tot / float64(len(S))
	}
	return out
}

// SimprotoActual es la implementación en uso; las pruebas de paridad estricta con Python la cambian a SimprotoRef.
var SimprotoActual = Simproto

// SimprotoRef es el cálculo en float32 sin cuantizar S (referencia de las pruebas).
func SimprotoRef(e *EntradaConj, S [][]float32, ids []string) []float64 {
	out := make([]float64, len(ids))
	for i, id := range ids {
		c := sort.SearchStrings(e.Clases, id)
		if c == len(e.Clases) || e.Clases[c] != id {
			continue
		}
		var tot float64
		for _, s := range S {
			best := math.Inf(-1)
			for j := 0; j < e.K; j++ {
				v := e.Proto[(c*e.K+j)*e.D : (c*e.K+j+1)*e.D]
				var d float32
				for t, q := range v {
					d += float32(int8(q)) * s[t]
				}
				best = math.Max(best, float64(d)*float64(e.Escala[c*e.K+j]))
			}
			tot += best
		}
		out[i] = tot / float64(len(S))
	}
	return out
}

const (
	carril = 21
	sesgo  = int64(1) << (2*carril - 1) // redondeo al extraer el carril alto
)

// empaquetar3 junta tres int8 en un int64: a0 + a1·2^21 + a2·2^42. Para el lado de los prototipos se pasan
// en orden inverso (a2, a1, a0) para que el carril 2^42 del producto sea a0b0 + a1b1 + a2b2.
func empaquetar3(a, b, c int8) int64 {
	return int64(a) + int64(b)<<carril + int64(c)<<(2*carril)
}

// dot3 es el producto escalar entero de dos vectores empaquetados con empaquetar3 (p al derecho, q al revés).
// Se acumulan bloques de bloque3 palabras sin extraer el carril alto: los carriles bajos suman a lo sumo
// bloque3·2·127²·2^21 < 2^41 (el sesgo los redondea) y el carril alto, bloque3·3·127² < 2^20 (se extiende el signo
// desde 21 bits, lo que de paso descarta el bit 63 que ensucia el producto).
func dot3(p, q []int64) int64 {
	q = q[:len(p)]
	var total int64
	for len(p) > 0 {
		n := min(len(p), bloque3)
		var a, b int64
		i := 0
		for ; i+2 <= n; i += 2 {
			a += p[i] * q[i]
			b += p[i+1] * q[i+1]
		}
		if i < n {
			a += p[i] * q[i]
		}
		total += extraer(a + b)
		p, q = p[n:], q[n:]
	}
	return total
}

const bloque3 = 16

// dot3x4 son cuatro dot3 contra el mismo p: lee p una sola vez.
func dot3x4(p, q0, q1, q2, q3 []int64) [4]int64 {
	q0, q1, q2, q3 = q0[:len(p)], q1[:len(p)], q2[:len(p)], q3[:len(p)]
	var total [4]int64
	for ini := 0; ini < len(p); ini += bloque3 {
		fin := min(ini+bloque3, len(p))
		var a0, a1, a2, a3 int64
		for i := ini; i < fin; i++ {
			x := p[i]
			a0 += x * q0[i]
			a1 += x * q1[i]
			a2 += x * q2[i]
			a3 += x * q3[i]
		}
		total[0] += extraer(a0)
		total[1] += extraer(a1)
		total[2] += extraer(a2)
		total[3] += extraer(a3)
	}
	return total
}

// extraer saca el carril alto de un acumulador de dot3: redondea, desplaza y extiende el signo desde 21 bits.
func extraer(a int64) int64 { return ((a + sesgo) >> (2 * carril)) << (64 - carril) >> (64 - carril) }

type protosPk struct {
	p []int64 // C·K filas de w palabras
	w int
}

var cachePk sync.Map // *EntradaConj → *protosPk

// protosEmpaquetados devuelve los prototipos de e listos para dot3 (se calcula una vez por entrada).
func protosEmpaquetados(e *EntradaConj) *protosPk {
	if v, ok := cachePk.Load(e); ok {
		return v.(*protosPk)
	}
	w := (e.D + 2) / 3
	filas := len(e.Proto) / e.D
	p := make([]int64, filas*w)
	for f := 0; f < filas; f++ {
		fila := e.Proto[f*e.D : (f+1)*e.D]
		for i := 0; i < w; i++ {
			var v [3]int8
			for t := 0; t < 3 && 3*i+t < e.D; t++ {
				v[t] = int8(fila[3*i+t])
			}
			p[f*w+i] = empaquetar3(v[0], v[1], v[2])
		}
	}
	v, _ := cachePk.LoadOrStore(e, &protosPk{p, w})
	return v.(*protosPk)
}

// cuantizarRanura cuantiza s a int8 con escala max|s|/127, lo empaqueta al revés en out y devuelve la escala.
func cuantizarRanura(s []float32, out []int64) float64 {
	var m float32
	for _, x := range s {
		m = max(m, x, -x)
	}
	if m == 0 {
		return 0
	}
	esc := m / 127
	q := func(t int) int8 {
		if t >= len(s) {
			return 0
		}
		return int8(math.RoundToEven(float64(s[t] / esc)))
	}
	for i := range out {
		out[i] = empaquetar3(q(3*i+2), q(3*i+1), q(3*i))
	}
	return float64(esc)
}
