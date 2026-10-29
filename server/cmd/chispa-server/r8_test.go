package main

import (
	"bufio"
	"context"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"runtime"
	"strings"
	"sync/atomic"
	"syscall"
	"testing"
	"time"

	"github.com/juan52878911/chispa/server/decide"
)

// R8-H1: un POST a la ruta admin con Content-Length y sin cuerpo, sin token, recibe respuesta con cierre en vez de colgar la conexión.
func TestR8AdminSinCuerpoNoCuelga(t *testing.T) {
	met := decide.NuevasMetricas()
	c, _ := decide.NuevaCascada([]decide.Capa{{Nombre: "L0", Tau: 0.5}}, []decide.Decisor{lento{}}, met)
	srv := decide.NuevoServidorDe(&decide.Armado{Cascada: c}, met).ConRecarga(func() (*decide.Armado, error) { return nil, nil }, "tok")
	var apagando atomic.Bool
	ts := httptest.NewUnstartedServer(conLimites(montarHandler(srv, true, time.Second, met), &apagando))
	ts.Config = nuevoHTTPServer("", ts.Config.Handler, time.Second)
	ts.Config.ReadTimeout = 20 * time.Second
	ts.Start()
	defer ts.Close()
	cn, err := net.Dial("tcp", ts.Listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer cn.Close()
	io.WriteString(cn, "POST /v1/admin/recargar HTTP/1.1\r\nHost: x\r\nContent-Length: 1000\r\n\r\n")
	cn.SetReadDeadline(time.Now().Add(3 * time.Second))
	resp, err := http.ReadResponse(bufio.NewReader(cn), nil)
	if err != nil {
		t.Fatalf("sin respuesta con el cuerpo pendiente: %v", err)
	}
	resp.Body.Close()
	if !resp.Close {
		t.Fatal("debía responder con Connection: close")
	}
	if resp.StatusCode != 401 {
		t.Fatalf("código %d", resp.StatusCode)
	}
}

// R8-H8: un Cerrar ya ejecutado se suelta de cierres y deja de retener lo que captura.
func TestR8CierresSueltaElModeloCerrado(t *testing.T) {
	c := &cierres{}
	liberado := make(chan struct{})
	func() {
		modelo := new([1 << 20]byte)
		runtime.SetFinalizer(modelo, func(*[1 << 20]byte) { close(liberado) })
		a := &decide.Armado{Cerrar: func() error { _ = modelo[0]; return nil }}
		c.registrar(a)
		a.Cerrar()
	}()
	for i := 0; i < 20; i++ {
		runtime.GC()
		select {
		case <-liberado:
			return
		case <-time.After(50 * time.Millisecond):
		}
	}
	t.Fatal("el modelo cerrado sigue retenido por cierres")
}

// R8-H9: las conexiones keep-alive ociosas se cierran pronto para no ocupar -max-conexiones.
func TestR8IdleCorto(t *testing.T) {
	if d := nuevoHTTPServer(":0", http.NewServeMux(), 0).IdleTimeout; d > 15*time.Second {
		t.Fatalf("IdleTimeout %s", d)
	}
}

// R8-H10: el apagado es en paralelo: el público deja de aceptar aunque el admin tenga una conexión colgada.
func TestR8ApagadoEnParalelo(t *testing.T) {
	cuelga := make(chan struct{})
	defer close(cuelga)
	arr := func(h http.Handler) (*http.Server, string) {
		ln, _ := net.Listen("tcp", "127.0.0.1:0")
		s := &http.Server{Handler: h}
		go s.Serve(ln)
		return s, ln.Addr().String()
	}
	admin, aAddr := arr(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-cuelga }))
	pub, pAddr := arr(http.NotFoundHandler())
	go http.Get("http://" + aAddr + "/")
	time.Sleep(100 * time.Millisecond)
	ctx, cancel := context.WithTimeout(context.Background(), 1500*time.Millisecond)
	defer cancel()
	hecho := make(chan int, 1)
	go func() { hecho <- apagarTodo(ctx, pub, admin) }()
	time.Sleep(300 * time.Millisecond)
	if c, err := net.DialTimeout("tcp", pAddr, time.Second); err == nil {
		c.Close()
		t.Fatal("el público sigue aceptando mientras el admin espera")
	}
	if code := <-hecho; code != 1 {
		t.Fatalf("código %d, quería 1 por el admin colgado", code)
	}
}

// bloqueado avisa en dentro cuando una petición entra a decidir y espera a que se cierre suelta.
type bloqueado struct{ dentro, suelta chan struct{} }

func (bloqueado) Nombre() string { return "L0" }
func (b bloqueado) Decidir(context.Context, decide.Pregunta) (decide.Respuesta, error) {
	b.dentro <- struct{}{}
	<-b.suelta
	return decide.Respuesta{}, nil
}

// R8-H12: la saturación de /v1/decide (tope de ConMaxEnCurso) responde 429 con Retry-After y se cuenta en /metrics.
// El hueco lo ocupa una petición que ya está decidiendo: desde R8-H6 el semáforo se toma tras leer el cuerpo, así que un
// cuerpo lento ya no lo ocupa.
func TestR8SaturacionContada(t *testing.T) {
	met := decide.NuevasMetricas()
	bl := bloqueado{dentro: make(chan struct{}, 1), suelta: make(chan struct{})}
	c, _ := decide.NuevaCascada([]decide.Capa{{Nombre: "L0", Tau: 0.5}}, []decide.Decisor{bl}, met)
	var apagando atomic.Bool
	ds := decide.NuevoServidorDe(&decide.Armado{Cascada: c}, met).ConMaxEnCurso(1).ConPlazoCuerpo(2 * time.Second)
	ts := httptest.NewServer(conMetricasAdmin(conLimites(montarHandler(ds, false, 0, met), &apagando), met))
	defer ts.Close()
	cuerpo := `{"state":"hola","questions":[{"id":"q1","question":"¿Qué quiere?","kind":"choice","options":[{"id":"a"},{"id":"b"}]}]}`
	primera := make(chan error, 1)
	go func() {
		r, err := http.Post(ts.URL+"/v1/decide", "application/json", strings.NewReader(cuerpo))
		if err == nil {
			r.Body.Close()
		}
		primera <- err
	}()
	select {
	case <-bl.dentro:
	case <-time.After(5 * time.Second):
		t.Fatal("la primera petición no llegó a decidir")
	}
	resp, err := http.Post(ts.URL+"/v1/decide", "application/json", strings.NewReader(cuerpo))
	close(bl.suelta)
	if e := <-primera; e != nil {
		t.Fatal(e)
	}
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 429 || resp.Header.Get("Retry-After") == "" {
		t.Fatalf("saturado: %d retry=%q", resp.StatusCode, resp.Header.Get("Retry-After"))
	}
	m, _ := http.Get(ts.URL + "/metrics")
	b, _ := io.ReadAll(m.Body)
	m.Body.Close()
	if !strings.Contains(string(b), `chispa_peticiones_total{codigo="429"} 1`) {
		t.Fatalf("la saturación no se cuenta:\n%s", b)
	}
}

// R8-H16: con -pre-drenaje el listener sigue abierto y /healthz responde 503 shutting_down.
func TestR8PreDrenajeHealthz503(t *testing.T) {
	cmd, log := hijo(t, "-addr 127.0.0.1:18793 -apagado 5s -pre-drenaje 2s")
	esperarLog(t, log, "chispa-server en")
	cmd.Process.Signal(syscall.SIGTERM)
	esperarLog(t, log, "pre-drenaje")
	time.Sleep(200 * time.Millisecond)
	resp, err := http.Get("http://127.0.0.1:18793/healthz")
	if err != nil {
		t.Fatalf("el listener ya estaba cerrado: %v", err)
	}
	b, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != 503 || !strings.Contains(string(b), "shutting_down") {
		t.Fatalf("healthz: %d %s", resp.StatusCode, b)
	}
}
