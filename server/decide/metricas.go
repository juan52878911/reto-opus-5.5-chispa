package decide

import (
	"fmt"
	"io"
	"sort"
	"sync"
	"sync/atomic"
	"time"
)

// Buckets de latencia en segundos (formato Prometheus, escrito a mano).
var buckets = []float64{0.00001, 0.00005, 0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1}

type histo struct {
	n   [12]atomic.Uint64 // un contador por bucket + +Inf (no acumulado)
	sum atomic.Uint64     // nanosegundos
}

func (h *histo) observa(d time.Duration) {
	s := d.Seconds()
	i := 0
	for i < len(buckets) && s > buckets[i] {
		i++
	}
	h.n[i].Add(1)
	h.sum.Add(uint64(d.Nanoseconds()))
}

// escribe vuelca el histograma sin etiquetas (las de capa las escribe Escribe a mano).
func (h *histo) escribe(w io.Writer, nombre string) {
	var acc uint64
	for i, b := range buckets {
		acc += h.n[i].Load()
		fmt.Fprintf(w, "%s_bucket{le=\"%g\"} %d\n", nombre, b, acc)
	}
	acc += h.n[len(buckets)].Load()
	fmt.Fprintf(w, "%s_bucket{le=\"+Inf\"} %d\n", nombre, acc)
	fmt.Fprintf(w, "%s_sum %g\n", nombre, float64(h.sum.Load())/1e9)
	fmt.Fprintf(w, "%s_count %d\n", nombre, acc)
}

// Metricas son los contadores de /metrics.
type Metricas struct {
	mu        sync.Mutex
	capas     map[string]*histo
	errCapa   map[string]*atomic.Uint64
	decididas map[string]*atomic.Uint64
	codigos   map[int]*atomic.Uint64

	Preguntas     atomic.Uint64
	Escalados     atomic.Uint64
	NonceHits     atomic.Uint64
	EsquemaHits   func() uint64 // inyectados por el servidor
	EsquemaMisses func() uint64

	// Torres al vuelo de L2 (esquemas que ESQUEMAS no trae). Las suben L2 y L2c; todas son por torre salvo PresupuestoAgotado.
	TorresCalculadas    atomic.Uint64 // pasadas del codificador de torre que terminaron bien
	TorresCacheAciertos atomic.Uint64 // torres servidas de la caché LRU
	TorresEsperas       atomic.Uint64 // torres que esperaron a otra petición en vuelo (singleflight) en vez de calcularse
	TorresErrores       atomic.Uint64 // cálculos de torre fallidos (error o pánico) y esperas que acabaron en error de la calculadora
	PresupuestoAgotado  atomic.Uint64 // preguntas en las que L2 no opinó porque la petición ya había gastado su tope de torres nuevas
	torreLatencia       histo         // duración de cada cálculo de torre

	// Esquema nuevo: preguntas puntuadas por L2 con torres al vuelo.
	EsquemaNuevoPreguntas atomic.Uint64
	EsquemaNuevoDecididas atomic.Uint64 // las que L2 resolvió con su τ de esquema nuevo (el resto subió o escaló)
	tauEsquemaNuevo       *float64      // τ propio de L2 para esquemas nuevos, si la cascada lo tiene

	recargas map[string]*atomic.Uint64 // chispa_recargas_total{resultado}, bajo mu

	Timeouts atomic.Uint64 // peticiones cuyo contexto venció por plazo (p. ej. http.TimeoutHandler)
}

// UsaMetricas lo implementan los decisores que cuentan en /metrics (L2, y L2c por incrustación); NuevaCascada se lo entrega.
type UsaMetricas interface{ UsaMetricas(*Metricas) }

// ObservaTorre apunta el cálculo de una torre (nil-safe: L2 sin métricas no cuenta).
func (m *Metricas) ObservaTorre(d time.Duration, err error) {
	if m == nil {
		return
	}
	if err != nil {
		m.TorresErrores.Add(1)
		return
	}
	m.TorresCalculadas.Add(1)
	m.torreLatencia.observa(d)
}

// sube incrementa c si hay métricas.
func (m *Metricas) sube(c func(*Metricas) *atomic.Uint64) {
	if m != nil {
		c(m).Add(1)
	}
}

// FijaEsquemas apunta la métrica de la caché de esquemas a los contadores del L0 en servicio (cambia con cada recarga).
func (m *Metricas) FijaEsquemas(hits, misses func() uint64) {
	m.mu.Lock()
	m.EsquemaHits, m.EsquemaMisses = hits, misses
	m.mu.Unlock()
}

// Recarga cuenta un intento de recarga del modelo: resultado "ok" o "error".
func (m *Metricas) Recarga(resultado string) { contador(&m.mu, m.recargas, resultado).Add(1) }

func NuevasMetricas() *Metricas {
	return &Metricas{recargas: map[string]*atomic.Uint64{}, capas: map[string]*histo{}, errCapa: map[string]*atomic.Uint64{},
		decididas: map[string]*atomic.Uint64{}, codigos: map[int]*atomic.Uint64{}}
}

func contador[K comparable](mu *sync.Mutex, m map[K]*atomic.Uint64, k K) *atomic.Uint64 {
	mu.Lock()
	defer mu.Unlock()
	c := m[k]
	if c == nil {
		c = new(atomic.Uint64)
		m[k] = c
	}
	return c
}

func (m *Metricas) ObservaCapa(capa string, d time.Duration, err error) {
	m.mu.Lock()
	h := m.capas[capa]
	if h == nil {
		h = new(histo)
		m.capas[capa] = h
	}
	m.mu.Unlock()
	h.observa(d)
	if err != nil {
		contador(&m.mu, m.errCapa, capa).Add(1)
	}
}

func (m *Metricas) Decidida(capa string, escalada bool) {
	m.Preguntas.Add(1)
	if escalada {
		m.Escalados.Add(1)
	}
	contador(&m.mu, m.decididas, capa).Add(1)
}

func (m *Metricas) Peticion(codigo int) { contador(&m.mu, m.codigos, codigo).Add(1) }

func claves[V any](mu *sync.Mutex, m map[string]V) []string {
	mu.Lock()
	defer mu.Unlock()
	ks := make([]string, 0, len(m))
	for k := range m {
		ks = append(ks, k)
	}
	sort.Strings(ks)
	return ks
}

// Escribe vuelca el formato de texto de Prometheus.
func (m *Metricas) Escribe(w io.Writer) {
	fmt.Fprintln(w, "# HELP chispa_peticiones_total Peticiones a /v1/decide por código HTTP.")
	fmt.Fprintln(w, "# TYPE chispa_peticiones_total counter")
	m.mu.Lock()
	cods := make([]int, 0, len(m.codigos))
	for c := range m.codigos {
		cods = append(cods, c)
	}
	sort.Ints(cods)
	for _, c := range cods {
		fmt.Fprintf(w, "chispa_peticiones_total{codigo=\"%d\"} %d\n", c, m.codigos[c].Load())
	}
	m.mu.Unlock()
	fmt.Fprintln(w, "# HELP chispa_preguntas_total Preguntas decididas.")
	fmt.Fprintln(w, "# TYPE chispa_preguntas_total counter")
	fmt.Fprintf(w, "chispa_preguntas_total %d\n", m.Preguntas.Load())
	fmt.Fprintln(w, "# HELP chispa_decididas_total Preguntas por capa que respondió (o escaló, última capa).")
	fmt.Fprintln(w, "# TYPE chispa_decididas_total counter")
	for _, k := range claves(&m.mu, m.decididas) {
		fmt.Fprintf(w, "chispa_decididas_total{capa=%q} %d\n", k, m.decididas[k].Load())
	}
	fmt.Fprintln(w, "# HELP chispa_escalados_total Preguntas escaladas fuera de la cascada.")
	fmt.Fprintln(w, "# TYPE chispa_escalados_total counter")
	fmt.Fprintf(w, "chispa_escalados_total %d\n", m.Escalados.Load())
	fmt.Fprintln(w, "# HELP chispa_capa_errores_total Errores de cada capa.")
	fmt.Fprintln(w, "# TYPE chispa_capa_errores_total counter")
	for _, k := range claves(&m.mu, m.errCapa) {
		fmt.Fprintf(w, "chispa_capa_errores_total{capa=%q} %d\n", k, m.errCapa[k].Load())
	}
	fmt.Fprintln(w, "# HELP chispa_cache_esquemas_total Aciertos y fallos de la caché de esquemas.")
	fmt.Fprintln(w, "# TYPE chispa_cache_esquemas_total counter")
	m.mu.Lock()
	hits, misses, tauNuevo := m.EsquemaHits, m.EsquemaMisses, m.tauEsquemaNuevo
	m.mu.Unlock()
	if hits != nil {
		fmt.Fprintf(w, "chispa_cache_esquemas_total{resultado=\"acierto\"} %d\n", hits())
		fmt.Fprintf(w, "chispa_cache_esquemas_total{resultado=\"fallo\"} %d\n", misses())
	}
	fmt.Fprintln(w, "# HELP chispa_recargas_total Recargas en caliente del .chispa por resultado (ok, error).")
	fmt.Fprintln(w, "# TYPE chispa_recargas_total counter")
	for _, r := range []string{"ok", "error"} {
		fmt.Fprintf(w, "chispa_recargas_total{resultado=%q} %d\n", r, contador(&m.mu, m.recargas, r).Load())
	}
	fmt.Fprintln(w, "# HELP chispa_cache_nonce_aciertos_total Respuestas servidas desde la caché de nonces.")
	fmt.Fprintln(w, "# TYPE chispa_cache_nonce_aciertos_total counter")
	fmt.Fprintf(w, "chispa_cache_nonce_aciertos_total %d\n", m.NonceHits.Load())
	fmt.Fprintln(w, "# HELP chispa_torres_calculadas_total Torres de opción calculadas al vuelo para esquemas nuevos.")
	fmt.Fprintln(w, "# TYPE chispa_torres_calculadas_total counter")
	fmt.Fprintf(w, "chispa_torres_calculadas_total %d\n", m.TorresCalculadas.Load())
	fmt.Fprintln(w, "# HELP chispa_torres_cache_aciertos_total Torres al vuelo servidas desde la caché de torres.")
	fmt.Fprintln(w, "# TYPE chispa_torres_cache_aciertos_total counter")
	fmt.Fprintf(w, "chispa_torres_cache_aciertos_total %d\n", m.TorresCacheAciertos.Load())
	fmt.Fprintln(w, "# HELP chispa_torres_esperas_total Torres que esperaron a un cálculo ya en curso (singleflight).")
	fmt.Fprintln(w, "# TYPE chispa_torres_esperas_total counter")
	fmt.Fprintf(w, "chispa_torres_esperas_total %d\n", m.TorresEsperas.Load())
	fmt.Fprintln(w, "# HELP chispa_torres_errores_total Cálculos de torre fallidos (error o pánico del codificador).")
	fmt.Fprintln(w, "# TYPE chispa_torres_errores_total counter")
	fmt.Fprintf(w, "chispa_torres_errores_total %d\n", m.TorresErrores.Load())
	fmt.Fprintln(w, "# HELP chispa_torres_presupuesto_agotado_total Preguntas en las que L2 no opinó por agotar el tope de torres nuevas de la petición.")
	fmt.Fprintln(w, "# TYPE chispa_torres_presupuesto_agotado_total counter")
	fmt.Fprintf(w, "chispa_torres_presupuesto_agotado_total %d\n", m.PresupuestoAgotado.Load())
	fmt.Fprintln(w, "# HELP chispa_torre_latencia_segundos Latencia de cada cálculo de torre al vuelo.")
	fmt.Fprintln(w, "# TYPE chispa_torre_latencia_segundos histogram")
	m.torreLatencia.escribe(w, "chispa_torre_latencia_segundos")
	fmt.Fprintln(w, "# HELP chispa_esquema_nuevo_preguntas_total Preguntas que L2 puntuó con torres al vuelo (esquema ausente de ESQUEMAS).")
	fmt.Fprintln(w, "# TYPE chispa_esquema_nuevo_preguntas_total counter")
	fmt.Fprintf(w, "chispa_esquema_nuevo_preguntas_total %d\n", m.EsquemaNuevoPreguntas.Load())
	fmt.Fprintln(w, "# HELP chispa_esquema_nuevo_decididas_total Preguntas de esquema nuevo que L2 resolvió con su τ de esquema nuevo.")
	fmt.Fprintln(w, "# TYPE chispa_esquema_nuevo_decididas_total counter")
	fmt.Fprintf(w, "chispa_esquema_nuevo_decididas_total %d\n", m.EsquemaNuevoDecididas.Load())
	if tauNuevo != nil {
		fmt.Fprintln(w, "# HELP chispa_esquema_nuevo_tau τ de L2 para esquemas nuevos (solo si la config lo fija).")
		fmt.Fprintln(w, "# TYPE chispa_esquema_nuevo_tau gauge")
		fmt.Fprintf(w, "chispa_esquema_nuevo_tau %g\n", *tauNuevo)
	}
	fmt.Fprintln(w, "# HELP chispa_timeouts_total Peticiones a /v1/decide cuyo plazo venció.")
	fmt.Fprintln(w, "# TYPE chispa_timeouts_total counter")
	fmt.Fprintf(w, "chispa_timeouts_total %d\n", m.Timeouts.Load())
	fmt.Fprintln(w, "# HELP chispa_capa_latencia_segundos Latencia por capa.")
	fmt.Fprintln(w, "# TYPE chispa_capa_latencia_segundos histogram")
	for _, k := range claves(&m.mu, m.capas) {
		m.mu.Lock()
		h := m.capas[k]
		m.mu.Unlock()
		var acc uint64
		for i, b := range buckets {
			acc += h.n[i].Load()
			fmt.Fprintf(w, "chispa_capa_latencia_segundos_bucket{capa=%q,le=\"%g\"} %d\n", k, b, acc)
		}
		acc += h.n[len(buckets)].Load()
		fmt.Fprintf(w, "chispa_capa_latencia_segundos_bucket{capa=%q,le=\"+Inf\"} %d\n", k, acc)
		fmt.Fprintf(w, "chispa_capa_latencia_segundos_sum{capa=%q} %g\n", k, float64(h.sum.Load())/1e9)
		fmt.Fprintf(w, "chispa_capa_latencia_segundos_count{capa=%q} %d\n", k, acc)
	}
}
