package decide

import (
	"bufio"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"runtime"
	"strings"
	"testing"
	"time"
)

func preguntas(n int, nonce string) string {
	var qs []string
	for i := 0; i < n; i++ {
		qs = append(qs, fmt.Sprintf(`{"id":"q%d","question":"¿?","kind":"choice","nonce":%q,"options":[{"id":"a"},{"id":"b"}]}`, i, nonce))
	}
	return `{"state":"s","questions":[` + strings.Join(qs, ",") + `]}`
}

// Hallazgo 1: un cuerpo lento no retiene el modelo ni esquiva el plazo.
func TestR7CuerpoLentoNoRetieneModelo(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"x"}}
	s, _ := servidorRecargable(t, a, "")
	s.ConPlazoCuerpo(300 * time.Millisecond)
	srv := httptest.NewServer(ConTimeout(s.Handler(), 30*time.Second))
	defer srv.Close()
	c, err := net.Dial("tcp", srv.Listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	fmt.Fprintf(c, "POST /v1/decide HTTP/1.1\r\nHost: x\r\nContent-Length: 100000\r\n\r\n{")
	v := s.cur.Load()
	time.Sleep(100 * time.Millisecond)
	v.mu.Lock()
	refs := v.refs
	v.mu.Unlock()
	if refs != 0 {
		t.Fatalf("mientras llega el cuerpo el modelo ya tiene %d refs", refs)
	}
	c.SetReadDeadline(time.Now().Add(3 * time.Second))
	resp, err := http.ReadResponse(bufio.NewReader(c), nil)
	if err != nil {
		t.Fatalf("sin respuesta al cuerpo lento: %v", err)
	}
	if resp.StatusCode != 400 && resp.StatusCode != 503 { // bajo ConTimeout, el plazo cancela el ctx y responde su 503
		t.Fatalf("estado %d", resp.StatusCode)
	}
}

// Hallazgo 4: 1 MB de opciones vacías se rechaza sin reservar ~95 MB.
func TestR7DecodificacionAcotada(t *testing.T) {
	_, h := servidorRecargable(t, &armadorModelos{etiquetas: []string{"x"}}, "")
	body := `{"questions":[{"id":"a","question":"q","kind":"choice","options":[` + strings.Repeat("{},", 349000) + `{}]}]}`
	if len(body) > 1<<20 {
		t.Fatalf("cuerpo de %d bytes", len(body))
	}
	var m0, m1 runtime.MemStats
	runtime.ReadMemStats(&m0)
	rr := post(h, body)
	runtime.ReadMemStats(&m1)
	if rr.Code != 400 || !strings.Contains(rr.Body.String(), ErrDemasiadasOpc) || !strings.Contains(rr.Body.String(), `"question_id":"a"`) {
		t.Fatalf("%d %s", rr.Code, rr.Body)
	}
	if d := m1.TotalAlloc - m0.TotalAlloc; d > 16<<20 {
		t.Fatalf("la petición reservó %d MB", d>>20)
	}
}

func TestR7TopeDePreguntasSinDecodificar(t *testing.T) {
	_, h := servidorRecargable(t, &armadorModelos{etiquetas: []string{"x"}}, "")
	rr := post(h, `{"questions":[`+strings.Repeat("{},", 300)+`{}]}`)
	if rr.Code != 400 || !strings.Contains(rr.Body.String(), ErrDemasiadasPreg) {
		t.Fatalf("%d %s", rr.Code, rr.Body)
	}
}

// Hallazgo 13: JSON estricto.
func TestR7JSONEstricto(t *testing.T) {
	_, h := servidorRecargable(t, &armadorModelos{etiquetas: []string{"x"}}, "")
	q := `"questions":[{"id":"1","question":"q","kind":"noul"}]`
	for n, c := range map[string]string{
		"state en mayúsculas":  `{"state":"a","STATE":"b",` + q + `}`,
		"solo mayúsculas":      `{"State":"a",` + q + `}`,
		"state repetido":       `{"state":"a","state":"b",` + q + `}`,
		"id de pregunta":       `{"questions":[{"ID":"1","question":"q","kind":"noul"}]}`,
		"id de pregunta dup":   `{"questions":[{"id":"1","id":"2","question":"q","kind":"noul"}]}`,
		"opción en mayúsculas": `{"questions":[{"id":"1","question":"q","kind":"choice","options":[{"Id":"a"},{"iD":"b"}]}]}`,
		"opción con id dup":    `{"questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a","id":"b"},{"id":"c"}]}]}`,
		"anidado sin fin":      `{"state":` + strings.Repeat("[", 100) + strings.Repeat("]", 100) + `,` + q + `}`,
	} {
		rr := post(h, c)
		if rr.Code != 400 || !strings.Contains(rr.Body.String(), ErrJSONInvalido) {
			t.Errorf("%s: %d %s", n, rr.Code, rr.Body)
		}
	}
	if rr := post(h, `{"state":"a",`+q+`}`); rr.Code != 200 {
		t.Fatalf("válida: %d %s", rr.Code, rr.Body)
	}
}

// Hallazgo 16: la caché de nonces no cruza claves de API.
func TestR7NoncePorClave(t *testing.T) {
	s, h, _ := servidorConClaves(t, []ClaveAPI{
		{ID: "a", HashSHA256: HashClave("ka"), RPS: 100, Rafaga: 100},
		{ID: "b", HashSHA256: HashClave("kb"), RPS: 100, Rafaga: 100}})
	if rr := conClave(h, "ka"); rr.Code != 200 {
		t.Fatal(rr.Body)
	}
	if rr := conClave(h, "ka"); rr.Code != 200 || s.Met.NonceHits.Load() != 1 {
		t.Fatalf("misma clave: aciertos %d", s.Met.NonceHits.Load())
	}
	if rr := conClave(h, "kb"); rr.Code != 200 {
		t.Fatal(rr.Body)
	}
	if n := s.Met.NonceHits.Load(); n != 1 {
		t.Fatalf("la clave b acertó la caché de la a (aciertos %d)", n)
	}
}

// Hallazgo 11: /metrics protegible.
func TestR7MetricasProtegidas(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"x"}}
	s, h := servidorRecargable(t, a, "adm")
	s.ConClaves([]ClaveAPI{{ID: "a", HashSHA256: HashClave("ka"), RPS: 10}}, nil)
	get := func(tok string) int {
		r := httptest.NewRequest("GET", "/metrics", nil)
		if tok != "" {
			r.Header.Set("Authorization", "Bearer "+tok)
		}
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, r)
		return rr.Code
	}
	if c := get(""); c != 200 {
		t.Fatalf("por defecto /metrics debe seguir abierto: %d", c)
	}
	s.ConMetricasProtegidas(true)
	for tok, want := range map[string]int{"": 401, "mala": 401, "adm": 200, "ka": 200} {
		if c := get(tok); c != want {
			t.Errorf("token %q: %d, quería %d", tok, c, want)
		}
	}
}

// Hallazgo 8 (auth): el cubo cobra por pregunta.
func TestR7CuboCobraPorPregunta(t *testing.T) {
	_, h, rl := servidorConClaves(t, []ClaveAPI{{ID: "a", HashSHA256: HashClave("k"), RPS: 1, Rafaga: 4}})
	envia := func(n int) *httptest.ResponseRecorder {
		r := httptest.NewRequest("POST", "/v1/decide", strings.NewReader(preguntas(n, "")))
		r.Header.Set("Authorization", "Bearer k")
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, r)
		return rr
	}
	if rr := envia(4); rr.Code != 200 { // 4 preguntas = toda la ráfaga
		t.Fatalf("%d %s", rr.Code, rr.Body)
	}
	if rr := envia(1); rr.Code != 429 {
		t.Fatalf("tras gastar la ráfaga en preguntas, la siguiente debe limitarse: %d", rr.Code)
	}
	rl.avanza(5 * time.Second)
	if rr := envia(1); rr.Code != 200 {
		t.Fatalf("tras recargar: %d", rr.Code)
	}
}

// Hallazgo 4: tope de peticiones simultáneas.
func TestR7MaxEnCurso(t *testing.T) {
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
	resp, err := http.Post(srv.URL+"/v1/decide", "application/json", strings.NewReader(cuerpoNonce))
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 429 || resp.Header.Get("Retry-After") == "" {
		t.Fatalf("%d, Retry-After %q", resp.StatusCode, resp.Header.Get("Retry-After"))
	}
}
