package decide

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// R8 H5: un lote dentro de la ráfaga no deja deuda: tras esperar lo que tarda un token, la clave vuelve a pasar.
func TestR8CuboLoteNoDejaDeuda(t *testing.T) {
	_, h, rl := servidorConClaves(t, []ClaveAPI{{ID: "a", HashSHA256: HashClave("k"), RPS: 2}})
	envia := func(n int) int {
		r := httptest.NewRequest("POST", "/v1/decide", strings.NewReader(preguntas(n, "")))
		r.Header.Set("Authorization", "Bearer k")
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, r)
		return rr.Code
	}
	if c := envia(10); c != 200 {
		t.Fatalf("lote de 10 con rps 2: %d", c)
	}
	rl.avanza(1 * time.Second)
	if c := envia(1); c != 200 {
		t.Fatalf("tras 1 s la clave sigue bloqueada por deuda: %d", c)
	}
}

// R8 H6: un cuerpo lento no retiene hueco de -max-en-curso; el hueco se toma tras leer el cuerpo y da 503 overloaded.
func TestR8SemaforoTrasLeerCuerpo(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"x"}}
	s, _ := servidorRecargable(t, a, "")
	s.ConMaxEnCurso(1).ConPlazoCuerpo(2 * time.Second)
	srv := httptest.NewServer(s.Handler())
	defer srv.Close()
	c, err := net.Dial("tcp", srv.Listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	fmt.Fprintf(c, "POST /v1/decide HTTP/1.1\r\nHost: x\r\nContent-Length: 100000\r\n\r\n{")
	time.Sleep(100 * time.Millisecond)
	post := func() *http.Response {
		resp, err := http.Post(srv.URL+"/v1/decide", "application/json", strings.NewReader(cuerpoNonce))
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		return resp
	}
	if resp := post(); resp.StatusCode != 200 {
		t.Fatalf("el cuerpo lento retiene el hueco: %d", resp.StatusCode)
	}
	s.enCurso <- struct{}{} // hueco ocupado por una petición con el cuerpo ya leído
	resp, err := http.Post(srv.URL+"/v1/decide", "application/json", strings.NewReader(cuerpoNonce))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var b strings.Builder
	buf := make([]byte, 512)
	n, _ := resp.Body.Read(buf)
	b.Write(buf[:n])
	if resp.StatusCode != 503 || resp.Header.Get("Retry-After") == "" || !strings.Contains(b.String(), `"overloaded"`) {
		t.Fatalf("saturado: %d %q %s", resp.StatusCode, resp.Header.Get("Retry-After"), b.String())
	}
}

func recargarDesde(h http.Handler, auth, ip string) int {
	rr := httptest.NewRecorder()
	r := httptest.NewRequest("POST", "/v1/admin/recargar", nil)
	r.RemoteAddr = ip + ":1234"
	r.Header.Set("Authorization", auth)
	h.ServeHTTP(rr, r)
	return rr.Code
}

// R8 H7: el cubo es por IP: un atacante agotando el suyo no deja fuera al operador, y la tabla tiene tope.
func TestR8AdminCuboPorIP(t *testing.T) {
	s, h, _ := servidorAdminHash(t, tok32)
	for i := 0; i < adminRafaga+5; i++ {
		recargarDesde(h, "Bearer mala", "203.0.113.9")
	}
	if c := recargarDesde(h, "Bearer mala", "203.0.113.9"); c != 429 {
		t.Fatalf("el atacante debe quedar limitado: %d", c)
	}
	if c := recargarDesde(h, "Bearer "+tok32, "198.51.100.1"); c != 200 {
		t.Fatalf("el operador desde otra IP debe pasar: %d", c)
	}
	est := s.Met.adminEst()
	for i := 0; i < adminMaxCubos+50; i++ {
		recargarDesde(h, "Bearer mala", fmt.Sprintf("10.%d.%d.%d", i>>16&255, i>>8&255, i&255))
	}
	est.mu.Lock()
	n := len(est.ips)
	est.mu.Unlock()
	if n > adminMaxCubos {
		t.Fatalf("la tabla de IPs creció a %d", n)
	}
}

// R8 H11: /metrics protegidas comparan contra la credencial vigente: tras rotar, el viejo deja de valer y el nuevo vale.
func TestR8MetricasSiguenRotacion(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"x"}}
	a.t, a.met = t, NuevasMetricas()
	ar, err := a.armar()
	if err != nil {
		t.Fatal(err)
	}
	arm := func() (*Armado, error) {
		x, err := a.armar()
		if x != nil {
			x.AdminToken = "token-nuevo"
		}
		return x, err
	}
	s := NuevoServidorDe(ar, a.met).ConRecarga(arm, "token-viejo").ConMetricasProtegidas(true)
	h := s.Handler()
	get := func(tok string) int {
		r := httptest.NewRequest("GET", "/metrics", nil)
		r.Header.Set("Authorization", "Bearer "+tok)
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, r)
		return rr.Code
	}
	if get("token-viejo") != 200 {
		t.Fatal("antes de rotar el token vigente debe valer")
	}
	if err := s.Recargar(); err != nil {
		t.Fatal(err)
	}
	if c := get("token-viejo"); c != 401 {
		t.Fatalf("el token viejo sigue leyendo /metrics: %d", c)
	}
	if c := get("token-nuevo"); c != 200 {
		t.Fatalf("el token nuevo recibe %d", c)
	}
	// los fallos pasan por el cubo de admin: /metrics no es un oráculo ilimitado
	for i := 0; i < adminRafaga+2; i++ {
		get("mala")
	}
	if c := get("token-nuevo"); c != 401 {
		t.Fatalf("tras agotar el cubo de la IP, ni el token bueno pasa (sin oráculo): %d", c)
	}
}

// R8 H13: una desconexión del cliente no cuenta como 503.
func TestR8DesconexionNoCuenta503(t *testing.T) {
	met := NuevasMetricas()
	h := ConTimeoutMet(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-r.Context().Done()
	}), time.Minute, met)
	ctx, cancel := context.WithCancel(context.Background())
	r := httptest.NewRequest("POST", "/v1/decide", nil).WithContext(ctx)
	go func() { time.Sleep(50 * time.Millisecond); cancel() }()
	h.ServeHTTP(httptest.NewRecorder(), r)
	var sb strings.Builder
	met.Escribe(&sb)
	if strings.Contains(sb.String(), `codigo="503"`) {
		t.Fatalf("desconexión contada como 503:\n%s", sb.String())
	}
	// y un timeout real sí se cuenta
	h = ConTimeoutMet(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-r.Context().Done() }), 30*time.Millisecond, met)
	h.ServeHTTP(httptest.NewRecorder(), httptest.NewRequest("POST", "/v1/decide", nil))
	sb.Reset()
	met.Escribe(&sb)
	if !strings.Contains(sb.String(), `codigo="503"} 1`) {
		t.Fatalf("el timeout real debe contar:\n%s", sb.String())
	}
}
