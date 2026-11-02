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
	"chispa/runtime/tok"
	"chispa/runtime/torre"
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
	ses             SesionS
	tok             Tokenizador
	esq             *chispa3.Esquemas
	calib           chispa3.Calib
	origenCalib     string      // de dónde salen los tipos de calib: OrigenFichero u OrigenTiposL2
	sinCalibFichero bool        // el .chispa no trae CALIB
	multi           indiceCalib // índice de CALIB de multi, calculado una vez

	// Torres al vuelo para esquemas que ESQUEMAS no trae (nil = sin opinión, como antes).
	torres CodificadorTorre
	cache  *LRU[torreDin] // ClaveTorre → torre cuantizada de una opción (o de la consulta, en noul y score)
	// maxNuevas es el tope de torres por calcular en una sola petición; por encima, L2 no opina.
	maxNuevas int
	// textoTorre es META.texto_torre del .chispa («v1» / «v2_sin_id»); vacío = v1.
	textoTorre string
	// motivoSinTorre: por qué no hay torre al vuelo pese a traer TORR (texto_torre_inconsistente); "" = ninguno.
	motivoSinTorre string
	// cacheTorresEf es el tamaño efectivo de la caché de torres; cacheTorresCfg el que pedía la config si hubo que subirlo (0 = sin ajuste).
	cacheTorresEf, cacheTorresCfg int
	// vuelo agrupa los cálculos en curso por ClaveTorre (singleflight): N peticiones simultáneas de la misma torre la calculan una vez.
	muVuelo sync.Mutex
	vuelo   map[string]*llamadaTorre
	// Hits y Misses cuentan las peticiones de esquema nuevo con todas sus torres en caché / con alguna por calcular.
	Hits, Misses atomic.Uint64
	met          *Metricas  // nil = sin contadores en /metrics
	largo        TextoLargo // estrategia para consultas que pasan de max_len; cero = cabeza

	// Presupuesto global de torres por segundo (ConTorresPorSegundo); nil = sin tope.
	cubo *cuboTorres
}

// cuboTorres es un cubo de fichas de torres por segundo: recarga `tasa` fichas/s y su capacidad (ráfaga) la fija quien lo usa, de
// modo que una pregunta completa de opciones nuevas siempre cabe (max(tasa, max_torres_nuevas, 1)). Nace lleno.
type cuboTorres struct {
	mu     sync.Mutex
	tasa   float64
	fichas float64
	t      time.Time
	lleno  bool             // aún no se ha tocado: la primera toma lo llena con su ráfaga
	reloj  func() time.Time // nil = time.Now; los tests y el autenticador inyectan el suyo
}

func nuevoCuboTorres(tasa float64) *cuboTorres { return nuevoCuboTorresReloj(tasa, nil) }

func nuevoCuboTorresReloj(tasa float64, reloj func() time.Time) *cuboTorres {
	c := &cuboTorres{tasa: tasa, reloj: reloj}
	c.t = c.now()
	return c
}

func (c *cuboTorres) now() time.Time {
	if c.reloj != nil {
		return c.reloj()
	}
	return time.Now()
}

func rafagaTorres(tasa float64, maxNuevas int) float64 {
	return math.Max(math.Max(tasa, float64(maxNuevas)), 1)
}

// toma coge una ficha; false si no queda (con ráfaga de rafaga fichas como máximo).
func (c *cuboTorres) toma(rafaga float64) bool {
	c.mu.Lock()
	defer c.mu.Unlock()
	ahora := c.now()
	if !c.lleno {
		c.lleno, c.fichas = true, rafaga
	} else {
		c.fichas = math.Min(rafaga, c.fichas+ahora.Sub(c.t).Seconds()*c.tasa)
	}
	c.t = ahora
	if c.fichas < 1 {
		return false
	}
	c.fichas--
	return true
}

// devuelve repone una ficha tomada que no se llegó a gastar.
func (c *cuboTorres) devuelve(rafaga float64) {
	c.mu.Lock()
	c.fichas = math.Min(rafaga, c.fichas+1)
	c.mu.Unlock()
}

// hereda pasa a c las fichas de o (el cubo de la recarga anterior) para que recargar no devuelva la ráfaga entera; con
// distinta tasa se conserva lo que había; la ráfaga lo acota en la siguiente toma.
func (c *cuboTorres) hereda(o *cuboTorres) {
	if c == nil || o == nil || c == o {
		return
	}
	o.mu.Lock()
	fichas := o.fichas + o.now().Sub(o.t).Seconds()*o.tasa
	lleno := o.lleno
	o.mu.Unlock()
	if !lleno {
		return
	}
	c.mu.Lock()
	c.fichas, c.t, c.lleno = fichas, c.now(), true
	c.mu.Unlock()
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

// ConTorresPorSegundo fija un tope global de torres calculadas por segundo (cubo con ráfaga max(n, max_torres_nuevas, 1), que cubre
// una pregunta completa); n <= 0 lo quita. Por encima, L2 no opina (como con el tope por petición) en vez de saturar el único
// ORT con textos únicos.
func (l *L2) ConTorresPorSegundo(n float64) *L2 {
	if n <= 0 {
		l.cubo = nil
	} else {
		l.cubo = nuevoCuboTorres(n)
	}
	return l
}

func (l *L2) cuboGlobalTorres() *cuboTorres {
	if l == nil {
		return nil
	}
	return l.cubo
}

// tomaFichaTorre cobra una torre al cubo de la clave de la petición, si lo tiene, y al global. Con la clave agotada no se toca
// el global: las demás claves no se ven afectadas. Devuelve además la función que deshace el cobro, para cuando el cálculo no
// llega a ejecutarse (ctx vencido esperando turno de ORT): sin ella, el cubo se vaciaría al ritmo de los timeouts y no de los cálculos.
func (l *L2) tomaFichaTorre(ctx context.Context) (deshace func(), ok bool) {
	var ck *cuboTorres
	var rk float64
	if c := cobroDe(ctx); c != nil && c.k.torres != nil {
		ck, rk = c.k.torres, rafagaTorres(c.k.torres.tasa, l.maxNuevas)
		if !ck.toma(rk) {
			return nil, false
		}
	}
	var cg *cuboTorres
	var rg float64
	if l.cubo != nil {
		cg, rg = l.cubo, rafagaTorres(l.cubo.tasa, l.maxNuevas)
		if !cg.toma(rg) {
			if ck != nil {
				ck.devuelve(rk)
			}
			return nil, false
		}
	}
	return func() {
		if ck != nil {
			ck.devuelve(rk)
		}
		if cg != nil {
			cg.devuelve(rg)
		}
	}, true
}

// adoptaCubo hace que el cubo global de l sea el de la recarga anterior (o) si la tasa no cambió: las peticiones en vuelo, que
// siguen cobrando de o, y las nuevas gastan de la misma cuenta. Con otra tasa, hereda las fichas en un cubo nuevo.
func (l *L2) adoptaCubo(o *cuboTorres) {
	if l == nil || l.cubo == nil || o == nil {
		return
	}
	if o.tasa == l.cubo.tasa {
		l.cubo = o
		return
	}
	l.cubo.hereda(o)
}

// UsaMetricas conecta L2 con /metrics (lo hace NuevaCascada).
func (l *L2) UsaMetricas(m *Metricas) {
	l.met = m
	if m != nil {
		or := l.origenCalib
		if or == "" {
			or = OrigenFichero
		}
		m.FijaCalib(VistaCalibCapa("L2", l.calib, or, !l.sinCalibFichero))
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

// MaxTorresNuevasPorDefecto es el tope de torres que una petición puede obligar a calcular. Cubre al menos una pregunta completa
// (MaxOpciones): una pregunta válida nunca queda sin respuesta para siempre por este tope. La protección anti-DoS sigue sobre el
// total de la petición (todas sus preguntas comparten el tope) y, por segundo, sobre ConTorresPorSegundo.
const MaxTorresNuevasPorDefecto = MaxOpciones

// costeTorreAprox son los bytes que cuenta el LRU por torre (dim ≤ 768, clave y sobre-entrada), por exceso.
const costeTorreAprox = 1024

// ConTorres activa el cálculo al vuelo de torres para esquemas nuevos, cacheadas en un LRU de cacheTorres torres
// (capacidad aproximada: el LRU se reparte en fragmentos).
func (l *L2) ConTorres(c CodificadorTorre, cacheTorres int) *L2 {
	l.torres = c
	bytes := max(BytesCacheTorresDefecto, cacheTorres*costeTorreAprox) // una caché mayor que el tope por defecto lleva su propio tope de bytes
	l.cache = newLRU[torreDin](cacheTorres, bytes, func(t torreDin) int { return len(t.v) + 4 + 24 })
	l.vuelo = map[string]*llamadaTorre{}
	if l.maxNuevas == 0 {
		l.maxNuevas = MaxTorresNuevasPorDefecto
	}
	return l
}

// ConMotivoSinTorre anota por qué L2 no calcula torres al vuelo aunque el .chispa traiga TORR (p. ej. texto_torre_inconsistente);
// /healthz lo publica en torre_al_vuelo_motivo y /metrics en chispa_torre_al_vuelo_desactivada.
func (l *L2) ConMotivoSinTorre(m string) *L2 {
	l.motivoSinTorre = m
	return l
}

// ConCacheTorresEfectiva anota el tamaño efectivo de la caché de torres y, si ArmarDesde lo subió, el que pedía la config (0 = sin ajuste).
func (l *L2) ConCacheTorresEfectiva(efectiva, pedida int) *L2 {
	l.cacheTorresEf, l.cacheTorresCfg = efectiva, pedida
	return l
}

// CacheTorresEfectiva es el tamaño efectivo de la caché de torres (0 = sin torres al vuelo) y el pedido por la config si se subió (0 = sin ajuste).
func (l *L2) CacheTorresEfectiva() (efectiva, pedida int) {
	if l == nil {
		return 0, 0
	}
	return l.cacheTorresEf, l.cacheTorresCfg
}

// MotivoSinTorre es el motivo anotado con ConMotivoSinTorre ("" = ninguno).
func (l *L2) MotivoSinTorre() string {
	if l == nil {
		return ""
	}
	return l.motivoSinTorre
}

// ConTextoTorre fija la versión del texto de torre (META.texto_torre); vacío = v1.
func (l *L2) ConTextoTorre(v string) *L2 {
	l.textoTorre = v
	return l
}

// VersionTextoTorre es la versión del texto de torre con que L2 calcula torres al vuelo; "" si no las calcula.
func (l *L2) VersionTextoTorre() string {
	if l == nil || l.torres == nil {
		return ""
	}
	if l.textoTorre == "" {
		return chispa3.TextoTorreV1
	}
	return l.textoTorre
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
// calculada es true solo si esta llamada la calculó ella misma (líder y con éxito): es lo que cobra el cupo de la petición.
//
// Si el líder se cancela (su cliente corta o se queda sin plazo), los que esperaban con el ctx vivo no heredan ese error:
// reintentan y uno pasa a ser el nuevo líder. Se prefiere esto a un ctx desligado del líder porque así un cálculo que nadie
// espera ya no gasta ORT, y cada cálculo sigue atado al plazo de la petición que lo paga.
func (l *L2) torreUnica(ctx context.Context, k, texto string) (t torreDin, calculada bool, err error) {
	for {
		if t, ok := l.cache.Get(k); ok {
			l.met.sube(func(m *Metricas) *atomic.Uint64 { return &m.TorresCacheAciertos })
			return t, false, nil
		}
		l.muVuelo.Lock()
		if t, ok := l.cache.Get(k); ok { // otra la acaba de terminar
			l.muVuelo.Unlock()
			l.met.sube(func(m *Metricas) *atomic.Uint64 { return &m.TorresCacheAciertos })
			return t, false, nil
		}
		c, ok := l.vuelo[k]
		if !ok {
			c = &llamadaTorre{done: make(chan struct{})}
			l.vuelo[k] = c
			l.muVuelo.Unlock()
			t, err = l.calculaTorre(ctx, c, k, texto)
			return t, err == nil, err
		}
		l.muVuelo.Unlock()
		l.met.sube(func(m *Metricas) *atomic.Uint64 { return &m.TorresEsperas })
		select {
		case <-c.done:
			if (errors.Is(c.err, context.Canceled) || errors.Is(c.err, context.DeadlineExceeded) || errors.Is(c.err, ErrPresupuestoTorres)) && ctx.Err() == nil {
				// El líder se canceló, o se quedó sin SU presupuesto (otra clave): no es mi error. Reintento y paso a líder
				// (cobrando a mi propia clave) si nadie más lo ha hecho.
				continue
			}
			return c.t, false, c.err
		case <-ctx.Done():
			return torreDin{}, false, ctx.Err()
		}
	}
}

// calculaTorre es el cálculo del líder del singleflight: c ya está en l.vuelo[k].
func (l *L2) calculaTorre(ctx context.Context, c *llamadaTorre, k, texto string) (t torreDin, err error) {
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
	deshace, ok := l.tomaFichaTorre(ctx)
	if !ok {
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
	if err != nil && (errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded)) && ctx.Err() != nil {
		// El ctx venció antes (o mientras) de esperar turno de ORT: no hubo cálculo que cobrar.
		deshace()
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
type presupuestoTorres struct {
	usadas atomic.Int64

	mu     sync.Mutex
	trozos [2]int                     // ventanas de texto largo ya decididas por la petición, por capa (capaL1, capaL2): L1 no gasta el cupo de L2
	l1v    map[string]*ventanasL1Memo // ventanas de L1 por texto: se embeben y se cobran una vez por petición, no por pregunta
	l1     map[string]bool            // textos largos ya contados en L1 (por texto, no por pregunta)
	l2     map[string]*ranurasMemo    // ranuras de ONNX por texto: una pasada por ventana y petición, no por pregunta
}

// ranurasMemo guarda las ranuras de cada ventana de un texto, calculadas una sola vez en la petición.
type ranurasMemo struct {
	once sync.Once
	rs   [][][]float32
	err  error
}

const (
	capaL1 = 0
	capaL2 = 1
)

// ventanasL1Memo guarda los embeddings de las ventanas de un texto largo en L1, calculados una sola vez en la petición.
type ventanasL1Memo struct {
	once sync.Once
	v    [][]float32
}

// cupoTrozos son las ventanas que aún puede decidir un texto largo de la petición en esa capa: lo que queda de max_trozos, y siempre al
// menos la primera (la cabeza), sin la cual el texto no se podría decidir.
func (p *presupuestoTorres) cupoTrozos(capa, tope int) int {
	p.mu.Lock()
	defer p.mu.Unlock()
	return max(1, tope-p.trozos[capa])
}

func (p *presupuestoTorres) cobraTrozos(capa, n int) {
	p.mu.Lock()
	p.trozos[capa] += n
	p.mu.Unlock()
}

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
	claves := make([]string, len(ops))
	textos := make([]string, len(ops))
	falta := make([]bool, len(ops))
	calculada := make([]bool, len(ops))
	faltan := 0
	for i, o := range ops {
		textos[i] = TextoTorre(l.textoTorre, p, o)
		claves[i] = torre.ClaveTexto(textos[i]) // clave del texto efectivo: depende de las demás opciones en v2
		if _, hit := l.cache.Get(claves[i]); !hit {
			falta[i] = true
			faltan++
		}
	}
	if faltan > 0 {
		pr := presupuestoDe(ctx)
		if tras := pr.usadas.Add(int64(faltan)); tras > int64(l.maxNuevas) {
			// Cupo que aún quedaba: esas torres se calculan y se guardan en la caché aunque la pregunta no opine, para que la
			// siguiente petición avance (con un tope menor que las opciones, la pregunta acaba respondiendo).
			cupo := max(0, l.maxNuevas-int(tras-int64(faltan)))
			pr.usadas.Add(-int64(faltan - cupo))
			for i := range ops {
				if cupo == 0 || ctx.Err() != nil {
					break
				}
				if _, hit := l.cache.Get(claves[i]); hit {
					continue
				}
				_, calc, err := l.torreUnica(ctx, claves[i], textos[i])
				if err != nil {
					break
				}
				if calc { // solo se cobra lo que esta petición calculó, no lo que esperó a otro líder
					cupo--
				}
			}
			pr.usadas.Add(-int64(cupo)) // lo reservado y no gastado vuelve a la petición
			l.met.sube(func(m *Metricas) *atomic.Uint64 { return &m.PresupuestoAgotado })
			return nil, false, errSinPresupuestoTorres
		}
		defer func() { // al salir (error, ctx cancelado) se devuelve el cupo reservado y no gastado
			gastadas := 0
			for i := range falta {
				if falta[i] && calculada[i] {
					gastadas++
				}
			}
			pr.usadas.Add(-int64(faltan - gastadas))
		}()
	}
	out := make([]torreDin, len(ops))
	for i := range ops {
		if err := ctx.Err(); err != nil {
			return nil, false, err
		}
		var calc bool
		if out[i], calc, err = l.torreUnica(ctx, claves[i], textos[i]); err != nil {
			if errors.Is(err, ErrPresupuestoTorres) {
				l.met.sube(func(m *Metricas) *atomic.Uint64 { return &m.PresupuestoAgotado })
				return nil, false, errSinPresupuestoTorres
			}
			return nil, false, err
		}
		calculada[i] = calc
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
func (l *L2) idsConsulta(pr *presupuestoTorres, estado string) [][]int64 {
	tt, ok := l.tok.(TokenizadorTrozos)
	if !ok {
		return [][]int64{l.tok.IDs(estado)}
	}
	ws, largo := tt.Trozos(estado, l.largo)
	if largo {
		if cupo := pr.cupoTrozos(capaL2, l.largo.Trozos()); len(ws) > cupo {
			ws = ws[:cupo]
		}
		pr.cobraTrozos(capaL2, len(ws))
		l.met.ObservaTextoLargo("L2", len(ws))
	}
	return ws
}

// ranurasConsulta son las ranuras de cada ventana del mensaje, memoizadas por texto en la petición: el ONNX corre una vez por
// ventana aunque la petición haga muchas preguntas sobre el mismo texto.
func (l *L2) ranurasConsulta(ctx context.Context, estado string) ([][][]float32, error) {
	pr := presupuestoDe(ctx)
	pr.mu.Lock()
	if pr.l2 == nil {
		pr.l2 = map[string]*ranurasMemo{}
	}
	m := pr.l2[estado]
	if m == nil {
		m = &ranurasMemo{}
		pr.l2[estado] = m
	}
	pr.mu.Unlock()
	m.once.Do(func() {
		for _, ids := range l.idsConsulta(pr, estado) {
			var S [][]float32
			var err error
			if sc, ok := l.ses.(SesionSCtx); ok {
				S, err = sc.RanurasCtx(ctx, ids)
			} else {
				S, err = l.ses.Ranuras(ids)
			}
			if err != nil {
				m.err = err
				return
			}
			if len(S) == 0 {
				m.err = fmt.Errorf("L2: el codificador no devolvió ranuras")
				return
			}
			m.rs = append(m.rs, S)
		}
	})
	return m.rs, m.err
}

// ventanasDeCtx corre el ONNX en cada ventana del mensaje (como mucho max_trozos) y puntúa cada una contra las torres.
func (l *L2) ventanasDeCtx(ctx context.Context, p Pregunta, ts []torreDin) ([]ventana, bool, error) {
	if l.tok == nil {
		return nil, false, fmt.Errorf("L2: falta el tokenizador")
	}
	rs, err := l.ranurasConsulta(ctx, NormalizarMayusculas(p.Estado))
	if err != nil {
		return nil, false, err
	}
	var vs []ventana
	for _, S := range rs {
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

// opcionesNiveles ordena las opciones de un score por nivel (ids "1".."K", ver tok.NivelesScore). El bool es false si los ids no son
// exactamente 1..K: la capa no opina. No modifica ops.
func opcionesNiveles(ops []Opcion) ([]Opcion, bool) {
	ids := make([]string, len(ops))
	pos := make(map[string]int, len(ops))
	for i, o := range ops {
		ids[i] = o.ID
		pos[o.ID] = i
	}
	niveles, ok := tok.NivelesScore(ids)
	if !ok {
		return nil, false
	}
	out := make([]Opcion, len(ops))
	for i, id := range niveles {
		out[i] = ops[pos[id]]
	}
	return out, true
}

// scoreValido dice si p es un score con ids 1..K (o no es un score): con otros ids ninguna capa opina.
func scoreValido(p Pregunta) bool {
	if p.Kind != KindScore {
		return true
	}
	_, ok := opcionesNiveles(p.Opciones)
	return ok
}

// opcionesUnica son las opciones de la única torre de noul (false y true, con la descripción de la petición si la trae) y
// score (todas).
func opcionesUnica(p Pregunta) []Opcion {
	if p.Kind == KindScore {
		out, _ := opcionesNiveles(p.Opciones) // L2 solo llega aquí con ids 1..K
		return out
	}
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
	if len(p.Opciones) == 0 || !scoreValido(p) {
		return Respuesta{}, nil // score con ids que no son 1..K: no opina (ni se gastan torres)
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
		return Respuesta{Incompleto: true, SinPresupuestoTorres: true}, nil
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
			rs[i] = respuestaSoftmax(p, v.sims, paramsDeCapa(l.met, "L2", l.calib, "choice").T)
		case KindNoul:
			prm := paramsDeCapa(l.met, "L2", l.calib, "noul")
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
	ops, ok := opcionesNiveles(p.Opciones) // el nivel es el valor del id: el orden de la petición no cambia la respuesta
	if !ok {
		return Respuesta{}, nil
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
		r.Probs[ops[i].ID] = d
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
	r.Answer = ops[k].ID
	r.Conf = r.Probs[r.Answer]
	return r, nil
}
