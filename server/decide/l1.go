package decide

import (
	"context"
	"math"
	"strings"
	"sync/atomic"

	"chispa/format/chispa3"
	"chispa/runtime/l1"
)

// Temperatura por defecto cuando CALIB no trae el tipo.
const tDefecto = 0.05

// L1 es el embedding estático (Model2Vec en Go puro): puntúa cada opción por
// coseno entre el mensaje y «pregunta · opción · descripción». choice: softmax
// del coseno / T; noul: σ(a·coseno + b) con el umbral θ. score no lo cubre
// (sin opinión): un coseno no ordena niveles y no hay cabeza calibrada para ello.
type L1 struct {
	m      *l1.Modelo
	calib  chispa3.Calib
	cache  *LRU[map[string][]float32] // clave de esquema → embedding por id de opción (la clave ignora el orden)
	Hits   atomic.Uint64
	Misses atomic.Uint64
}

// NuevoL1Modelo monta L1 sobre un modelo ya abierto. calib puede estar vacía (T por defecto).
func NuevoL1Modelo(m *l1.Modelo, calib chispa3.Calib, cacheEsquemas int) *L1 {
	return &L1{m: m, calib: calib, cache: NewLRU[map[string][]float32](cacheEsquemas)}
}

func (l *L1) Nombre() string { return "L1" }

func (l *L1) params(tipo string) chispa3.ParamsTipo { return paramsDe(l.calib, tipo) }

// paramsDe devuelve los parámetros calibrados de un tipo, o unos por defecto.
func paramsDe(c chispa3.Calib, tipo string) chispa3.ParamsTipo {
	p, ok := c.Tipos[tipo]
	if !ok {
		return chispa3.ParamsTipo{T: tDefecto, A: 4, B: -2, Theta: 0.5}
	}
	return p
}

// textoOpcion es el texto de la torre de una opción.
func textoOpcion(p Pregunta, o Opcion) string {
	s := []string{p.Texto, o.ID}
	if o.Description != "" {
		s = append(s, o.Description)
	}
	return strings.Join(s, " · ")
}

func (l *L1) opciones(p Pregunta) map[string][]float32 {
	k := ClaveEsquema(p)
	if v, ok := l.cache.Get(k); ok {
		l.Hits.Add(1)
		return v
	}
	l.Misses.Add(1)
	v := make(map[string][]float32, len(p.Opciones))
	for _, o := range p.Opciones {
		e := make([]float32, l.m.Dim())
		l.m.Embed(textoOpcion(p, o), e)
		v[o.ID] = e
	}
	l.cache.Put(k, v)
	return v
}

func coseno(a, b []float32) float64 {
	var s float64
	for i := range a {
		s += float64(a[i]) * float64(b[i]) // ambos unitarios (o cero)
	}
	return s
}

func (l *L1) Decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	if p.Kind == KindScore || len(p.Opciones) == 0 {
		return Respuesta{}, nil
	}
	msg := make([]float32, l.m.Dim())
	if !l.m.Embed(p.Estado, msg) {
		return Respuesta{}, nil
	}
	ops := l.opciones(p)
	sims := make([]float64, len(ops))
	for i, o := range p.Opciones {
		sims[i] = coseno(msg, ops[o.ID])
	}
	if p.Kind == KindNoul { // la consulta es la opción «true»
		prm := l.params("noul")
		var s float64
		for i, o := range p.Opciones {
			if o.ID == "true" {
				s = sims[i]
			}
		}
		return respuestaNoul(prm.A*s+prm.B, prm.Theta), nil
	}
	return respuestaSoftmax(p, sims, l.params("choice").T), nil
}

func respuestaNoul(z, theta float64) Respuesta {
	pt := 1 / (1 + math.Exp(-z))
	r := Respuesta{Probs: map[string]float64{"true": pt, "false": 1 - pt}}
	if pt >= theta {
		r.Answer, r.Conf = "true", pt
	} else {
		r.Answer, r.Conf = "false", 1-pt
	}
	return r
}

func respuestaSoftmax(p Pregunta, sims []float64, T float64) Respuesta {
	mx := math.Inf(-1)
	for _, s := range sims {
		mx = math.Max(mx, s)
	}
	var z float64
	ex := make([]float64, len(sims))
	for i, s := range sims {
		ex[i] = math.Exp((s - mx) / T)
		z += ex[i]
	}
	r := Respuesta{Probs: make(map[string]float64, len(sims))}
	for i, o := range p.Opciones {
		pr := ex[i] / z
		r.Probs[o.ID] = pr
		if pr > r.Conf {
			r.Conf, r.Answer = pr, o.ID
		}
	}
	return r
}
