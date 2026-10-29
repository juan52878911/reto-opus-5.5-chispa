// chispa-server sirve POST /v1/decide, /healthz y /metrics (contrato: server/api/openapi.yaml).
package main

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"chispa/format/chispa3"
	"chispa/runtime/tok"
	"github.com/juan52878911/chispa/server/decide"
)

func main() {
	addr := flag.String("addr", "127.0.0.1:8090", "dirección de escucha")
	cfgPath := flag.String("config", "", "JSON de configuración (capas, τ, modelos, cachés)")
	modelo := flag.String("modelo", "", ".chispa v3 (o v2 envuelto) del que armar L0, L1 y L2 según sus secciones")
	rutaTok := flag.String("tok", "", ".chispa-tok de e5 (runtime/tok/exportar.py); sin él, L2 queda en stub")
	timeout := flag.Duration("timeout", 30*time.Second, "tope de tiempo por petición (cancela su ctx y responde 503 con Retry-After y código timeout); 0 = sin tope")
	ortLib := flag.String("ort-lib", "", "libonnxruntime.so para L2 y la torre (precede a CHISPA_ORT_LIB y a -ldflags -X …decide.RutaORT; vacío = la del sistema)")
	maxConex := flag.Int("max-conexiones", 1024, "tope de conexiones TCP abiertas a la vez (0 = sin tope); evita agotar los descriptores con conexiones ociosas")
	maxEnCurso := flag.Int("max-en-curso", 64, "tope de peticiones a /v1/decide en curso a la vez (0 = sin tope); al llenarse responde 429 rate_limited con Retry-After (contado en /metrics)")
	preDrenaje := flag.Duration("pre-drenaje", 0, "al recibir SIGTERM/SIGINT, /healthz responde 503 shutting_down este tiempo con los listeners aún abiertos, para que el balanceador saque el nodo, y luego empieza el apagado (0 = sin espera)")
	apagado := flag.Duration("apagado", 25*time.Second, "plazo para terminar las peticiones en vuelo tras SIGTERM/SIGINT")
	abierto := flag.Bool("abierto", false, "permite escuchar fuera de loopback sin api_keys (también vale api_keys_abierto en la config)")
	adminAddr := flag.String("admin-addr", "", "dirección de escucha aparte para POST /v1/admin/recargar (p. ej. 127.0.0.1:8091); la pública deja de servirla (404). Vacío = comparte -addr")
	plazoCuerpo := flag.Duration("plazo-cuerpo", 0, "plazo para recibir el cuerpo entero de /v1/decide (0 = 10 s; negativo = sin plazo)")
	metricasProt := flag.Bool("metricas-protegidas", false, "/metrics exige Authorization: Bearer con una api_key válida (o el admin_token en claro)")
	hashClave := flag.Bool("hash-clave", false, "lee una clave de la entrada estándar, imprime su SHA-256 (hash_sha256 de api_keys) y sale")
	flag.Parse()
	if *hashClave {
		if err := imprimirHashClave(os.Stdin, os.Stdout); err != nil {
			log.Fatalf("FATAL: -hash-clave: %v", err)
		}
		return
	}
	rutaORT, origenORT = fijarRutaORT(*ortLib)
	log.Printf("ORT: ruta %q (%s)", rutaORT, origenORT)
	cierres := &cierres{}
	armar := func(met *decide.Metricas) decide.Armador {
		return func() (*decide.Armado, error) {
			a, err := armarModelo(met, *cfgPath, *modelo, *rutaTok)
			if err == nil {
				cierres.registrar(a)
			}
			return a, err
		}
	}
	met := decide.NuevasMetricas()
	// SIGHUP se registra antes de armar (tarda segundos): sin Notify, Go lo trataría como salida. Un HUP durante el arranque
	// queda encolado y se atiende cuando el servidor está listo (el modelo recién armado ya es el de la config actual,
	// así que ese primer HUP se descarta en lugar de armar dos veces).
	sighup := make(chan os.Signal, 1)
	signal.Notify(sighup, syscall.SIGHUP)
	// Arranque: cualquier fallo es fatal. Recargas: el servidor conserva el modelo anterior.
	inicial, err := armar(met)()
	if err != nil {
		log.Fatalf("FATAL: arranque: %v", err)
	}
	if err := exigirClaves(*addr, len(inicial.APIKeys), inicial.APIKeysAbierto || *abierto); err != nil {
		log.Fatalf("FATAL: %v", err)
	}
	srv0 := decide.NuevoServidorDe(inicial, met)
	srv0.ConRecargaDe(armar(met), inicial)
	srv0.ConMaxEnCurso(*maxEnCurso).ConPlazoCuerpo(*plazoCuerpo).ConMetricasProtegidas(*metricasProt)
	adminOn := inicial.AdminToken != "" || inicial.AdminTokenSHA256 != ""
	if *metricasProt && len(inicial.APIKeys) == 0 && (inicial.AdminTokenSHA256 != "" || !adminOn) {
		log.Print("AVISO: -metricas-protegidas sin api_keys (y sin admin_token en claro): /metrics responderá 401 siempre")
	}
	if adminOn && *adminAddr == "" && !esLoopback(*addr) {
		log.Printf("AVISO: /v1/admin/recargar comparte el puerto público %s; use -admin-addr 127.0.0.1:<puerto> para separarla", *addr)
	}
	apagando := &atomic.Bool{}
	handler := conLimites(montarHandler(srv0, adminOn, *timeout, met), apagando)
	handler = conMetricasAdmin(handler, met)
	var adminSrv *http.Server
	if adminOn && *adminAddr != "" {
		if !esLoopback(*adminAddr) {
			log.Printf("AVISO: -admin-addr %s no es loopback: la ruta de administración queda expuesta", *adminAddr)
		}
		aln, err := net.Listen("tcp", *adminAddr)
		if err != nil {
			log.Fatalf("FATAL: escuchar la administración en %s: %v", *adminAddr, err)
		}
		adminSrv = nuevoHTTPServer(*adminAddr, soloAdmin(handler), *timeout)
		go func() {
			if err := adminSrv.Serve(aln); err != nil && !errors.Is(err, http.ErrServerClosed) {
				log.Fatalf("FATAL: servir la administración en %s: %v", *adminAddr, err)
			}
		}()
		log.Printf("administración en %s", *adminAddr)
		handler = sinAdmin(handler)
	}
	go func() {
		select {
		case <-sighup: // llegó durante el arranque: el modelo recién armado ya lo refleja
		default:
		}
		for range sighup {
			log.Print("SIGHUP: recargando el modelo")
			srv0.Recargar() // ya registra el error y cuenta la métrica
		}
	}()
	srv := nuevoHTTPServer(*addr, handler, *timeout)
	ln, err := net.Listen("tcp", *addr)
	if err != nil {
		log.Fatalf("FATAL: escuchar en %s: %v", *addr, err)
	}
	ln = limitarConexiones(ln, *maxConex)
	ctx, parar := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer parar()
	errSrv := make(chan error, 1)
	go func() { errSrv <- srv.Serve(ln) }()
	log.Printf("chispa-server en %s: %d modelos en L0", *addr, inicial.L0.NumModelos())
	select {
	case err := <-errSrv:
		log.Fatalf("FATAL: servir en %s: %v", *addr, err)
	case <-ctx.Done():
	}
	parar()
	apagando.Store(true)
	if *preDrenaje > 0 {
		log.Printf("apagando (pre-drenaje): /healthz responde 503 shutting_down durante %s antes de cerrar los listeners", *preDrenaje)
		time.Sleep(*preDrenaje)
	}
	log.Printf("apagando: dejo de aceptar y espero las peticiones en vuelo hasta %s", *apagado)
	sctx, cancel := context.WithTimeout(context.Background(), *apagado)
	defer cancel()
	code := apagarTodo(sctx, srv, adminSrv)
	cierres.cerrarTodo()
	log.Print("apagado")
	os.Exit(code)
}

// apagarTodo apaga a la vez el listener público y el de administración con el mismo ctx; devuelve 1 si alguno agota el plazo
// (y lo corta), 0 si no.
func apagarTodo(ctx context.Context, srv, adminSrv *http.Server) int {
	var wg sync.WaitGroup
	var fallos atomic.Int32
	for _, c := range []struct {
		nombre string
		s      *http.Server
	}{{"público", srv}, {"administración", adminSrv}} {
		if c.s == nil {
			continue
		}
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := c.s.Shutdown(ctx); err != nil {
				log.Printf("apagado: %s: plazo agotado con peticiones en vuelo (%v): se cortan", c.nombre, err)
				c.s.Close()
				fallos.Add(1)
			}
		}()
	}
	wg.Wait()
	if fallos.Load() > 0 {
		return 1
	}
	return 0
}

// cierres sigue los Cerrar de los modelos armados (el de servicio y los pendientes) para liberarlos al apagar: el servidor solo
// cierra los retirados por una recarga. Cada Cerrar corre una sola vez aunque lo llamen el servidor y el apagado.
type cierres struct {
	mu   sync.Mutex
	todo map[*func() error]func() error
}

func (c *cierres) registrar(a *decide.Armado) {
	if a.Cerrar == nil {
		return
	}
	orig := a.Cerrar
	var once sync.Once
	var err error
	id := new(func() error)
	a.Cerrar = func() error {
		once.Do(func() {
			err = orig()
			// Ya cerrado: se suelta para que no retenga el modelo (el .chispa, L1, L2) hasta el apagado.
			c.mu.Lock()
			delete(c.todo, id)
			c.mu.Unlock()
		})
		return err
	}
	c.mu.Lock()
	if c.todo == nil {
		c.todo = map[*func() error]func() error{}
	}
	c.todo[id] = a.Cerrar
	c.mu.Unlock()
}

func (c *cierres) cerrarTodo() {
	c.mu.Lock()
	fs := make([]func() error, 0, len(c.todo))
	for _, f := range c.todo {
		fs = append(fs, f)
	}
	c.mu.Unlock() // cada f toma c.mu al terminar
	for _, f := range fs {
		if err := f(); err != nil {
			log.Printf("apagado: cerrar modelo: %v", err)
		}
	}
}

// nuevoHTTPServer fija los plazos del servidor. WriteTimeout = timeout+5 s (el -timeout lo corta antes con su 503 tipado).
func nuevoHTTPServer(addr string, h http.Handler, timeout time.Duration) *http.Server {
	srv := &http.Server{Addr: addr, Handler: h, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second,
		IdleTimeout: 10 * time.Second, MaxHeaderBytes: 64 << 10}
	if timeout > 0 {
		srv.WriteTimeout = timeout + 5*time.Second
	}
	return srv
}

// conLimites baja /healthz a 503 shutting_down al apagar y, en la recarga admin, amplía solo el plazo de escritura (la recarga
// puede tardar más). El de lectura no se toca, y si la petición trae cuerpo se responde con Connection: close: net/http vacía el
// cuerpo antes de escribir y un cliente que prometa Content-Length y no lo mande retendría la conexión hasta ReadTimeout.
func conLimites(h http.Handler, apagando *atomic.Bool) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/healthz":
			if apagando.Load() {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusServiceUnavailable)
				io.WriteString(w, `{"status":"shutting_down"}`+"\n")
				return
			}
		case "/v1/admin/recargar":
			http.NewResponseController(w).SetWriteDeadline(time.Now().Add(plazoEscrituraAdmin))
			if r.ContentLength != 0 {
				w.Header().Set("Connection", "close")
			}
		}
		h.ServeHTTP(w, r)
	})
}

// plazoEscrituraAdmin es lo que tiene la recarga admin para terminar y responder.
const plazoEscrituraAdmin = 10 * time.Minute

// limitarConexiones envuelve ln con un tope de conexiones abiertas (como netutil.LimitListener): Accept espera un hueco.
func limitarConexiones(ln net.Listener, n int) net.Listener {
	if n <= 0 {
		return ln
	}
	return &limitListener{Listener: ln, sem: make(chan struct{}, n), hecho: make(chan struct{})}
}

type limitListener struct {
	net.Listener
	sem   chan struct{}
	hecho chan struct{}
	once  sync.Once
}

func (l *limitListener) Accept() (net.Conn, error) {
	select {
	case l.sem <- struct{}{}:
	case <-l.hecho:
		return nil, net.ErrClosed
	}
	c, err := l.Listener.Accept()
	if err != nil {
		<-l.sem
		return nil, err
	}
	return &conLimitada{Conn: c, liberar: func() { <-l.sem }}, nil
}

func (l *limitListener) Close() error {
	err := l.Listener.Close()
	l.once.Do(func() { close(l.hecho) })
	return err
}

type conLimitada struct {
	net.Conn
	once    sync.Once
	liberar func()
}

func (c *conLimitada) Close() error {
	err := c.Conn.Close()
	c.once.Do(c.liberar)
	return err
}

// exigirClaves rechaza escuchar fuera de loopback sin api_keys salvo que se haya permitido abierto.
func exigirClaves(addr string, nClaves int, permitido bool) error {
	if nClaves > 0 || permitido || esLoopback(addr) {
		return nil
	}
	return fmt.Errorf("escuchar en %s sin api_keys deja /v1/decide abierto a la red: ponga api_keys en la config, escuche en loopback, "+
		"o pase -abierto (o api_keys_abierto: true) si es a propósito", addr)
}

func esLoopback(addr string) bool {
	host, _, err := net.SplitHostPort(addr)
	if err != nil {
		host = addr
	}
	if host == "localhost" {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

// armarModelo relee la config y el .chispa y arma una cascada completa con cachés propias. Lo usan el arranque y cada recarga
// (SIGHUP o POST /v1/admin/recargar); si algo falla devuelve el error sin tocar nada de lo que sirve.
// rutaORT y origenORT: la ruta de ORT resuelta al arrancar y de dónde salió (para los avisos).
var rutaORT, origenORT string

func armarModelo(met *decide.Metricas, cfgPath, modelo, rutaTok string) (*decide.Armado, error) {
	cfg := decide.ConfigPorDefecto()
	if cfgPath != "" {
		var err error
		if cfg, err = decide.CargarConfig(cfgPath); err != nil {
			return nil, err
		}
	}
	l0 := decide.NuevoL0(cfg.CacheEsquemas)
	if err := l0.Cargar(cfg.Modelos...); err != nil {
		return nil, err
	}
	capaL1, capaL2 := decide.NuevoL1(), decide.NuevoL2()
	var cerrar func() error
	if modelo != "" {
		f, err := chispa3.Abrir(modelo)
		if err != nil {
			return nil, err
		}
		cerrar = f.Close
		if f.Tiene(chispa3.TORR) || f.Tiene(chispa3.L2) {
			if err := comprobarORT(); err != nil {
				log.Printf("AVISO: ONNX Runtime no carga (ruta %q, %s): %v. L2 queda en stub y los esquemas nuevos escalan "+
					"(chispa_torres_calculadas_total seguirá en 0); use -ort-lib o CHISPA_ORT_LIB", rutaORT, origenORT, err)
			}
		}
		fallo := func(err error) (*decide.Armado, error) { f.Close(); return nil, err }
		var tk decide.Tokenizador
		if rutaTok != "" {
			t, err := tok.Abrir(rutaTok)
			if err != nil {
				return fallo(err)
			}
			tk = decide.NuevoTokenizadorE5(t)
		}
		mt, err := decide.ArmarDesde(f, l0, &cfg, cfgPath == "", tk)
		if err != nil {
			return fallo(err)
		}
		if f.Tiene(chispa3.TORR) && tk == nil {
			log.Print("el .chispa trae TORR pero falta -tok: sin torres al vuelo, L2 solo decide esquemas de ESQUEMAS")
		}
		for _, a := range mt.Avisos {
			log.Print(a)
		}
		capaL1, capaL2 = mt.L1, mt.L2
		if mt.Cerrar != nil {
			// Las sesiones ORT (L2 y torre) se cierran antes que el .chispa que las alimentó.
			cerrarSesiones := mt.Cerrar
			cerrar = func() error { return errors.Join(cerrarSesiones(), f.Close()) }
		}
	}
	if l1, ok := capaL1.(interface{ ConCacheBytes(int) *decide.L1 }); ok {
		l1.ConCacheBytes(cfg.CacheEsquemasMB)
	}
	casc, err := decide.NuevaCascadaConTauNuevo(cfg.Capas, []decide.Decisor{l0, capaL1, capaL2, decide.NuevoL3()}, met, cfg.TauL2EsquemaNuevo)
	if err != nil {
		if cerrar != nil {
			cerrar()
		}
		return nil, err
	}
	return &decide.Armado{Cascada: casc, CacheRespuestas: cfg.CacheRespuestas, BytesNonces: cfg.CacheRespuestasMB << 20, Limites: cfg.Limites, APIKeys: cfg.APIKeys, APIKeysAbierto: cfg.APIKeysAbierto, AdminToken: cfg.AdminToken, AdminTokenSHA256: cfg.AdminTokenSHA256, L0: l0, Cerrar: cerrar}, nil
}

// montarHandler envuelve el mux del servidor en el -timeout (503 contado en las métricas), salvo /v1/admin/recargar: una recarga
// puede tardar más (L1 grande + ORT en disco lento) y cortarla con 503 invita al operador a reintentar y recargar dos veces.
func montarHandler(srv *decide.Servidor, adminOn bool, timeout time.Duration, met *decide.Metricas) http.Handler {
	handler := srv.Handler()
	if timeout <= 0 {
		return handler
	}
	con := decide.ConTimeoutMet(handler, timeout, met)
	if !adminOn {
		return con
	}
	mux := http.NewServeMux()
	mux.Handle("/v1/admin/recargar", handler)
	mux.Handle("/", con)
	return mux
}

// soloAdmin deja pasar a h solo /v1/admin/recargar (el listener de administración); sinAdmin hace lo contrario en el público.
func soloAdmin(h http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/admin/recargar" {
			http.NotFound(w, r)
			return
		}
		h.ServeHTTP(w, r)
	})
}

func sinAdmin(h http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/admin/recargar" {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusNotFound)
			io.WriteString(w, `{"error":{"code":"not_found","message":"ruta /v1/admin/recargar no existe"}}`+"\n")
			return
		}
		h.ServeHTTP(w, r)
	})
}

// conMetricasAdmin añade chispa_admin_rechazos_total a la respuesta 200 de GET /metrics (metricas.go no lo emite).
func conMetricasAdmin(h http.Handler, met *decide.Metricas) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/metrics" || r.Method != http.MethodGet {
			h.ServeHTTP(w, r)
			return
		}
		rec := &bufResp{h: http.Header{}, code: http.StatusOK}
		h.ServeHTTP(rec, r)
		if rec.code == http.StatusOK {
			met.EscribeAdmin(&rec.buf)
		}
		for k, v := range rec.h {
			w.Header()[k] = v
		}
		w.Header().Del("Content-Length")
		w.WriteHeader(rec.code)
		w.Write(rec.buf.Bytes())
	})
}

type bufResp struct {
	h    http.Header
	buf  bytes.Buffer
	code int
}

func (b *bufResp) Header() http.Header         { return b.h }
func (b *bufResp) Write(p []byte) (int, error) { return b.buf.Write(p) }
func (b *bufResp) WriteHeader(c int)           { b.code = c }

// imprimirHashClave lee la clave (una línea, sin el salto) de r y escribe en w su SHA-256 en hex. Por la entrada estándar
// para que la clave no quede en el historial del shell ni en la lista de procesos.
func imprimirHashClave(r io.Reader, w io.Writer) error {
	linea, err := bufio.NewReader(r).ReadString('\n')
	if err != nil && err != io.EOF {
		return err
	}
	clave := strings.TrimRight(linea, "\r\n")
	if clave == "" {
		return fmt.Errorf("-hash-clave: la entrada estándar no trae ninguna clave")
	}
	_, err = fmt.Fprintln(w, decide.HashClave(clave))
	return err
}
