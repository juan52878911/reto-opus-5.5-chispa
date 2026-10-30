package decide

import (
	"context"
	"math"
	"strings"
	"sync/atomic"

	"chispa/format/chispa3"
	"chispa/runtime/l1"
	"chispa/runtime/tok"
)

// Temperatura por defecto cuando CALIB no trae el tipo.
const tDefecto = 0.05

// L1 es el embedding estático (Model2Vec en Go puro): puntúa cada opción por
// coseno entre el mensaje y «pregunta · opción · descripción». choice: softmax
// del coseno / T; noul: σ(a·coseno + b) con el umbral θ; multi: esa misma sigmoide por opción (CALIB «multi», θ por opción en «multi#id»); score: el mismo softmax
// sobre los niveles (en el orden de la pregunta) y la respuesta es la mediana de
// esa distribución, con confianza P(mediana).
type L1 struct {
	m               *l1.Modelo
	calib           chispa3.Calib
	sinCalibFichero bool                       // el .chispa no trae CALIB (τ y tipos por defecto)
	cache           *LRU[map[string][]float32] // clave de esquema → embedding por id de opción (la clave ignora el orden)
	sopl            *chispa3.Sopl1             // soporte few-shot del .chispa (k y media de ejemplos por pregunta y opción), o nil
	lambda          *float64                   // λ del encogimiento; nil = apagado (el comportamiento de antes); 0 = solo ejemplos; +Inf = solo descripción
	largo           TextoLargo                 // estrategia para textos que pasan de max_tokens; cero = cabeza
	met             *Metricas
	Hits            atomic.Uint64
	Misses          atomic.Uint64
}

// NuevoL1Modelo monta L1 sobre un modelo ya abierto. calib puede estar vacía (T por defecto).
func NuevoL1Modelo(m *l1.Modelo, calib chispa3.Calib, cacheEsquemas int) *L1 {
	c := newLRU[map[string][]float32](cacheEsquemas, BytesCacheL1Defecto, costeEmbeddings)
	return &L1{m: m, calib: calib, cache: c}
}

// costeEmbeddings es el tamaño de los embeddings de opción de un esquema: float32 por componente más id y cabeceras.
func costeEmbeddings(v map[string][]float32) (n int) {
	for id, e := range v {
		n += len(id) + 4*len(e) + 24 + 48
	}
	return n
}

// ConCacheBytes cambia el tope en bytes de la caché de esquemas (descarta lo cacheado); mb <= 0 deja el de por defecto.
// Debe llamarse antes de usar L1.
func (l *L1) ConCacheBytes(mb int) *L1 {
	if mb > 0 {
		l.cache = newLRU[map[string][]float32](0, mb<<20, costeEmbeddings)
	}
	return l
}

// UsaMetricas conecta L1 con /metrics (chispa_cache_bytes{cache="l1"}); lo hace NuevaCascada.
func (l *L1) UsaMetricas(m *Metricas) {
	l.met = m
	if m != nil {
		m.FijaCalib(VistaCalibCapa("L1", l.calib, OrigenFichero, !l.sinCalibFichero))
		m.FijaCacheBytes("l1", func() int64 { return l.cache.Bytes() })
	}
}

// ConSoporte activa el prototipo encogido: con una pregunta presente en sopl (SOPL1), el prototipo de cada opción es
// normaliza((1−w)·p_desc + w·media(ejemplos)), w = k/(k+λ). lambda nil (apagado) deja L1 como estaba; λ = 0 usa solo los ejemplos y λ = +Inf solo la descripción. Debe llamarse antes
// de usar L1 (no es seguro con peticiones en curso). Un soporte de otra dimensión que el modelo se ignora.
func (l *L1) ConSoporte(sopl *chispa3.Sopl1, lambda *float64) *L1 {
	if sopl != nil && sopl.Dim() != l.m.Dim() {
		sopl = nil
	}
	l.sopl, l.lambda = sopl, lambda
	return l
}

// ConTextoLargo fija la estrategia para textos que pasan de max_tokens del modelo (ventana_l1 si no es 0). Con cabeza (el
// valor cero) L1 queda como estaba. Debe llamarse antes de usar L1.
func (l *L1) ConTextoLargo(tl TextoLargo) *L1 {
	l.largo = tl
	return l
}

// ventanasMsg devuelve el embedding de cada ventana del mensaje (las que no tienen tokens se omiten) y cuenta en /metrics los
// textos que pasan del tope. Sin estrategia, o con un texto que cabe, es la única ventana de siempre (Embed del texto entero).
func (l *L1) ventanasMsg(ctx context.Context, estado string) [][]float32 {
	dim := l.m.Dim()
	un := func(ids []int32) [][]float32 {
		e := make([]float32, dim)
		if !l.m.EmbedIDs(ids, e) {
			return nil
		}
		return [][]float32{e}
	}
	n := l.m.MaxTokens()
	if l.largo.VentanaL1 > 0 {
		n = min(n, l.largo.VentanaL1)
	}
	if !l.largo.Activa() {
		ids, trunc := l.m.TokenizarTruncado(estado)
		if trunc {
			l.textoLargo(ctx, estado, 1)
		}
		return un(ids)
	}
	todo := l.m.TokenizarSinTope(estado, l.largo.NecesitaTokens(n)*16)
	if len(todo) <= n {
		ids, trunc := l.m.TokenizarTruncado(estado) // cabe en la ventana: lo de siempre
		if trunc {
			l.textoLargo(ctx, estado, 1)
		}
		return un(ids)
	}
	// Memoria por texto: las ventanas se eligen, se embeben y se cobran una vez por petición; todas las preguntas sobre el mismo
	// texto usan las mismas ventanas, sea cual sea su orden o cuántas haya en la petición.
	pr := presupuestoDe(ctx)
	pr.mu.Lock()
	if pr.l1v == nil {
		pr.l1v = map[string]*ventanasL1Memo{}
	}
	m := pr.l1v[estado]
	if m == nil {
		m = &ventanasL1Memo{}
		pr.l1v[estado] = m
	}
	pr.mu.Unlock()
	m.once.Do(func() {
		ws := tok.Trocear(todo, n, l.largo)
		if cupo := pr.cupoTrozos(capaL1, l.largo.Trozos()); len(ws) > cupo {
			ws = ws[:cupo]
		}
		pr.cobraTrozos(capaL1, len(ws))
		for _, w := range ws {
			m.v = append(m.v, un(w)...)
		}
		l.textoLargo(ctx, estado, len(ws))
	})
	return m.v
}

// textoLargo cuenta en /metrics un texto largo y sus ventanas una sola vez por petición, aunque tenga muchas preguntas.
func (l *L1) textoLargo(ctx context.Context, estado string, ventanas int) {
	pr := presupuestoDe(ctx)
	pr.mu.Lock()
	visto := pr.l1[estado]
	if pr.l1 == nil {
		pr.l1 = map[string]bool{}
	}
	pr.l1[estado] = true
	pr.mu.Unlock()
	if !visto {
		l.met.ObservaTextoLargo("L1", ventanas)
	}
}

func (l *L1) Nombre() string { return "L1" }

func (l *L1) params(tipo string) chispa3.ParamsTipo { return paramsDeCapa(l.met, "L1", l.calib, tipo) }

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
	var sop *chispa3.EntradaSopl1
	if l.sopl != nil && l.lambda != nil {
		sop, _ = l.sopl.Buscar(ClaveConj(p))
	}
	for _, o := range p.Opciones {
		e := make([]float32, l.m.Dim())
		l.m.Embed(textoOpcion(p, o), e)
		if sop != nil {
			if k, media, ok := sop.Opcion(o.ID, l.m.Dim()); ok {
				e = chispa3.Mezclar(e, media, chispa3.PesoSoporte(k, l.lambda))
			}
		}
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
	if len(p.Opciones) == 0 {
		return Respuesta{}, nil
	}
	msgs := l.ventanasMsg(ctx, p.Estado)
	if len(msgs) == 0 {
		return Respuesta{}, nil
	}
	ops := l.opciones(p)
	sims := make([][]float64, len(msgs))
	for w, msg := range msgs {
		sims[w] = make([]float64, len(p.Opciones))
		for i, o := range p.Opciones {
			sims[w][i] = coseno(msg, ops[o.ID])
		}
	}
	agg := l.largo.Agg()
	if p.Kind == KindMulti { // cada opción, un sí/no sobre su propia similitud: se agregan las similitudes
		return respuestaMulti(p, agregarSims(sims, agg), l.calib), nil
	}
	rs := make([]Respuesta, len(sims))
	theta := 0.5
	for w, s := range sims {
		switch p.Kind {
		case KindNoul: // la consulta es la opción «true»
			prm := l.params("noul")
			theta = prm.Theta
			var st float64
			for i, o := range p.Opciones {
				if o.ID == "true" {
					st = s[i]
				}
			}
			rs[w] = respuestaNoul(prm.A*st+prm.B, prm.Theta)
		case KindScore:
			rs[w] = respuestaScore(p, s, l.paramsScore().T)
		default:
			rs[w] = respuestaSoftmax(p, s, l.params("choice").T)
		}
	}
	return agregarRespuestas(p, rs, agg, theta), nil
}

// paramsScore: la T de «score» si CALIB la trae; si no, la de choice (o la de por defecto).
func (l *L1) paramsScore() chispa3.ParamsTipo {
	if p, ok := l.calib.Tipos["score"]; ok && p.T > 0 {
		return p
	}
	if _, ok := l.calib.Tipos["choice"]; !ok {
		l.met.CalibDefecto("L1", "score")
		return paramsDe(l.calib, "score")
	}
	return l.params("choice")
}

// respuestaScore: softmax de coseno/T sobre los niveles (probs por id, como L2) y salida
// ordinal: answer es el nivel mediano (primero con masa acumulada ≥ 0,5) y conf su probabilidad,
// así que una distribución repartida entre niveles lejanos baja la confianza y escala.
func respuestaScore(p Pregunta, sims []float64, T float64) Respuesta {
	r := respuestaSoftmax(p, sims, T)
	var acc float64
	for _, o := range opcionesPorNivel(p.Opciones) {
		acc += r.Probs[o.ID]
		if acc >= 0.5 {
			r.Answer, r.Conf = o.ID, r.Probs[o.ID]
			break
		}
	}
	return r
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
