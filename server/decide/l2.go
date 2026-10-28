package decide

import (
	"context"
	"fmt"
	"math"
	"strconv"

	"chispa/format/chispa3"
)

// Tokenizador convierte un texto en ids del tokenizador original de e5 (con «query: »
// delante, tokens especiales y recorte a 128), que es lo que espera el ONNX de L2.
type Tokenizador interface {
	IDs(texto string) []int64
}

// SesionS es el ONNX de L2: ids → S ∈ R^{K×d} (una consulta, K ranuras).
type SesionS interface {
	Ranuras(ids []int64) ([][]float32, error)
}

// L2 es la capa neuronal: ranuras del mensaje (ONNX) contra las torres de opción
// de ESQUEMAS, con MaxSim = max_k softplus(h · s_k) y las cabezas de CALIB.
type L2 struct {
	ses   SesionS
	tok   Tokenizador
	esq   *chispa3.Esquemas
	calib chispa3.Calib
}

// NuevoL2Con monta L2 sobre cualquier SesionS (el ONNX real solo existe con la etiqueta ort).
func NuevoL2Con(ses SesionS, esq *chispa3.Esquemas, calib chispa3.Calib, tok Tokenizador) *L2 {
	return &L2{ses: ses, tok: tok, esq: esq, calib: calib}
}

func (l *L2) Nombre() string { return "L2" }

func softplus(x float64) float64 {
	if x > 30 {
		return x
	}
	return math.Log1p(math.Exp(x))
}

// maxsim de una torre h (int8 · escala) contra las ranuras S.
func maxsim(S [][]float32, vec []byte, escala float32) float64 {
	best := math.Inf(-1)
	for _, s := range S {
		var d float64
		for j, q := range vec {
			d += float64(int8(q)) * float64(s[j])
		}
		best = math.Max(best, softplus(d*float64(escala)))
	}
	return best
}

func (l *L2) Decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	if len(p.Opciones) == 0 {
		return Respuesta{}, nil
	}
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	// Puntuar antes de llamar al ONNX: sin torres para este esquema no hay nada que hacer.
	torre := func(opciones []string) ([]byte, float32, bool) {
		return l.esq.Buscar(chispa3.HashEsquema(p.Texto, opciones))
	}
	type vt struct {
		v []byte
		e float32
	}
	var ts []vt
	if p.Kind == KindChoice {
		for _, id := range ids {
			v, e, ok := torre([]string{id})
			if !ok {
				return Respuesta{}, nil
			}
			ts = append(ts, vt{v, e})
		}
	} else {
		if p.Kind == KindNoul {
			ids = []string{"false", "true"}
		}
		v, e, ok := torre(ids)
		if !ok {
			return Respuesta{}, nil
		}
		ts = []vt{{v, e}}
	}
	if l.tok == nil {
		return Respuesta{}, fmt.Errorf("L2: falta el tokenizador")
	}
	S, err := l.ses.Ranuras(l.tok.IDs(p.Estado))
	if err != nil {
		return Respuesta{}, err
	}
	if len(S) == 0 || len(S[0]) != len(ts[0].v) {
		return Respuesta{}, fmt.Errorf("L2: ranuras de dimensión %d y torres de %d", len(S[0]), len(ts[0].v))
	}
	sims := make([]float64, len(ts))
	for i, t := range ts {
		sims[i] = maxsim(S, t.v, t.e)
	}
	switch p.Kind {
	case KindChoice:
		return respuestaSoftmax(p, sims, paramsDe(l.calib, "choice").T), nil
	case KindNoul:
		prm := paramsDe(l.calib, "noul")
		return respuestaNoul(prm.A*sims[0]+prm.B, prm.Theta), nil
	}
	return l.score(p, sims[0])
}

// score: CORAL, P(y>j) = σ(a·s − b_j); b_1 = b de «scoreK» y b_j = b_{j−1} + a de «scoreK#j».
func (l *L2) score(p Pregunta, s float64) (Respuesta, error) {
	K := len(p.Opciones)
	for i, o := range p.Opciones {
		if o.ID != strconv.Itoa(i+1) {
			return Respuesta{}, nil // las cabezas de score van sobre 1..K en orden
		}
	}
	clave := "score" + strconv.Itoa(K)
	base, ok := l.calib.Tipos[clave]
	if !ok {
		return Respuesta{}, nil
	}
	sup := make([]float64, K-1) // P(y > j+1)
	b := base.B
	for j := 0; j < K-1; j++ {
		if j > 0 {
			inc, ok := l.calib.Tipos[fmt.Sprintf("%s#%d", clave, j+1)]
			if !ok {
				return Respuesta{}, nil
			}
			b += inc.A
		}
		sup[j] = 1 / (1 + math.Exp(-(base.A*s - b)))
	}
	r := Respuesta{Probs: make(map[string]float64, K)}
	for i := 0; i < K; i++ {
		hi, lo := 1.0, 0.0
		if i > 0 {
			hi = sup[i-1]
		}
		if i < K-1 {
			lo = sup[i]
		}
		pr := math.Max(hi-lo, 0)
		r.Probs[p.Opciones[i].ID] = pr
		if pr > r.Conf {
			r.Conf, r.Answer = pr, p.Opciones[i].ID
		}
	}
	return r, nil
}
