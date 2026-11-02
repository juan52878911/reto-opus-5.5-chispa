package main

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/juan52878911/chispa/server/decide"
)

type lento struct{}

func (lento) Nombre() string { return "L0" }
func (lento) Decidir(context.Context, decide.Pregunta) (decide.Respuesta, error) {
	return decide.Respuesta{}, nil
}

// R4-8: una recarga más lenta que -timeout no responde 503.
func TestAdminFueraDelTimeout(t *testing.T) {
	met := decide.NuevasMetricas()
	armar := func() (*decide.Armado, error) {
		time.Sleep(80 * time.Millisecond)
		c, err := decide.NuevaCascada([]decide.Capa{{Nombre: "L0", Tau: 0.5}}, []decide.Decisor{lento{}}, met)
		return &decide.Armado{Cascada: c}, err
	}
	a, _ := armar()
	srv := decide.NuevoServidorDe(a, met).ConRecarga(armar, "tok")
	h := montarHandler(srv, true, 20*time.Millisecond, met)
	r := httptest.NewRequest(http.MethodPost, "/v1/admin/recargar", nil)
	r.Header.Set("Authorization", "Bearer tok")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != 200 {
		t.Fatalf("recarga lenta: %d %s", w.Code, w.Body)
	}
	if srv.Generacion() != 2 {
		t.Fatalf("generación %d", srv.Generacion())
	}
}

func TestImprimirHashClave(t *testing.T) {
	var out strings.Builder
	if err := imprimirHashClave(strings.NewReader("abc\n"), &out); err != nil {
		t.Fatal(err)
	}
	// sha256("abc"), vector estándar.
	if want := "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad\n"; out.String() != want {
		t.Fatalf("%q", out.String())
	}
	if err := imprimirHashClave(strings.NewReader("\n"), &out); err == nil {
		t.Fatal("clave vacía debía fallar")
	}
}

func TestExigirClaves(t *testing.T) {
	casos := []struct {
		addr      string
		claves    int
		permitido bool
		ok        bool
	}{
		{"127.0.0.1:8090", 0, false, true}, {"[::1]:8090", 0, false, true}, {"localhost:80", 0, false, true},
		{"0.0.0.0:8090", 0, false, false}, {":8090", 0, false, false}, {"10.0.0.5:80", 0, false, false},
		{"0.0.0.0:8090", 1, false, true}, {"0.0.0.0:8090", 0, true, true},
	}
	for _, c := range casos {
		if err := exigirClaves(c.addr, c.claves, c.permitido); (err == nil) != c.ok {
			t.Errorf("%+v: err=%v", c, err)
		}
	}
}

func TestConLimitesApaga(t *testing.T) {
	var apagando atomic.Bool
	srv := httptest.NewServer(conLimites(http.NotFoundHandler(), &apagando))
	defer srv.Close()
	apagando.Store(true)
	resp, _ := http.Get(srv.URL + "/healthz")
	resp.Body.Close()
	if resp.StatusCode != 503 {
		t.Fatalf("healthz apagando: %d", resp.StatusCode)
	}
}

func TestLimitarConexiones(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ll := limitarConexiones(ln, 2)
	defer ll.Close()
	var cs []net.Conn
	for i := 0; i < 3; i++ {
		c, err := net.Dial("tcp", ln.Addr().String())
		if err != nil {
			t.Fatal(err)
		}
		defer c.Close()
		cs = append(cs, c)
	}
	acep := make(chan net.Conn, 3)
	go func() {
		for {
			c, err := ll.Accept()
			if err != nil {
				return
			}
			acep <- c
		}
	}()
	a, b := <-acep, <-acep
	select {
	case <-acep:
		t.Fatal("aceptó una tercera conexión sobre el tope")
	case <-time.After(150 * time.Millisecond):
	}
	a.Close()
	select {
	case c := <-acep:
		c.Close()
	case <-time.After(2 * time.Second):
		t.Fatal("no aceptó al liberarse un hueco")
	}
	b.Close()
}

func TestHTTPServerPlazos(t *testing.T) {
	s := nuevoHTTPServer(":0", http.NewServeMux(), 30*time.Second)
	if s.ReadTimeout == 0 || s.IdleTimeout == 0 || s.ReadHeaderTimeout == 0 || s.WriteTimeout != 35*time.Second || s.MaxHeaderBytes != 64<<10 {
		t.Fatalf("%+v", s)
	}
}

// Conexión ociosa: el IdleTimeout la cierra y libera el hueco.
func TestIdleCierraConexion(t *testing.T) {
	srv := httptest.NewUnstartedServer(http.NotFoundHandler())
	srv.Config = nuevoHTTPServer("", srv.Config.Handler, 0)
	srv.Config.IdleTimeout = 100 * time.Millisecond
	srv.Start()
	defer srv.Close()
	c, err := net.Dial("tcp", srv.Listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	io.WriteString(c, "GET /healthz HTTP/1.1\r\nHost: x\r\n\r\n")
	c.SetReadDeadline(time.Now().Add(2 * time.Second))
	buf := make([]byte, 4096)
	c.Read(buf)
	if _, err := c.Read(buf); err == nil || strings.Contains(err.Error(), "timeout") {
		t.Fatalf("la conexión ociosa debía cerrarla el servidor: %v", err)
	}
}

// R7-4: un cuerpo de 1 MB con 349000 opciones vacías se rechaza sin reservar ~95 MB.
func TestCuerpoMuchasOpcionesAcotado(t *testing.T) {
	met := decide.NuevasMetricas()
	c, _ := decide.NuevaCascada([]decide.Capa{{Nombre: "L0", Tau: 0.5}}, []decide.Decisor{lento{}}, met)
	h := decide.NuevoServidorDe(&decide.Armado{Cascada: c}, met).Handler()
	body := `{"questions":[{"id":"a","question":"q","kind":"choice","options":[` + strings.Repeat("{},", 349000) + `{}]}]}`
	var antes, despues runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&antes)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "/v1/decide", strings.NewReader(body)))
	runtime.ReadMemStats(&despues)
	if w.Code != 400 && w.Code != 413 {
		t.Fatalf("código %d %s", w.Code, w.Body)
	}
	if d := despues.TotalAlloc - antes.TotalAlloc; d > 20<<20 {
		t.Fatalf("reservó %d MB", d>>20)
	}
}

// Apagado: sin plazo agotado y con cierres idempotentes.
func TestCierresUnaVez(t *testing.T) {
	n := 0
	a := &decide.Armado{Cerrar: func() error { n++; return nil }}
	c := &cierres{}
	c.registrar(a)
	a.Cerrar()
	c.cerrarTodo()
	if n != 1 {
		t.Fatalf("Cerrar corrió %d veces", n)
	}
}

// Proceso hijo: el test se reejecuta a sí mismo como chispa-server con los argumentos de CHISPA_HIJO.
func TestHijoServidor(t *testing.T) {
	a := os.Getenv("CHISPA_HIJO")
	if a == "" {
		t.Skip("solo como proceso hijo")
	}
	os.Args = append([]string{"chispa-server"}, strings.Fields(a)...)
	main()
}

// bufLog es un búfer seguro entre la goroutine que copia la salida del hijo y el test.
type bufLog struct {
	mu sync.Mutex
	b  bytes.Buffer
}

func (l *bufLog) Write(p []byte) (int, error) { l.mu.Lock(); defer l.mu.Unlock(); return l.b.Write(p) }
func (l *bufLog) String() string              { l.mu.Lock(); defer l.mu.Unlock(); return l.b.String() }

func hijo(t *testing.T, args string) (*exec.Cmd, *bufLog) {
	t.Helper()
	cmd := exec.Command(os.Args[0], "-test.run=^TestHijoServidor$")
	cmd.Env = append(os.Environ(), "CHISPA_HIJO="+args)
	log := &bufLog{}
	cmd.Stderr, cmd.Stdout = log, log
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { cmd.Process.Kill(); cmd.Wait() })
	return cmd, log
}

// R7-9 y R7-14: sin api_keys fuera de loopback se niega a arrancar, con FATAL:.
func TestNoArrancaAbiertoFueraDeLoopback(t *testing.T) {
	cmd, log := hijo(t, "-addr 0.0.0.0:0")
	if err := cmd.Wait(); err == nil {
		t.Fatalf("debía salir con error:\n%s", log)
	}
	if !strings.Contains(log.String(), "FATAL: ") || !strings.Contains(log.String(), "-abierto") {
		t.Fatalf("sin FATAL:\n%s", log)
	}
}

func TestArrancaAbiertoConFlag(t *testing.T) {
	cmd, log := hijo(t, "-addr 0.0.0.0:18791 -abierto")
	esperarLog(t, log, "chispa-server en")
	cmd.Process.Signal(syscall.SIGTERM)
	cmd.Wait()
}

func esperarLog(t *testing.T, log *bufLog, s string) {
	t.Helper()
	for i := 0; i < 200; i++ {
		if strings.Contains(log.String(), s) {
			return
		}
		time.Sleep(25 * time.Millisecond)
	}
	t.Fatalf("no apareció %q:\n%s", s, log)
}

// R7-6: SIGTERM con una petición a medias: se termina de contestar y queda registrado.
func TestSigtermTerminaPeticionEnVuelo(t *testing.T) {
	cmd, log := hijo(t, "-addr 127.0.0.1:18792 -apagado 5s")
	esperarLog(t, log, "chispa-server en")
	c, err := net.Dial("tcp", "127.0.0.1:18792")
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	body := `{"questions":[]}`
	io.WriteString(c, "POST /v1/decide HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\nContent-Length: "+strconv.Itoa(len(body))+"\r\n\r\n"+body[:5])
	time.Sleep(200 * time.Millisecond)
	cmd.Process.Signal(syscall.SIGTERM)
	esperarLog(t, log, "apagando")
	io.WriteString(c, body[5:])
	c.SetReadDeadline(time.Now().Add(3 * time.Second))
	resp, err := http.ReadResponse(bufio.NewReader(c), nil)
	if err != nil {
		t.Fatalf("la petición en vuelo se cortó sin respuesta: %v", err)
	}
	resp.Body.Close()
	if err := cmd.Wait(); err != nil {
		t.Fatalf("salida: %v\n%s", err, log)
	}
	if !strings.Contains(log.String(), "apagado\n") {
		t.Fatalf("sin «apagado»:\n%s", log)
	}
}

// Con el tope lleno de conexiones ociosas, una nueva expulsa a la ociosa más antigua; las activas no se cortan.
func TestLimitarConexionesExpulsaOciosas(t *testing.T) {
	const n = 5
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	ll := limitarConexiones(ln, n)
	defer ll.Close()
	var cli, srv []net.Conn
	for i := 0; i < n; i++ {
		c, err := net.Dial("tcp", ln.Addr().String())
		if err != nil {
			t.Fatal(err)
		}
		defer c.Close()
		s, err := ll.Accept()
		if err != nil {
			t.Fatal(err)
		}
		cli, srv = append(cli, c), append(srv, s)
	}
	// srv[0] queda activa (petición en curso); srv[1..] ociosas, la 1 la más antigua.
	for _, s := range srv[1:] {
		s.(*conLimitada).ociosa(true)
	}
	nueva, err := net.Dial("tcp", ln.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer nueva.Close()
	acep := make(chan net.Conn, 1)
	go func() {
		if c, err := ll.Accept(); err == nil {
			acep <- c
		}
	}()
	select {
	case c := <-acep:
		defer c.Close()
	case <-time.After(2 * time.Second):
		t.Fatal("no expulsó una ociosa para aceptar la nueva")
	}
	cli[1].SetReadDeadline(time.Now().Add(time.Second))
	if _, err := cli[1].Read(make([]byte, 1)); err == nil || errors.Is(err, os.ErrDeadlineExceeded) {
		t.Fatalf("la ociosa más antigua debía quedar cerrada: %v", err)
	}
	cli[0].SetReadDeadline(time.Now().Add(100 * time.Millisecond))
	if _, err := cli[0].Read(make([]byte, 1)); !errors.Is(err, os.ErrDeadlineExceeded) {
		t.Fatalf("la activa no debía cortarse: %v", err)
	}
}

// Si todas están activas no se expulsa a nadie: la nueva espera.
func TestLimitarConexionesNoCortaActivas(t *testing.T) {
	ln, _ := net.Listen("tcp", "127.0.0.1:0")
	ll := limitarConexiones(ln, 1)
	defer ll.Close()
	c, _ := net.Dial("tcp", ln.Addr().String())
	defer c.Close()
	s, _ := ll.Accept()
	defer s.Close()
	got := make(chan struct{})
	go func() {
		if c, err := ll.Accept(); err == nil {
			c.Close()
			close(got)
		}
	}()
	select {
	case <-got:
		t.Fatal("aceptó sobre el tope con la única conexión activa")
	case <-time.After(150 * time.Millisecond):
	}
	s.(*conLimitada).ociosa(true) // pasa a ociosa: se expulsa y la nueva entra
	n, _ := net.Dial("tcp", ln.Addr().String())
	defer n.Close()
	select {
	case <-got:
	case <-time.After(2 * time.Second):
		t.Fatal("no entró la nueva tras quedar ociosa la anterior")
	}
}

func TestResumenCapasAvisaSinTorre(t *testing.T) {
	sin := resumenCapas(0, decide.Capacidades{Capas: map[string]bool{"L0": false, "L1": false, "L2": true, "L3": false}})
	for _, w := range []string{"capas efectivas: L2; sin modelo: L0, L1, L3", "torre al vuelo (esquemas nuevos en L2): false", "AVISO: sin torre al vuelo", "sin_opinion"} {
		if !strings.Contains(sin, w) {
			t.Fatalf("falta %q en %q", w, sin)
		}
	}
	con := resumenCapas(2, decide.Capacidades{Capas: map[string]bool{"L0": true, "L1": true, "L2": true, "L3": false}, TorreAlVuelo: true, TextoTorre: "v2_sin_id"})
	if !strings.Contains(con, "L0(2 modelos), L1, L2") || strings.Contains(con, "AVISO") || !strings.Contains(con, "texto_torre: v2_sin_id") {
		t.Fatal(con)
	}
	if !strings.Contains(sin, "texto_torre: -") {
		t.Fatal(sin)
	}
}
