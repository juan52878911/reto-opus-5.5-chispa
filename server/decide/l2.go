package decide

import (
	"context"
	"errors"
	"fmt"
	"math"
	"strconv"
	"sync"
	"sync/atomic"
	"time"

	"chispa/format/chispa3"
)

// Tokenizador convierte un texto en ids del tokenizador original de e5 (con «query: »
// delante, tokens especiales y recorte a `chispa.consulta.max_len`, 128 por defecto), que es lo que espera el ONNX de L2.
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
	multi indiceCalib // índice de CALIB de multi, calculado una vez

	// Torres al vuelo para esquemas que ESQUEMAS no trae (nil = sin opinión, como antes).
	torres CodificadorTorre
	cache  *LRU[torreDin] // ClaveTorre → torre cuantizada de una opción (o de la consulta, en noul y score)
	// maxNuevas es el tope de torres por calcular en una sola petición; por encima, L2 no opina.
	maxNuevas int
	// vuelo agrupa los cálculos en curso por ClaveTorre (singleflight): N peticiones simultáneas de la misma torre la calculan una vez.
	muVuelo sync.Mutex
	vuelo   map[string]*llamadaTorre
	// Hits y Misses cuentan las peticiones de esquema nuevo con todas sus torres en caché / con alguna por calcular.
	Hits, Misses atomic.Uint64
	met          *Metricas  // nil = sin contadores en /metrics
	largo        TextoLargo // estrategia para consultas que pasan de max_len; cero = cabeza

	// Presupuesto global de torres por segundo (ConTorresPorSegundo); tasa 0 = sin tope.
	cuboMu               sync.Mutex
	cuboTasa, cuboFichas float64
	cuboT                time.Time
}

// SesionSCtx es SesionS que espera su turno de ORT respetando el ctx; L2 la usa si la sesión la implementa.
type SesionSCtx interface {
	RanurasCtx(ctx context.Context, ids []int64) ([][]float32, error)
}

// CodificadorTorreCtx es CodificadorTorre que espera su turno de ORT respetando el ctx; L2 lo usa si el codificador lo implementa.
type CodificadorTorreCtx interface {
	TorreCtx(ctx context.Context, texto string) ([]float32, error)
}

// ErrPresupuestoTorres: se agotó el presupuesto global de torres por segundo (L2.ConTorresPorSegundo); L2 no opina.
var ErrPresupuestoTorres = errors.New("L2: presupuesto de torres por segundo agotado")

// errSinPresupuestoTorres: a la petición ya no le quedan torres nuevas; L2.decidir lo traduce en Respuesta{Incompleto}
// para que la escalada no se cachee bajo el nonce.
var errSinPresupuestoTorres = errors.New("L2: presupuesto de torres nuevas de la petición agotado")

// ConTorresPorSegundo fija un tope global de torres calculadas por segundo (cubo con ráfaga de igual tamaño); n <= 0 lo
// quita. Por encima, L2 no opina (como con el tope por petición) en vez de saturar el único ORT con textos únicos.
func (l *L2) ConTorresPorSegundo(n float64) *L2 {
	l.cuboMu.Lock()
	l.cuboTasa, l.cuboFichas, l.cuboT = n, n, time.Now()
	l.cuboMu.Unlock()
	return l
}

func (l *L2) tomaFichaTorre() bool {
	l.cuboMu.Lock()
	defer l.cuboMu.Unlock()
	if l.cuboTasa <= 0 {
		return true
	}
	ahora := time.Now()
	l.cuboFichas = math.Min(l.cuboTasa, l.cuboFichas+ahora.Sub(l.cuboT).Seconds()*l.cuboTasa)
	l.cuboT = ahora
	if l.cuboFichas < 1 {
		return false
	}
	l.cuboFichas--
	return true
}

// UsaMetricas conecta L2 con /metrics (lo hace NuevaCascada).
func (l *L2) UsaMetricas(m *Metricas) {
	l.met = m
	if m != nil {
		m.FijaCacheBytes("torres", func() int64 {
			if l.cache == nil {
				return 0
			}
			return l.cache.Bytes()
		})
	}
}

// CodificadorTorre calcula la torre de opción h (d floats, normalizada) de un texto de pasaje «passage: pregunta · opción ·
// descripción» (model/l2/modelo.py, texto_opcion). Es el e5 de pasaje más la cabeza de torre: la implementación real es
// torre.Codificador (segundo ONNX, sección TORR del .chispa).
type CodificadorTorre interface {
	Torre(texto string) ([]float32, error)
}

type llamadaTorre struct {
	done chan struct{}
	t    torreDin
	err  error
}

type torreDin struct {
	v []byte
	e float32
}

// MaxTorresNuevasPorDefecto es el tope de torres que una petición puede obligar a calcular.
const MaxTorresNuevasPorDefecto = 64

// ConTorres activa el cálculo al vuelo de torres para esquemas nuevos, cacheadas en un LRU de cacheTorres torres
// (capacidad aproximada: el LRU se reparte en fragmentos).
func (l *L2) ConTorres(c CodificadorTorre, cacheTorres int) *L2 {
	l.torres = c
	l.cache = newLRU[torreDin](cacheTorres, BytesCacheTorresDefecto, func(t torreDin) int { return len(t.v) + 4 + 24 })
	l.vuelo = map[string]*llamadaTorre{}
	if l.maxNuevas == 0 {
		l.maxNuevas = MaxTorresNuevasPorDefecto
	}
	return l
}

// ConMaxTorresNuevas fija cuántas torres sin cachear puede calcular una petición (<= 0: el valor por defecto).
func (l *L2) ConMaxTorresNuevas(n int) *L2 {
	if n <= 0 {
		n = MaxTorresNuevasPorDefecto
	}
	l.maxNuevas = n
	return l
}

// torreUnica devuelve la torre de k: de la caché, o calculándola una sola vez aunque la pidan varias goroutines a la vez.
func (l *L2) torreUnica(ctx context.Context, k, texto string) (t torreDin, err error) {
	if t, ok := l.cache.Get(k); ok {
		l.met.sube(func(m *Metricas) *atomic.Uint64 { return &m.TorresCacheAciertos })
		return t, nil
	}
	l.muVuelo.Lock()
	if t, ok := l.cache.Get(k); ok { // otra la acaba de terminar
		l.muVuelo.Unlock()
		l.met.sube(func(m *Metricas) *atomic.Uint64 { return &m.TorresCacheAciertos })
		return t, nil
	}
	if c, ok := l.vuelo[k]; ok {
		l.muVuelo.Unlock()
		l.met.sube(func(m *Metricas) *atomic.Uint64 { return &m.TorresEsperas })
		select {
		case <-c.done:
			return c.t, c.err
		case <-ctx.Done():
			return torreDin{}, ctx.Err()
		}
	}
	c := &llamadaTorre{done: make(chan struct{})}
	l.vuelo[k] = c
	l.muVuelo.Unlock()

	// Aunque Torre entre en pánico, la clave se libera y los que esperan despiertan con error.
	defer func() {
		if r := recover(); r != nil {
			c.t, c.err = torreDin{}, fmt.Errorf("torre: pánico: %v", r)
			t, err = torreDin{}, c.err // el líder también recibe el error, no una torre vacía
		}
		l.muVuelo.Lock()
		delete(l.vuelo, k)
		l.muVuelo.Unlock()
		close(c.done)
	}()
	if !l.tomaFichaTorre() {
		c.err = ErrPresupuestoTorres
		return torreDin{}, c.err
	}
	t0 := time.Now()
	var h []float32
	if tc, ok := l.torres.(CodificadorTorreCtx); ok {
		h, err = tc.TorreCtx(ctx, texto)
	} else {
		h, err = l.torres.Torre(texto)
	}
	l.met.ObservaTorre(time.Since(t0), err)
	if err == nil {
		c.t = cuantizarTorre(h)
		l.cache.Put(k, c.t)
	}
	c.err = err
	return c.t, c.err
}

type claveCtxPresupuesto struct{}

// presupuestoTorres cuenta las torres nuevas que ha calculado una petición.
type presupuestoTorres struct{ usadas atomic.Int64 }

// conPresupuesto devuelve un ctx con un presupuesto de torres nuevas propio de la petición, si no lo tenía ya.
func conPresupuesto(ctx context.Context) context.Context {
	if ctx.Value(claveCtxPresupuesto{}) != nil {
		return ctx
	}
	return context.WithValue(ctx, claveCtxPresupuesto{}, &presupuestoTorres{})
}

func presupuestoDe(ctx context.Context) *presupuestoTorres {
	if p, ok := ctx.Value(claveCtxPresupuesto{}).(*presupuestoTorres); ok {
		return p
	}
	return &presupuestoTorres{} // llamada directa sin petición: presupuesto propio
}

// torresNuevas calcula (o recupera de la caché) las torres de un esquema que ESQUEMAS no trae, en el orden de OpcionesConsulta.
// errSinPresupuestoTorres si a la petición (todas sus preguntas juntas, ver conPresupuesto) ya no le quedan torres nuevas por calcular: L2 no opina.
func (l *L2) torresNuevas(ctx context.Context, p Pregunta) (ts []torreDin, ok bool, err error) {
	ops := OpcionesConsulta(p)
	faltan := 0
	for _, o := range ops {
		if _, hit := l.cache.Get(ClaveTorre(p.Texto, o)); !hit {
			faltan++
		}
	}
	if faltan > 0 {
		pr := presupuestoDe(ctx)
		if pr.usadas.Add(int64(faltan)) > int64(l.maxNuevas) {
			pr.usadas.Add(-int64(faltan))
			l.met.sube(func(m *Metricas) *atomic.Uint64 { return &m.PresupuestoAgotado })
			return nil, false, errSinPresupuestoTorres
		}
	}
	out := make([]torreDin, len(ops))
	for i, o := range ops {
		if err := ctx.Err(); err != nil {
			return nil, false, err
		}
		if out[i], err = l.torreUnica(ctx, ClaveTorre(p.Texto, o), TextoTorre(p.Texto, o)); err != nil {
			if errors.Is(err, ErrPresupuestoTorres) {
				l.met.sube(func(m *Metricas) *atomic.Uint64 { return &m.PresupuestoAgotado })
				return nil, false, errSinPresupuestoTorres
			}
			return nil, false, err
		}
	}
	if faltan == 0 {
		l.Hits.Add(1)
	} else {
		l.Misses.Add(1)
	}
	return out, true, nil
}

// ErrSinTokenizador: L2 necesita el tokenizador de e5.
var ErrSinTokenizador = errors.New("L2: hace falta un Tokenizador de e5 (no hay uno en Go todavía)")

// NuevoL2Con monta L2 sobre cualquier SesionS (el ONNX real solo existe con la etiqueta ort).
func NuevoL2Con(ses SesionS, esq *chispa3.Esquemas, calib chispa3.Calib, tok Tokenizador) *L2 {
	l := &L2{ses: ses, tok: tok, esq: esq, calib: calib}
	l.multi.carga(calib)
	return l
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
	Similitudes(ctx context.Context, p Pregunta) (S [][]float32, sims []float64, ok bool, err error)
}

func (l *L2) Similitudes(ctx context.Context, p Pregunta) ([][]float32, []float64, bool, error) {
	S, sims, _, ok, err := l.similitudesTorres(ctx, p)
	return S, sims, ok, err
}

// ventana son las ranuras de una ventana del texto y su MaxSim contra cada torre.
type ventana struct {
	S    [][]float32
	sims []float64
}

// ConTextoLargo fija la estrategia para consultas que pasan de max_len (cabeza_cola, trozos con agregación max o media).
// Con cabeza (el valor cero) L2 queda como estaba. Debe llamarse antes de usar L2.
func (l *L2) ConTextoLargo(tl TextoLargo) *L2 {
	l.largo = tl
	return l
}

// similitudesTorres es la ventana 0 de similitudesVentanas: con cabeza (o un texto que cabe) es la única, y con otra estrategia
// es la cabeza del texto; así quien no agrega ventanas (Similitudes, L2c sin trozos) sigue viendo lo de siempre.
func (l *L2) similitudesTorres(ctx context.Context, p Pregunta) ([][]float32, []float64, []torreDin, bool, error) {
	vs, ts, ok, err := l.similitudesVentanas(ctx, p)
	if err != nil || !ok {
		return nil, nil, nil, ok, err
	}
	return vs[0].S, vs[0].sims, ts, true, nil
}

// similitudesTorres es Similitudes devolviendo además las torres con las que puntuó cada opción (choice) o la única
// (noul y score), para que L2c mezcle con esas mismas. Devuelve una ventana por trozo del texto (ver ConTextoLargo).
func (l *L2) similitudesVentanas(ctx context.Context, p Pregunta) ([]ventana, []torreDin, bool, error) {
	// Puntuar antes de llamar al ONNX: sin torres para este esquema no hay nada que hacer.
	type vt = torreDin
	var ts []vt
	if p.Kind == KindChoice || p.Kind == KindMulti { // una torre por opción
		for _, o := range p.Opciones {
			v, e, ok := buscarTorre(l.esq, p, []Opcion{o})
			if !ok {
				return l.similitudesNuevas(ctx, p)
			}
			ts = append(ts, vt{v, e})
		}
	} else {
		v, e, ok := buscarTorre(l.esq, p, opcionesUnica(p))
		if !ok {
			return l.similitudesNuevas(ctx, p)
		}
		ts = []vt{{v, e}}
	}
	return l.simsConTorres(ctx, p, ts)
}

// similitudesNuevas: esquema ausente de ESQUEMAS. Sin CodificadorTorre, sin opinión; con él, torres al vuelo.
func (l *L2) similitudesNuevas(ctx context.Context, p Pregunta) ([]ventana, []torreDin, bool, error) {
	if l.torres == nil {
		return nil, nil, false, nil
	}
	ts, ok, err := l.torresNuevas(ctx, p)
	if err != nil || !ok {
		return nil, nil, false, err
	}
	return l.simsConTorres(ctx, p, ts)
}

func (l *L2) simsConTorres(ctx context.Context, p Pregunta, ts []torreDin) ([]ventana, []torreDin, bool, error) {
	vs, ok, err := l.ventanasDeCtx(ctx, p, ts)
	if err != nil || !ok {
		return nil, nil, ok, err
	}
	return vs, ts, true, nil
}

func (l *L2) simsDe(p Pregunta, ts []torreDin) ([][]float32, []float64, bool, error) {
	return l.simsDeCtx(context.Background(), p, ts)
}

// simsDeCtx es la ventana 0 de ventanasDeCtx.
func (l *L2) simsDeCtx(ctx context.Context, p Pregunta, ts []torreDin) ([][]float32, []float64, bool, error) {
	vs, ok, err := l.ventanasDeCtx(ctx, p, ts)
	if err != nil || !ok {
		return nil, nil, ok, err
	}
	return vs[0].S, vs[0].sims, true, nil
}

// idsConsulta son los ids de cada ventana del mensaje. Un tokenizador que sabe trocear da las de la estrategia (y cuenta en
// /metrics los textos que pasan de max_len); si no, la única de siempre.
func (l *L2) idsConsulta(estado string) [][]int64 {
	tt, ok := l.tok.(TokenizadorTrozos)
	if !ok {
		return [][]int64{l.tok.IDs(estado)}
	}
	ws, largo := tt.Trozos(estado, l.largo)
	if largo {
		l.met.ObservaTextoLargo("L2", len(ws))
	}
	return ws
}

// ventanasDeCtx corre el ONNX en cada ventana del mensaje (como mucho max_trozos) y puntúa cada una contra las torres.
func (l *L2) ventanasDeCtx(ctx context.Context, p Pregunta, ts []torreDin) ([]ventana, bool, error) {
	if l.tok == nil {
		return nil, false, fmt.Errorf("L2: falta el tokenizador")
	}
	var vs []ventana
	for _, ids := range l.idsConsulta(p.Estado) {
		var S [][]float32
		var err error
		if sc, ok := l.ses.(SesionSCtx); ok {
			S, err = sc.RanurasCtx(ctx, ids)
		} else {
			S, err = l.ses.Ranuras(ids)
		}
		if err != nil {
			return nil, false, err
		}
		if len(S) == 0 {
			return nil, false, fmt.Errorf("L2: el codificador no devolvió ranuras")
		}
		for _, t := range ts {
			if len(S[0]) != len(t.v) {
				return nil, false, fmt.Errorf("L2: ranuras de dimensión %d y torres de %d", len(S[0]), len(t.v))
			}
		}
		sims := make([]float64, len(ts))
		for i, t := range ts {
			sims[i] = maxsim(S, t.v, t.e)
		}
		vs = append(vs, ventana{S, sims})
	}
	return vs, true, nil
}

// esquemaNuevo dice si ESQUEMAS no trae las torres de la pregunta (las mismas que busca Similitudes).
func (l *L2) esquemaNuevo(p Pregunta) bool {
	if p.Kind == KindChoice || p.Kind == KindMulti {
		for _, o := range p.Opciones {
			if _, _, ok := buscarTorre(l.esq, p, []Opcion{o}); !ok {
				return true
			}
		}
		return false
	}
	_, _, ok := buscarTorre(l.esq, p, opcionesUnica(p))
	return !ok
}

func clavesDe(ops []Opcion) []chispa3.OpcionClave {
	out := make([]chispa3.OpcionClave, len(ops))
	for i, o := range ops {
		out[i] = chispa3.OpcionClave{ID: o.ID, Descripcion: o.Description}
	}
	return out
}

// opcionesUnica son las opciones de la única torre de noul (false y true, con la descripción de la petición si la trae) y
// score (todas).
func opcionesUnica(p Pregunta) []Opcion {
	if p.Kind != KindNoul {
		return p.Opciones
	}
	out := []Opcion{{ID: "false"}, {ID: "true"}}
	for _, o := range p.Opciones {
		for i := range out {
			if o.ID == out[i].ID {
				out[i].Description = o.Description
			}
		}
	}
	return out
}

// buscarTorre busca en ESQUEMAS la torre de estas opciones de la pregunta con la clave de la versión de la sección
// (HashEsquema en v1, HashEsquema2 en v2: con v2, otra descripción u otro kind es otro esquema).
func buscarTorre(esq *chispa3.Esquemas, p Pregunta, ops []Opcion) ([]byte, float32, bool) {
	return esq.BuscarEsquema(p.Texto, p.Kind, clavesDe(ops))
}

// marcarNuevo anota en r si la pregunta venía de torres al vuelo.
func (l *L2) marcarNuevo(p Pregunta, r Respuesta, err error) (Respuesta, error) {
	if l != nil && err == nil && r.Conf > 0 {
		r.EsquemaNuevo = l.esquemaNuevo(p)
	}
	return r, err
}

func (l *L2) Decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	r, err := l.decidir(ctx, p)
	return l.marcarNuevo(p, r, err)
}

func (l *L2) decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	if len(p.Opciones) == 0 {
		return Respuesta{}, nil
	}
	var esqMulti string
	if p.Kind == KindMulti { // sin multi_l2 no opinará: no se gastan torres (ni presupuesto de la petición) en calcularlas
		var opina bool
		if esqMulti, opina = l.multi.opinaMultiL2(p, l.calib, l.met); !opina {
			return Respuesta{}, nil
		}
	}
	vs, _, ok, err := l.similitudesVentanas(ctx, p)
	if errors.Is(err, errSinPresupuestoTorres) {
		return Respuesta{Incompleto: true}, nil
	}
	if err != nil || !ok {
		return Respuesta{}, err
	}
	agg := l.largo.Agg()
	if p.Kind == KindMulti { // se agregan las similitudes: cada opción es un sí/no sobre la suya
		todas := make([][]float64, len(vs))
		for i, v := range vs {
			todas[i] = v.sims
		}
		return respuestaMultiCapa(p, agregarSims(todas, agg), l.calib, l.multi.porEsquema, claveMultiL2, esqMulti), nil
	}
	rs := make([]Respuesta, len(vs))
	theta := 0.5
	for i, v := range vs {
		switch p.Kind {
		case KindChoice:
			rs[i] = respuestaSoftmax(p, v.sims, paramsDe(l.calib, "choice").T)
		case KindNoul:
			prm := paramsDe(l.calib, "noul")
			theta = prm.Theta
			rs[i] = respuestaNoul(prm.A*v.sims[0]+prm.B, prm.Theta)
		default:
			r, err := l.score(p, v.sims[0])
			if err != nil {
				return Respuesta{}, err
			}
			rs[i] = r
		}
	}
	return agregarRespuestas(p, rs, agg, theta), nil
}

// score: CORAL, P(y>j) = σ(a·s − b_j); b_1 = b de «scoreK» y b_j = b_{j−1} + a de «scoreK#j» (j = 1..K−2, como a_calib_chispa).
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
			inc, ok := l.calib.Tipos[fmt.Sprintf("%s#%d", clave, j)]
			if !ok {
				return Respuesta{}, nil
			}
			b += inc.A
		}
		sup[j] = 1 / (1 + math.Exp(-(base.A*s - b)))
	}
	r := Respuesta{Probs: make(map[string]float64, K)}
	var suma float64
	for i := 0; i < K; i++ {
		hi, lo := 1.0, 0.0
		if i > 0 {
			hi = sup[i-1]
		}
		if i < K-1 {
			lo = sup[i]
		}
		d := math.Max(hi-lo, 0)
		r.Probs[p.Opciones[i].ID] = d
		suma += d
	}
	for id, d := range r.Probs { // con acumuladas no monótonas las diferencias recortadas suman > 1: se normaliza
		r.Probs[id] = d / suma
	}
	// Mediana CORAL: nivel 1 + número de umbrales con P(y > j) > 0,5 (como L1). Con acumuladas no monótonas, el argmax
	// de las diferencias podría salir de diferencias negativas recortadas.
	k := 0
	for _, x := range sup {
		if x > 0.5 {
			k++
		}
	}
	r.Answer = p.Opciones[k].ID
	r.Conf = r.Probs[r.Answer]
	return r, nil
}
