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
}

func NuevasMetricas() *Metricas {
	return &Metricas{capas: map[string]*histo{}, errCapa: map[string]*atomic.Uint64{},
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
	s := d.Seconds()
	i := 0
	for i < len(buckets) && s > buckets[i] {
		i++
	}
	h.n[i].Add(1)
	h.sum.Add(uint64(d.Nanoseconds()))
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
	if m.EsquemaHits != nil {
		fmt.Fprintf(w, "chispa_cache_esquemas_total{resultado=\"acierto\"} %d\n", m.EsquemaHits())
		fmt.Fprintf(w, "chispa_cache_esquemas_total{resultado=\"fallo\"} %d\n", m.EsquemaMisses())
	}
	fmt.Fprintln(w, "# HELP chispa_cache_nonce_aciertos_total Respuestas servidas desde la caché de nonces.")
	fmt.Fprintln(w, "# TYPE chispa_cache_nonce_aciertos_total counter")
	fmt.Fprintf(w, "chispa_cache_nonce_aciertos_total %d\n", m.NonceHits.Load())
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
