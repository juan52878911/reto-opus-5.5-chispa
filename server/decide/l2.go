package decide

import (
	"context"
	"errors"
	"fmt"
	"math"
	"strconv"
	"strings"
	"sync/atomic"

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

	// Torres al vuelo para esquemas que ESQUEMAS no trae (nil = sin opinión, como antes).
	torres CodificadorTorre
	cache  *LRU[[]torreDin] // ClaveEsquema → torres de ese esquema (una por opción en choice, una en noul y score)
	// Hits y Misses cuentan las peticiones de esquema nuevo servidas desde la caché o calculadas.
	Hits, Misses atomic.Uint64
}

// CodificadorTorre calcula la torre de opción (d floats) de un texto de pasaje, con el prefijo «passage: » y el
// formato de model/l2/modelo.py (texto_opcion). Es el e5 de pasaje más la cabeza de torre: hoy el ONNX del .chispa solo
// exporta las ranuras S, así que la implementación real necesita un segundo ONNX (descrito en el informe).
type CodificadorTorre interface {
	Torre(texto string) ([]float32, error)
}

type torreDin struct {
	v []byte
	e float32
}

// ConTorres activa el cálculo al vuelo de torres para esquemas nuevos, cacheadas en un LRU de cacheEsquemas entradas.
func (l *L2) ConTorres(c CodificadorTorre, cacheEsquemas int) *L2 {
	l.torres = c
	l.cache = NewLRU[[]torreDin](cacheEsquemas)
	return l
}

const sepTorre = " · "

// textoTorre es texto_opcion de model/l2/modelo.py: «passage: pregunta · opción · descripción».
func textoTorre(pregunta string, o Opcion) string {
	return strings.Join([]string{"passage: " + pregunta, o.ID, o.Description}, sepTorre)
}

func cuantizarTorre(h []float32) torreDin {
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
	return torreDin{q, float32(esc)}
}

// torresNuevas calcula (o recupera de la caché) las torres de un esquema que ESQUEMAS no trae.
// noul y score usan la última opción como consulta (texto_consulta), como en el export.
func (l *L2) torresNuevas(p Pregunta) ([]torreDin, error) {
	k := ClaveEsquema(p)
	if v, ok := l.cache.Get(k); ok {
		l.Hits.Add(1)
		return v, nil
	}
	l.Misses.Add(1)
	ops := p.Opciones
	if p.Kind != KindChoice {
		if p.Kind == KindNoul { // la consulta es «true»
			ops = []Opcion{{ID: "true"}}
			for _, o := range p.Opciones {
				if o.ID == "true" {
					ops = []Opcion{o}
				}
			}
		} else {
			ops = ops[len(ops)-1:]
		}
	}
	out := make([]torreDin, len(ops))
	for i, o := range ops {
		h, err := l.torres.Torre(textoTorre(p.Texto, o))
		if err != nil {
			return nil, err
		}
		out[i] = cuantizarTorre(h)
	}
	l.cache.Put(k, out)
	return out, nil
}

// ErrSinTokenizador: L2 necesita el tokenizador de e5.
var ErrSinTokenizador = errors.New("L2: hace falta un Tokenizador de e5 (no hay uno en Go todavía)")

// NuevoL2Con monta L2 sobre cualquier SesionS (el ONNX real solo existe con la etiqueta ort).
func NuevoL2Con(ses SesionS, esq *chispa3.Esquemas, calib chispa3.Calib, tok Tokenizador) *L2 {
	return &L2{ses: ses, tok: tok, esq: esq, calib: calib}
}

func (l *L2) Nombre() string { return "L2" }

func softplus(x float64) float64 { return chispa3.Softplus(x) }

// maxsim de una torre h (int8 · escala) contra las ranuras S.
func maxsim(S [][]float32, vec []byte, escala float32) float64 { return chispa3.MaxSim(S, vec, escala) }

// Similitudes de L2 para una pregunta: las ranuras S del mensaje y el MaxSim contra la torre de cada
// opción (choice) o contra la única torre (noul y score, un solo valor). Es la parte que necesita el
// ONNX, detrás de una interfaz para que L2c se pruebe sin ORT con similitudes falsas.
type Similitudes interface {
	// Similitudes devuelve ok=false (sin error) si el esquema no tiene torres en ESQUEMAS.
	Similitudes(p Pregunta) (S [][]float32, sims []float64, ok bool, err error)
}

func (l *L2) Similitudes(p Pregunta) ([][]float32, []float64, bool, error) {
	ids := make([]string, len(p.Opciones))
	for i, o := range p.Opciones {
		ids[i] = o.ID
	}
	// Puntuar antes de llamar al ONNX: sin torres para este esquema no hay nada que hacer.
	torre := func(opciones []string) ([]byte, float32, bool) {
		return l.esq.Buscar(chispa3.HashEsquema(p.Texto, opciones))
	}
	type vt = torreDin
	var ts []vt
	if p.Kind == KindChoice {
		for _, id := range ids {
			v, e, ok := torre([]string{id})
			if !ok {
				return l.similitudesNuevas(p)
			}
			ts = append(ts, vt{v, e})
		}
	} else {
		if p.Kind == KindNoul {
			ids = []string{"false", "true"}
		}
		v, e, ok := torre(ids)
		if !ok {
			return l.similitudesNuevas(p)
		}
		ts = []vt{{v, e}}
	}
	return l.simsDe(p, ts)
}

// similitudesNuevas: esquema ausente de ESQUEMAS. Sin CodificadorTorre, sin opinión; con él, torres al vuelo.
func (l *L2) similitudesNuevas(p Pregunta) ([][]float32, []float64, bool, error) {
	if l.torres == nil {
		return nil, nil, false, nil
	}
	ts, err := l.torresNuevas(p)
	if err != nil {
		return nil, nil, false, err
	}
	return l.simsDe(p, ts)
}

func (l *L2) simsDe(p Pregunta, ts []torreDin) ([][]float32, []float64, bool, error) {
	if l.tok == nil {
		return nil, nil, false, fmt.Errorf("L2: falta el tokenizador")
	}
	S, err := l.ses.Ranuras(l.tok.IDs(p.Estado))
	if err != nil {
		return nil, nil, false, err
	}
	if len(S) == 0 {
		return nil, nil, false, fmt.Errorf("L2: el codificador no devolvió ranuras")
	}
	if len(S[0]) != len(ts[0].v) {
		return nil, nil, false, fmt.Errorf("L2: ranuras de dimensión %d y torres de %d", len(S[0]), len(ts[0].v))
	}
	sims := make([]float64, len(ts))
	for i, t := range ts {
		sims[i] = maxsim(S, t.v, t.e)
	}
	return S, sims, true, nil
}

func (l *L2) Decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	if len(p.Opciones) == 0 {
		return Respuesta{}, nil
	}
	_, sims, ok, err := l.Similitudes(p)
	if err != nil || !ok {
		return Respuesta{}, err
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
