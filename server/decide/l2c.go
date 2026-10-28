package decide

import (
	"context"
	"math"
	"sort"

	"chispa/format/chispa3"
)

// epsConj es el recorte de log(p) de la cabeza (EPS de model/l2/conjunta.py).
const epsConj = 1e-6

// Previas son las respuestas de las capas ya recorridas, por nombre de capa.
type Previas map[string]Respuesta

// DecisorConPrevias es un decisor que además usa lo que dijeron las capas anteriores (L2c lee las
// probabilidades de L0). La cascada llama a DecidirCon en vez de Decidir si el decisor lo implementa.
type DecisorConPrevias interface {
	Decisor
	DecidirCon(ctx context.Context, p Pregunta, previas Previas) (Respuesta, error)
}

// L2c es «L2 conjunta»: la cabeza lineal por esquema de la sección CONJ sobre las probabilidades de L0 y las
// similitudes de L2 con soporte (prototipos de los ejemplos del cliente). Sin entrada en CONJ para el esquema,
// sin probabilidades de L0 o fuera de choice, se comporta como L2. Se llama «L2» en la cascada y en la config.
type L2c struct {
	*L2
	sim  Similitudes
	conj *chispa3.Conj
}

// NuevoL2cCon monta L2c sobre cualquier fuente de similitudes (el ONNX real solo existe con la etiqueta ort).
func NuevoL2cCon(base *L2, sim Similitudes, conj *chispa3.Conj) *L2c {
	return &L2c{L2: base, sim: sim, conj: conj}
}

func (l *L2c) Nombre() string { return "L2" }

func (l *L2c) Decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	return l.DecidirCon(ctx, p, nil)
}

// ClaveConj es el hash del esquema en CONJ: la pregunta y los ids de las opciones, ordenados.
func ClaveConj(p Pregunta) [32]byte {
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	sort.Strings(ids)
	return chispa3.HashEsquema(p.Texto, ids)
}

func (l *L2c) DecidirCon(ctx context.Context, p Pregunta, previas Previas) (Respuesta, error) {
	if p.Kind != KindChoice || len(p.Opciones) == 0 {
		return l.L2.Decidir(ctx, p)
	}
	e, ok := l.conj.Buscar(ClaveConj(p))
	l0, hay := previas["L0"]
	if !ok || !hay || len(l0.Probs) == 0 {
		return l.L2.Decidir(ctx, p)
	}
	S, sims, ok, err := l.sim.Similitudes(p)
	if err != nil || !ok {
		return Respuesta{}, err
	}
	if len(S) == 0 || len(S[0]) != e.D {
		return l.L2.Decidir(ctx, p)
	}
	return cabezaConj(p, e, S, sims, l0.Probs), nil
}

// CabezaConj calcula las probabilidades de la cabeza `lr` (las de `conjunta.Cabeza.probs`) para las opciones
// de p, en su orden. sims es el MaxSim de L2 por opción; l0, las probabilidades de L0 por id de opción.
func cabezaConj(p Pregunta, e *chispa3.EntradaConj, S [][]float32, sims []float64, l0 map[string]float64) Respuesta {
	n := len(p.Opciones)
	sp := simproto(e, S, p.Opciones)
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
		p0[i] = l0[p.Opciones[i].ID]
	}
	lg := logitsLR(e, p0, sp, l2)
	return respuestaLogits(p, lg)
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
func logitsLR(e *chispa3.EntradaConj, p0, sp, p2 []float64) []float64 {
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

func respuestaLogits(p Pregunta, lg []float64) Respuesta {
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
	r := Respuesta{Probs: make(map[string]float64, len(lg))}
	for i, o := range p.Opciones {
		pr := ex[i] / z
		r.Probs[o.ID] = pr
		if pr > r.Conf {
			r.Conf, r.Answer = pr, o.ID
		}
	}
	return r
}

// simproto: para cada opción, media sobre las ranuras k del mensaje de max_j S_k · P_{c,j}, con los prototipos
// int8 de la clase (cuyo nombre es el id de la opción) por su escala. Una opción sin clase en CONJ vale 0.
func simproto(e *chispa3.EntradaConj, S [][]float32, ops []Opcion) []float64 {
	out := make([]float64, len(ops))
	for i, o := range ops {
		c := sort.SearchStrings(e.Clases, o.ID)
		if c == len(e.Clases) || e.Clases[c] != o.ID {
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
