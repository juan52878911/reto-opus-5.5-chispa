package decide

import (
	"fmt"
	"io"
	"sort"
	"strings"
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
	MultiL2SinCalib     atomic.Uint64 // preguntas multi en las que L2 no opinó por no traer el .chispa multi_l2 de su esquema
	MultiCalibAusente   atomic.Uint64 // preguntas multi cuya CALIB trae claves con esquema y ninguna casa (cae a la aproximación de noul)
	torreLatencia       histo         // duración de cada cálculo de torre

	// Texto largo: peticiones cuyo texto superó el truncado de la capa (max_len de L2, max_tokens de L1) y ventanas decididas (1 por
	// petición con «cabeza» o «cabeza_cola»; hasta max_trozos con «trozos»).
	TextoLargoL1, TextoLargoL2 atomic.Uint64
	TrozosL1, TrozosL2         atomic.Uint64

	// Esquema nuevo: preguntas puntuadas por L2 con torres al vuelo.
	EsquemaNuevoPreguntas atomic.Uint64
	EsquemaNuevoDecididas atomic.Uint64 // las que L2 resolvió con su τ de esquema nuevo (el resto subió o escaló)
	tauEsquemaNuevo       *float64      // τ propio de L2 para esquemas nuevos, si la cascada lo tiene

	// Totales de los L0 retirados por recargas: la caché de esquemas se muestra acumulada, sin bajar.
	esqBaseHits, esqBaseMisses uint64

	recargas map[string]*atomic.Uint64 // chispa_recargas_total{resultado}, bajo mu

	clavesN      map[[2]string]*atomic.Uint64 // chispa_clave_peticiones_total{clave,resultado}, bajo mu
	AuthRechazos atomic.Uint64                // 401 de /v1/decide (clave ausente o incorrecta)

	cachesBytes map[string]func() int64 // chispa_cache_bytes{cache}, bajo mu

	l3Llamadas map[string]*atomic.Uint64 // chispa_l3_llamadas_total{resultado}, bajo mu
	l3Lat      histo                     // latencia de cada llamada al LLM de L3

	Timeouts atomic.Uint64 // peticiones cuyo contexto venció por plazo (p. ej. http.TimeoutHandler)
}

// FijaCacheBytes registra el gauge chispa_cache_bytes{cache=nombre}; registrar de nuevo el mismo nombre lo sustituye.
func (m *Metricas) FijaCacheBytes(nombre string, bytes func() int64) {
	m.mu.Lock()
	if m.cachesBytes == nil {
		m.cachesBytes = map[string]func() int64{}
	}
	m.cachesBytes[nombre] = bytes
	m.mu.Unlock()
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
	if m.EsquemaHits != nil {
		m.esqBaseHits += m.EsquemaHits()
		m.esqBaseMisses += m.EsquemaMisses()
	}
	m.EsquemaHits, m.EsquemaMisses = hits, misses
	m.mu.Unlock()
}

// FijaTauNuevo fija el gauge chispa_esquema_nuevo_tau (nil = sin gauge); lo llama el servidor al poner un modelo en servicio.
func (m *Metricas) FijaTauNuevo(tau *float64) {
	m.mu.Lock()
	m.tauEsquemaNuevo = tau
	m.mu.Unlock()
}

// Recarga cuenta un intento de recarga del modelo: resultado "ok" o "error".
func (m *Metricas) Recarga(resultado string) { contador(&m.mu, m.recargas, resultado).Add(1) }

func NuevasMetricas() *Metricas {
	return &Metricas{clavesN: map[[2]string]*atomic.Uint64{}, recargas: map[string]*atomic.Uint64{}, capas: map[string]*histo{}, errCapa: map[string]*atomic.Uint64{},
		decididas: map[string]*atomic.Uint64{}, codigos: map[int]*atomic.Uint64{}, l3Llamadas: map[string]*atomic.Uint64{}}
}

// l3Cuenta cuenta una llamada de L3 por resultado: ok, invalida (respuesta que no sirve), error, timeout o presupuesto (tope por
// petición agotado, sin llamar). nil-safe.
func (m *Metricas) l3Cuenta(resultado string) {
	if m != nil {
		contador(&m.mu, m.l3Llamadas, resultado).Add(1)
	}
}

func (m *Metricas) l3Latencia(d time.Duration) {
	if m != nil {
		m.l3Lat.observa(d)
	}
}

// Clave cuenta una petición autenticada con la clave id: resultado "ok" o "limitada" (429).
func (m *Metricas) Clave(id, resultado string) {
	contador(&m.mu, m.clavesN, [2]string{id, resultado}).Add(1)
}

// AuthRechazo cuenta un 401 de /v1/decide.
func (m *Metricas) AuthRechazo() { m.AuthRechazos.Add(1) }

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
	defer m.escribeCachesBytes(w)
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
	fmt.Fprintln(w, "# HELP chispa_auth_rechazos_total Peticiones a /v1/decide rechazadas con 401 (clave ausente o incorrecta).")
	fmt.Fprintln(w, "# TYPE chispa_auth_rechazos_total counter")
	fmt.Fprintf(w, "chispa_auth_rechazos_total %d\n", m.AuthRechazos.Load())
	fmt.Fprintln(w, "# HELP chispa_clave_peticiones_total Peticiones autenticadas por id de clave y resultado (ok, limitada).")
	fmt.Fprintln(w, "# TYPE chispa_clave_peticiones_total counter")
	m.mu.Lock()
	ks := make([][2]string, 0, len(m.clavesN))
	for k := range m.clavesN {
		ks = append(ks, k)
	}
	sort.Slice(ks, func(i, j int) bool { return ks[i][0] < ks[j][0] || ks[i][0] == ks[j][0] && ks[i][1] < ks[j][1] })
	for _, k := range ks {
		fmt.Fprintf(w, "chispa_clave_peticiones_total{clave=\"%s\",resultado=\"%s\"} %d\n", escapaEtiqueta(k[0]), escapaEtiqueta(k[1]), m.clavesN[k].Load())
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
	baseH, baseM := m.esqBaseHits, m.esqBaseMisses
	m.mu.Unlock()
	if hits != nil {
		fmt.Fprintf(w, "chispa_cache_esquemas_total{resultado=\"acierto\"} %d\n", baseH+hits())
		fmt.Fprintf(w, "chispa_cache_esquemas_total{resultado=\"fallo\"} %d\n", baseM+misses())
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
	fmt.Fprintln(w, "# HELP chispa_multi_l2_sin_calib_total Preguntas multi en las que L2 no opinó por falta de CALIB multi_l2 del esquema.")
	fmt.Fprintln(w, "# TYPE chispa_multi_l2_sin_calib_total counter")
	fmt.Fprintf(w, "chispa_multi_l2_sin_calib_total %d\n", m.MultiL2SinCalib.Load())
	fmt.Fprintln(w, "# HELP chispa_multi_calib_ausente_total Preguntas multi cuya CALIB trae claves multi@<hash> y ninguna casa con la pregunta.")
	fmt.Fprintln(w, "# TYPE chispa_multi_calib_ausente_total counter")
	fmt.Fprintf(w, "chispa_multi_calib_ausente_total %d\n", m.MultiCalibAusente.Load()+multiCalibAusenteL1.Load())
	fmt.Fprintln(w, "# HELP chispa_torres_presupuesto_agotado_total Preguntas en las que L2 no opinó por agotar el tope de torres nuevas de la petición.")
	fmt.Fprintln(w, "# TYPE chispa_torres_presupuesto_agotado_total counter")
	fmt.Fprintf(w, "chispa_torres_presupuesto_agotado_total %d\n", m.PresupuestoAgotado.Load())
	fmt.Fprintln(w, "# HELP chispa_torre_latencia_segundos Latencia de cada cálculo de torre al vuelo.")
	fmt.Fprintln(w, "# TYPE chispa_torre_latencia_segundos histogram")
	m.torreLatencia.escribe(w, "chispa_torre_latencia_segundos")
	fmt.Fprintln(w, "# HELP chispa_texto_largo_total Peticiones cuyo texto superó el truncado de la capa (max_len de L2, max_tokens de L1).")
	fmt.Fprintln(w, "# TYPE chispa_texto_largo_total counter")
	fmt.Fprintf(w, "chispa_texto_largo_total{capa=\"L1\"} %d\nchispa_texto_largo_total{capa=\"L2\"} %d\n", m.TextoLargoL1.Load(), m.TextoLargoL2.Load())
	fmt.Fprintln(w, "# HELP chispa_texto_largo_trozos_total Ventanas decididas en textos largos (cabeza y cabeza_cola, 1 por petición; trozos, hasta max_trozos).")
	fmt.Fprintln(w, "# TYPE chispa_texto_largo_trozos_total counter")
	fmt.Fprintf(w, "chispa_texto_largo_trozos_total{capa=\"L1\"} %d\nchispa_texto_largo_trozos_total{capa=\"L2\"} %d\n", m.TrozosL1.Load(), m.TrozosL2.Load())
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
	fmt.Fprintln(w, "# HELP chispa_l3_llamadas_total Llamadas de L3 al LLM por resultado (ok, invalida, error, timeout, presupuesto). Sin L3 configurada, todo a 0.")
	fmt.Fprintln(w, "# TYPE chispa_l3_llamadas_total counter")
	for _, r := range []string{"ok", "invalida", "error", "timeout", "presupuesto"} {
		fmt.Fprintf(w, "chispa_l3_llamadas_total{resultado=%q} %d\n", r, contador(&m.mu, m.l3Llamadas, r).Load())
	}
	fmt.Fprintln(w, "# HELP chispa_l3_latencia_segundos Latencia de cada llamada de L3 al LLM.")
	fmt.Fprintln(w, "# TYPE chispa_l3_latencia_segundos histogram")
	m.l3Lat.escribe(w, "chispa_l3_latencia_segundos")
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

// escapaEtiqueta escapa un valor de etiqueta Prometheus: solo se admiten \\, \" y \n.
var escapaEtiqueta = strings.NewReplacer(`\`, `\\`, `"`, `\"`, "\n", `\n`).Replace

// escribeCachesBytes emite chispa_cache_bytes{cache}: las cachés registradas (l1, torres) y la de nonces del modelo en servicio.
func (m *Metricas) escribeCachesBytes(w io.Writer) {
	m.mu.Lock()
	vals := map[string]int64{}
	for n, f := range m.cachesBytes {
		vals[n] = f()
	}
	m.mu.Unlock()
	if c := noncesActual.Load(); c != nil {
		vals["nonces"] = c.Bytes()
	}
	fmt.Fprintln(w, "# HELP chispa_cache_bytes Bytes que ocupan las entradas de cada caché acotada por bytes (l1, nonces, torres).")
	fmt.Fprintln(w, "# TYPE chispa_cache_bytes gauge")
	for _, n := range []string{"l1", "nonces", "torres"} {
		if v, ok := vals[n]; ok {
			fmt.Fprintf(w, "chispa_cache_bytes{cache=%q} %d\n", n, v)
		}
	}
}

// ObservaTextoLargo cuenta un texto que superó el truncado de la capa («L1» o «L2») y las ventanas que costó decidirlo.
// Seguro con m nil.
func (m *Metricas) ObservaTextoLargo(capa string, ventanas int) {
	if m == nil {
		return
	}
	if capa == "L1" {
		m.TextoLargoL1.Add(1)
		m.TrozosL1.Add(uint64(ventanas))
		return
	}
	m.TextoLargoL2.Add(1)
	m.TrozosL2.Add(uint64(ventanas))
}
