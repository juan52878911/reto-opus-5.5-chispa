// chispa-server sirve POST /v1/decide, /healthz y /metrics (contrato: server/api/openapi.yaml).
package main

import (
	"bufio"
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
	maxEnCurso := flag.Int("max-en-curso", 64, "tope de peticiones a /v1/decide en curso a la vez (0 = sin tope); al llenarse responde 503 overloaded con Retry-After")
	apagado := flag.Duration("apagado", 25*time.Second, "plazo para terminar las peticiones en vuelo tras SIGTERM/SIGINT")
	abierto := flag.Bool("abierto", false, "permite escuchar fuera de loopback sin api_keys (también vale api_keys_abierto en la config)")
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
	srv0.ConRecarga(armar(met), inicial.AdminToken)
	apagando := &atomic.Bool{}
	handler := conLimites(montarHandler(srv0, inicial.AdminToken, *timeout, met), *maxEnCurso, apagando)
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
	log.Printf("apagando: dejo de aceptar y espero las peticiones en vuelo hasta %s", *apagado)
	sctx, cancel := context.WithTimeout(context.Background(), *apagado)
	defer cancel()
	code := 0
	if err := srv.Shutdown(sctx); err != nil {
		log.Printf("apagado: plazo agotado con peticiones en vuelo (%v): se cortan", err)
		srv.Close()
		code = 1
	}
	cierres.cerrarTodo()
	log.Print("apagado")
	os.Exit(code)
}

// cierres sigue los Cerrar de los modelos armados (el de servicio y los pendientes) para liberarlos al apagar: el servidor solo
// cierra los retirados por una recarga. Cada Cerrar corre una sola vez aunque lo llamen el servidor y el apagado.
type cierres struct {
	mu   sync.Mutex
	todo []func() error
}

func (c *cierres) registrar(a *decide.Armado) {
	if a.Cerrar == nil {
		return
	}
	orig := a.Cerrar
	var once sync.Once
	var err error
	a.Cerrar = func() error { once.Do(func() { err = orig() }); return err }
	c.mu.Lock()
	c.todo = append(c.todo, a.Cerrar)
	c.mu.Unlock()
}

func (c *cierres) cerrarTodo() {
	c.mu.Lock()
	defer c.mu.Unlock()
	for _, f := range c.todo {
		if err := f(); err != nil {
			log.Printf("apagado: cerrar modelo: %v", err)
		}
	}
}

// nuevoHTTPServer fija los plazos del servidor. WriteTimeout = timeout+5 s (el -timeout lo corta antes con su 503 tipado).
func nuevoHTTPServer(addr string, h http.Handler, timeout time.Duration) *http.Server {
	srv := &http.Server{Addr: addr, Handler: h, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second,
		IdleTimeout: 60 * time.Second, MaxHeaderBytes: 64 << 10}
	if timeout > 0 {
		srv.WriteTimeout = timeout + 5*time.Second
	}
	return srv
}

// conLimites aplica el semáforo de /v1/decide (503 overloaded con Retry-After, sin leer el cuerpo), baja /healthz a 503 al apagar
// y quita el plazo de escritura a la recarga admin, que puede tardar más.
func conLimites(h http.Handler, maxEnCurso int, apagando *atomic.Bool) http.Handler {
	var sem chan struct{}
	if maxEnCurso > 0 {
		sem = make(chan struct{}, maxEnCurso)
	}
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
			rc := http.NewResponseController(w)
			rc.SetWriteDeadline(time.Time{})
			rc.SetReadDeadline(time.Time{})
		case "/v1/decide":
			if sem != nil {
				select {
				case sem <- struct{}{}:
					defer func() { <-sem }()
				default:
					w.Header().Set("Content-Type", "application/json")
					w.Header().Set("Retry-After", "1")
					w.WriteHeader(http.StatusServiceUnavailable)
					io.WriteString(w, `{"error":{"code":"overloaded","message":"servidor saturado: demasiadas peticiones en curso"}}`+"\n")
					return
				}
			}
		}
		h.ServeHTTP(w, r)
	})
}

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
	casc, err := decide.NuevaCascadaConTauNuevo(cfg.Capas, []decide.Decisor{l0, capaL1, capaL2, decide.NuevoL3()}, met, cfg.TauL2EsquemaNuevo)
	if err != nil {
		if cerrar != nil {
			cerrar()
		}
		return nil, err
	}
	return &decide.Armado{Cascada: casc, CacheRespuestas: cfg.CacheRespuestas, Limites: cfg.Limites, APIKeys: cfg.APIKeys, APIKeysAbierto: cfg.APIKeysAbierto, AdminToken: cfg.AdminToken, L0: l0, Cerrar: cerrar}, nil
}

// montarHandler envuelve el mux del servidor en el -timeout (503 contado en las métricas), salvo /v1/admin/recargar: una recarga
// puede tardar más (L1 grande + ORT en disco lento) y cortarla con 503 invita al operador a reintentar y recargar dos veces.
func montarHandler(srv *decide.Servidor, adminToken string, timeout time.Duration, met *decide.Metricas) http.Handler {
	handler := srv.Handler()
	if timeout <= 0 {
		return handler
	}
	con := decide.ConTimeoutMet(handler, timeout, met)
	if adminToken == "" {
		return con
	}
	mux := http.NewServeMux()
	mux.Handle("/v1/admin/recargar", handler)
	mux.Handle("/", con)
	return mux
}

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
