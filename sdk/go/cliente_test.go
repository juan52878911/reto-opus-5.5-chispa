package chispa

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

var ferreteria = Pregunta{
	ID: "q1", Texto: "¿Qué necesita la persona que escribe a la ferretería?", Kind: KindChoice,
	Opciones: []Opcion{{ID: "cotizacion", Description: "pide precio"}, {ID: "pedido", Description: "quiere comprar"}},
}

// servidor devuelve un httptest.Server y un registro de los cuerpos recibidos.
type registro struct {
	mu      sync.Mutex
	cuerpos []peticion
	cabs    []http.Header
}

func (r *registro) n() int { r.mu.Lock(); defer r.mu.Unlock(); return len(r.cuerpos) }

func servidor(t *testing.T, h func(n int, w http.ResponseWriter, r *http.Request)) (*httptest.Server, *registro) {
	t.Helper()
	reg := &registro{}
	var n atomic.Int32
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/v1/decide" {
			b, _ := io.ReadAll(r.Body)
			var p peticion
			_ = json.Unmarshal(b, &p)
			reg.mu.Lock()
			reg.cuerpos = append(reg.cuerpos, p)
			reg.cabs = append(reg.cabs, r.Header.Clone())
			reg.mu.Unlock()
		}
		h(int(n.Add(1)), w, r)
	}))
	t.Cleanup(s.Close)
	return s, reg
}

func json200(w http.ResponseWriter, v string) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = io.WriteString(w, v)
}

func jsonErr(w http.ResponseWriter, status int, cuerpo string, cabs ...string) {
	w.Header().Set("Content-Type", "application/json")
	for i := 0; i+1 < len(cabs); i += 2 {
		w.Header().Set(cabs[i], cabs[i+1])
	}
	w.WriteHeader(status)
	_, _ = io.WriteString(w, cuerpo)
}

// cliente de prueba: sin esperas reales; guarda las que habría hecho.
func clienteDe(url string, esperas *[]time.Duration, opts ...Opt) *Cliente {
	c := Nuevo(url, append([]Opt{ConEspera(100 * time.Millisecond)}, opts...)...)
	c.dormir = func(ctx context.Context, d time.Duration) error {
		if esperas != nil {
			*esperas = append(*esperas, d)
		}
		return ctx.Err()
	}
	return c
}

func comoError(t *testing.T, err error) *ErrorChispa {
	t.Helper()
	var e *ErrorChispa
	if !errors.As(err, &e) {
		t.Fatalf("se esperaba *ErrorChispa, llegó %T: %v", err, err)
	}
	return e
}

func TestChoiceZeroShot(t *testing.T) {
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || r.Header.Get("Content-Type") != "application/json" {
			t.Errorf("método o cabecera: %s %q", r.Method, r.Header.Get("Content-Type"))
		}
		json200(w, `{"results":[{"id":"q1","kind":"choice","answer":"cotizacion","probs":{"cotizacion":0.8,"pedido":0.2},"layer":"L2","escalate":false,"ms":3.2}]}`)
	})
	rs, err := clienteDe(s.URL, nil).Decidir(context.Background(), "¿cuánto vale el cemento?", []Pregunta{ferreteria}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(rs) != 1 || rs[0].Answer != "cotizacion" || rs[0].Layer != "L2" || rs[0].Escalate || rs[0].Probs["pedido"] != 0.2 || rs[0].MS != 3.2 {
		t.Fatalf("resultado: %+v", rs)
	}
	p := reg.cuerpos[0]
	if p.State != "¿cuánto vale el cemento?" || p.Questions[0].Nonce == "" || p.Questions[0].Opciones[0].Description != "pide precio" {
		t.Fatalf("petición: %+v", p)
	}
	if _, ok := reg.cabs[0]["Authorization"]; ok {
		t.Error("sin api_key no debe ir Authorization")
	}
}

func TestNoulYScoreEnOrden(t *testing.T) {
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		json200(w, `{"results":[{"id":"n1","kind":"noul","answer":"true","probs":{"false":0.1,"true":0.9},"layer":"L0","escalate":false,"ms":0.1},`+
			`{"id":"s1","kind":"score","answer":"3","probs":{"1":0.1,"2":0.2,"3":0.7},"layer":"L1","escalate":false,"ms":0.4,"nonce":"abc-1"}]}`)
	})
	qs := []Pregunta{
		{ID: "n1", Texto: "¿Hay una queja?", Kind: KindNoul},
		{ID: "s1", Texto: "¿Qué tan urgente es?", Kind: KindScore, Opciones: []Opcion{{ID: "1"}, {ID: "2"}, {ID: "3"}}, Nonce: "abc-1"},
	}
	rs, err := clienteDe(s.URL, nil).Decidir(context.Background(), "El pedido llegó roto", qs, &DecidirOpts{Nonce: "lote"})
	if err != nil {
		t.Fatal(err)
	}
	if rs[0].Kind != KindNoul || rs[0].Answer != "true" || rs[1].Kind != KindScore || rs[1].Answer != "3" || rs[1].Nonce != "abc-1" {
		t.Fatalf("resultados: %+v", rs)
	}
	got := reg.cuerpos[0].Questions
	if got[0].Nonce != "lote:n1" || got[1].Nonce != "abc-1" {
		t.Errorf("nonces: %q %q", got[0].Nonce, got[1].Nonce)
	}
	if qs[0].Nonce != "" {
		t.Error("no debe mutar las preguntas del llamador")
	}
}

func TestNonceUnaPreguntaYVacioCuentaComoAusente(t *testing.T) {
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		json200(w, `{"results":[{"id":"q1","kind":"choice","answer":"pedido","probs":{},"layer":"L0","escalate":false,"ms":1}]}`)
	})
	c := clienteDe(s.URL, nil)
	if _, err := c.Decidir(context.Background(), "x", []Pregunta{ferreteria}, &DecidirOpts{Nonce: "mi-clave"}); err != nil {
		t.Fatal(err)
	}
	if _, err := c.Decidir(context.Background(), "x", []Pregunta{ferreteria}, &DecidirOpts{Nonce: ""}); err != nil {
		t.Fatal(err)
	}
	if reg.cuerpos[0].Questions[0].Nonce != "mi-clave" || len(reg.cuerpos[1].Questions[0].Nonce) != 32 {
		t.Errorf("nonces: %q %q", reg.cuerpos[0].Questions[0].Nonce, reg.cuerpos[1].Questions[0].Nonce)
	}
}

func TestErrorTipadoDelServidor(t *testing.T) {
	cuerpo := `{"error":{"code":"invalid_kind","message":"questions[0].kind: \"raro\" no valido","question_id":"q1"}}`
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) { jsonErr(w, 400, cuerpo) })
	_, err := clienteDe(s.URL, nil).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
	e := comoError(t, err)
	if e.Status != 400 || e.Codigo != "invalid_kind" || e.IDPregunta != "q1" || !strings.Contains(e.Error(), "invalid_kind") {
		t.Fatalf("error: %+v", e)
	}
	if reg.n() != 1 {
		t.Errorf("un 400 no se reintenta: %d intentos", reg.n())
	}
}

func TestErrorFormatoViejoYSinCuerpo(t *testing.T) {
	for cuerpo, want := range map[string]string{`{"error":"se rompió"}`: "se rompió", `<html>mal</html>`: "<html>mal</html>"} {
		s, _ := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) { jsonErr(w, 500, cuerpo) })
		_, err := clienteDe(s.URL, nil).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
		e := comoError(t, err)
		if e.Status != 500 || e.Codigo != CodHTTPGenerico || e.Mensaje != want {
			t.Errorf("%s: %+v", cuerpo, e)
		}
	}
}

func TestTimeoutDelServidor503SinReintento(t *testing.T) {
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		jsonErr(w, 503, `{"error":{"code":"timeout","message":"plazo vencido"}}`, "Retry-After", "1")
	})
	var esperas []time.Duration
	_, err := clienteDe(s.URL, &esperas).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
	e := comoError(t, err)
	if e.Status != 503 || e.Codigo != CodTimeout || e.RetryAfter != time.Second {
		t.Fatalf("error: %+v", e)
	}
	if reg.n() != 1 || len(esperas) != 0 {
		t.Errorf("intentos %d, esperas %v: el timeout del servidor no se reintenta", reg.n(), esperas)
	}
}

func TestStatusNoReintentables(t *testing.T) {
	for _, st := range []int{405, 413, 500, 502, 504} {
		s, reg := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
			jsonErr(w, st, `{"error":{"code":"x","message":"m"}}`)
		})
		_, err := clienteDe(s.URL, nil).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
		if e := comoError(t, err); e.Status != st || reg.n() != 1 {
			t.Errorf("%d: error %+v, intentos %d", st, e, reg.n())
		}
	}
}

func TestRetryAfter429SeExponeSinReintento(t *testing.T) {
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		jsonErr(w, 429, `{"error":{"code":"rate_limited","message":"despacio"}}`, "Retry-After", "7")
	})
	var esperas []time.Duration
	_, err := clienteDe(s.URL, &esperas).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
	e := comoError(t, err)
	if e.Status != 429 || e.Codigo != "rate_limited" || e.RetryAfter != 7*time.Second {
		t.Fatalf("error: %+v", e)
	}
	if reg.n() != 1 || len(esperas) != 0 {
		t.Errorf("429 no se reintenta (como Python): intentos %d, esperas %v", reg.n(), esperas)
	}
}

func TestRetryAfterConTope(t *testing.T) {
	for v, want := range map[string]time.Duration{"2": 2 * time.Second, "0.5": 500 * time.Millisecond, "999": 30 * time.Second,
		"-3": 0, "": 0, "Wed, 21 Oct 2026 07:28:00 GMT": 0, "NaN": 0} {
		if got := retryAfter(v); got != want {
			t.Errorf("retryAfter(%q) = %v, quiero %v", v, got, want)
		}
	}
}

func TestReintento503ConRetryAfterYMismoNonce(t *testing.T) {
	s, reg := servidor(t, func(n int, w http.ResponseWriter, _ *http.Request) {
		if n < 3 {
			jsonErr(w, 503, `{"error":{"code":"overloaded","message":"ocupado"}}`, "Retry-After", "2")
			return
		}
		json200(w, `{"results":[{"id":"q1","kind":"choice","answer":"pedido","probs":{},"layer":"L1","escalate":false,"ms":1}]}`)
	})
	var esperas []time.Duration
	rs, err := clienteDe(s.URL, &esperas).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
	if err != nil || rs[0].Answer != "pedido" {
		t.Fatalf("%v %+v", err, rs)
	}
	if reg.n() != 3 {
		t.Fatalf("intentos: %d", reg.n())
	}
	n0 := reg.cuerpos[0].Questions[0].Nonce
	if n0 == "" || reg.cuerpos[1].Questions[0].Nonce != n0 || reg.cuerpos[2].Questions[0].Nonce != n0 {
		t.Errorf("el nonce debe repetirse: %v", reg.cuerpos)
	}
	// espera = max(100ms·2^(n-1), Retry-After 2 s)
	if len(esperas) != 2 || esperas[0] != 2*time.Second || esperas[1] != 2*time.Second {
		t.Errorf("esperas: %v", esperas)
	}
}

func TestBackoffExponencialYAgotado(t *testing.T) {
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		jsonErr(w, 503, `{"error":{"code":"overloaded","message":"ocupado"}}`)
	})
	var esperas []time.Duration
	_, err := clienteDe(s.URL, &esperas).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
	e := comoError(t, err)
	if e.Status != 503 || reg.n() != 4 {
		t.Fatalf("error %+v, intentos %d", e, reg.n())
	}
	if want := []time.Duration{100 * time.Millisecond, 200 * time.Millisecond, 400 * time.Millisecond}; len(esperas) != 3 || esperas[0] != want[0] || esperas[1] != want[1] || esperas[2] != want[2] {
		t.Errorf("esperas: %v", esperas)
	}
	if !strings.Contains(e.Error(), "4 intentos") {
		t.Errorf("el mensaje debe decir los intentos: %v", e)
	}
}

func TestErrorDeRedReintentaConMismoNonce(t *testing.T) {
	s, reg := servidor(t, func(n int, w http.ResponseWriter, _ *http.Request) {
		if n == 1 { // corta la conexión sin responder
			conn, _, err := w.(http.Hijacker).Hijack()
			if err != nil {
				t.Error(err)
				return
			}
			conn.Close()
			return
		}
		json200(w, `{"results":[{"id":"q1","kind":"choice","answer":"pedido","probs":{},"layer":"L0","escalate":false,"ms":1}]}`)
	})
	var esperas []time.Duration
	rs, err := clienteDe(s.URL, &esperas).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
	if err != nil || rs[0].Answer != "pedido" {
		t.Fatalf("%v %+v", err, rs)
	}
	if reg.n() != 2 || reg.cuerpos[0].Questions[0].Nonce == "" || reg.cuerpos[0].Questions[0].Nonce != reg.cuerpos[1].Questions[0].Nonce {
		t.Errorf("intentos %d, cuerpos %+v", reg.n(), reg.cuerpos)
	}
	if len(esperas) != 1 || esperas[0] != 100*time.Millisecond {
		t.Errorf("esperas: %v", esperas)
	}
}

func TestConexionRechazadaAgotaReintentos(t *testing.T) {
	s := httptest.NewServer(http.NotFoundHandler())
	url := s.URL
	s.Close()
	var esperas []time.Duration
	_, err := clienteDe(url, &esperas, ConReintentos(2)).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
	e := comoError(t, err)
	if e.Codigo != CodRed || e.Status != 0 || len(esperas) != 2 || e.Causa == nil {
		t.Fatalf("error %+v, esperas %v", e, esperas)
	}
}

func TestTimeoutPropioSinReintento(t *testing.T) {
	parar := make(chan struct{})
	s, reg := servidor(t, func(_ int, _ http.ResponseWriter, r *http.Request) {
		select {
		case <-parar:
		case <-r.Context().Done():
		}
	})
	defer close(parar)
	var esperas []time.Duration
	_, err := clienteDe(s.URL, &esperas, ConTimeout(50*time.Millisecond)).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
	e := comoError(t, err)
	if e.Codigo != CodTimeout || e.Status != 0 {
		t.Fatalf("error: %+v", e)
	}
	if reg.n() != 1 || len(esperas) != 0 {
		t.Errorf("el timeout propio no se reintenta: intentos %d, esperas %v", reg.n(), esperas)
	}
}

func TestContextoCancelado(t *testing.T) {
	s, _ := servidor(t, func(_ int, _ http.ResponseWriter, r *http.Request) { <-r.Context().Done() })
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	_, err := clienteDe(s.URL, nil).Decidir(ctx, "x", []Pregunta{ferreteria}, nil)
	e := comoError(t, err)
	if e.Codigo != CodCancelado || !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("error: %+v", e)
	}
}

func TestCuerpo200IlegibleSeReintenta(t *testing.T) {
	s, reg := servidor(t, func(n int, w http.ResponseWriter, _ *http.Request) {
		if n == 1 {
			json200(w, `{"results":`)
			return
		}
		json200(w, `{"results":[{"id":"q1","kind":"choice","answer":"a","probs":{},"layer":"L0","escalate":false,"ms":1}]}`)
	})
	if _, err := clienteDe(s.URL, nil).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil); err != nil || reg.n() != 2 {
		t.Fatalf("%v, intentos %d", err, reg.n())
	}
}

func TestRespuestaFueraDeOrden(t *testing.T) {
	s, _ := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		json200(w, `{"results":[{"id":"otra","kind":"choice","answer":"a","probs":{},"layer":"L0","escalate":false,"ms":1}]}`)
	})
	_, err := clienteDe(s.URL, nil).Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
	if e := comoError(t, err); e.Codigo != CodRespuesta {
		t.Fatalf("error: %+v", e)
	}
}

func TestAPIKeyBearer(t *testing.T) {
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/healthz" {
			if r.Header.Get("Authorization") != "" {
				t.Errorf("healthz no debe llevar clave: %q", r.Header.Get("Authorization"))
			}
			json200(w, `{"status":"ok"}`)
			return
		}
		json200(w, `{"results":[{"id":"q1","kind":"choice","answer":"a","probs":{},"layer":"L0","escalate":false,"ms":1}]}`)
	})
	c := clienteDe(s.URL, nil, ConAPIKey("sk-1"))
	if _, err := c.Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil); err != nil {
		t.Fatal(err)
	}
	if got := reg.cabs[0].Get("Authorization"); got != "Bearer sk-1" {
		t.Errorf("Authorization: %q", got)
	}
	if err := c.Salud(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestSalud(t *testing.T) {
	s, _ := servidor(t, func(n int, w http.ResponseWriter, _ *http.Request) {
		switch n {
		case 1:
			json200(w, `{"status":"ok"}`)
		case 2:
			json200(w, `{"status":"mal"}`)
		default:
			jsonErr(w, 503, `{"error":{"code":"overloaded","message":"x"}}`)
		}
	})
	c := clienteDe(s.URL, nil)
	if err := c.Salud(context.Background()); err != nil {
		t.Fatal(err)
	}
	if e := comoError(t, c.Salud(context.Background())); e.Codigo != CodRespuesta {
		t.Errorf("%+v", e)
	}
	if e := comoError(t, c.Salud(context.Background())); e.Status != 503 { // Salud no reintenta
		t.Errorf("%+v", e)
	}
}

func TestValidacionLocalEnBytes(t *testing.T) {
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) { json200(w, `{"results":[]}`) })
	c := clienteDe(s.URL, nil)
	mk := func(f func(*Pregunta)) []Pregunta {
		q := ferreteria
		q.Opciones = append([]Opcion(nil), q.Opciones...)
		f(&q)
		return []Pregunta{q}
	}
	// 2049 «ñ» = 2049 caracteres pero 4098 bytes > 4096
	largo := strings.Repeat("ñ", 2049)
	casos := map[string]struct {
		estado string
		qs     []Pregunta
		codigo string
	}{
		"texto en bytes":     {"x", mk(func(q *Pregunta) { q.Texto = largo }), "field_too_long"},
		"descripcion":        {"x", mk(func(q *Pregunta) { q.Opciones[0].Description = largo }), "field_too_long"},
		"id en bytes":        {"x", mk(func(q *Pregunta) { q.ID = strings.Repeat("é", 129) }), "field_too_long"},
		"nonce en bytes":     {"x", mk(func(q *Pregunta) { q.Nonce = strings.Repeat("é", 129) }), "field_too_long"},
		"estado en bytes":    {strings.Repeat("ñ", 131073), mk(func(*Pregunta) {}), "state_too_long"},
		"sin preguntas":      {"x", nil, "empty_questions"},
		"kind invalido":      {"x", mk(func(q *Pregunta) { q.Kind = "raro" }), "invalid_kind"},
		"sin kind":           {"x", mk(func(q *Pregunta) { q.Kind = "" }), "missing_kind"},
		"sin id":             {"x", mk(func(q *Pregunta) { q.ID = "" }), "missing_id"},
		"sin texto":          {"x", mk(func(q *Pregunta) { q.Texto = "" }), "missing_question"},
		"pocas opciones":     {"x", mk(func(q *Pregunta) { q.Opciones = q.Opciones[:1] }), "too_few_options"},
		"opcion repetida":    {"x", mk(func(q *Pregunta) { q.Opciones[1].ID = q.Opciones[0].ID }), "duplicate_option_id"},
		"opcion sin id":      {"x", mk(func(q *Pregunta) { q.Opciones[1].ID = "" }), "missing_option_id"},
		"multi con 1 opcion": {"x", mk(func(q *Pregunta) { q.Kind = KindMulti; q.Opciones = q.Opciones[:1] }), "too_few_options"},
		"multi repetida":     {"x", mk(func(q *Pregunta) { q.Kind = KindMulti; q.Opciones[1].ID = q.Opciones[0].ID }), "duplicate_option_id"},
		"noul con otros ids": {"x", mk(func(q *Pregunta) { q.Kind = KindNoul }), "invalid_options"},
		"ids repetidos":      {"x", append(mk(func(*Pregunta) {}), ferreteria), "duplicate_question_id"},
	}
	for nombre, k := range casos {
		_, err := c.Decidir(context.Background(), k.estado, k.qs, nil)
		if e := comoError(t, err); e.Codigo != k.codigo || e.Status != 0 {
			t.Errorf("%s: %+v, quiero %s", nombre, e, k.codigo)
		}
	}
	// en el borde (4096 bytes exactos) pasa
	justo := strings.Repeat("ñ", 2048)
	if _, err := c.Decidir(context.Background(), "x", mk(func(q *Pregunta) { q.Texto = justo }), nil); err != nil && comoError(t, err).Codigo == "field_too_long" {
		t.Errorf("4096 bytes exactos deben pasar: %v", err)
	}
	// noul con {false,true} en cualquier orden pasa; con 0 opciones también
	for _, ops := range [][]Opcion{nil, {{ID: "true"}, {ID: "false"}}, {{ID: "false"}, {ID: "true"}}} {
		q := Pregunta{ID: "n", Texto: "¿?", Kind: KindNoul, Opciones: ops}
		if e := c.limites.validar("x", []Pregunta{q}); e != nil {
			t.Errorf("noul %v: %v", ops, e)
		}
	}
	if reg.n() > 1 {
		t.Errorf("la validación local no debe llegar al servidor (solo el caso del borde): %d", reg.n())
	}
}

func TestCuerpoMayorQueMaxCuerpo(t *testing.T) {
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) { json200(w, `{"results":[]}`) })
	l := LimitesPorDefecto()
	l.MaxCuerpo = 100
	_, err := clienteDe(s.URL, nil, ConLimites(l)).Decidir(context.Background(), strings.Repeat("a", 200), []Pregunta{ferreteria}, nil)
	if e := comoError(t, err); e.Codigo != "request_too_large" || reg.n() != 0 {
		t.Fatalf("%+v, intentos %d", e, reg.n())
	}
}

func TestJSONSinEscapeHTML(t *testing.T) {
	var cuerpo string
	s, _ := servidor(t, func(_ int, w http.ResponseWriter, r *http.Request) {
		json200(w, `{"results":[]}`)
	})
	s.Config.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		cuerpo = string(b)
		json200(w, `{"results":[{"id":"q1","kind":"choice","answer":"a","probs":{},"layer":"L0","escalate":false,"ms":1}]}`)
	})
	if _, err := clienteDe(s.URL, nil).Decidir(context.Background(), "a<b & c>d", []Pregunta{ferreteria}, nil); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(cuerpo, `"a<b & c>d"`) || !strings.Contains(cuerpo, `"state"`) || strings.Contains(cuerpo, `"options":null`) {
		t.Errorf("cuerpo: %s", cuerpo)
	}
}

func TestNoulSinOpcionesNoEnviaOptions(t *testing.T) {
	var cuerpo string
	s, _ := servidor(t, func(_ int, w http.ResponseWriter, r *http.Request) { json200(w, `{"results":[]}`) })
	s.Config.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		cuerpo = string(b)
		json200(w, `{"results":[{"id":"n","kind":"noul","answer":"true","probs":{},"layer":"L0","escalate":false,"ms":1}]}`)
	})
	if _, err := clienteDe(s.URL, nil).Decidir(context.Background(), "x", []Pregunta{{ID: "n", Texto: "¿?", Kind: KindNoul}}, nil); err != nil {
		t.Fatal(err)
	}
	if strings.Contains(cuerpo, "options") {
		t.Errorf("cuerpo: %s", cuerpo)
	}
}

func TestConcurrente(t *testing.T) {
	s, _ := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		json200(w, `{"results":[{"id":"q1","kind":"choice","answer":"a","probs":{},"layer":"L0","escalate":false,"ms":1}]}`)
	})
	c := Nuevo(s.URL)
	var wg sync.WaitGroup
	for range 16 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if _, err := c.Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil); err != nil {
				t.Error(err)
			}
		}()
	}
	wg.Wait()
}

func TestR6ClaveConSaltoSeRecorta(t *testing.T) {
	s, reg := servidor(t, func(n int, w http.ResponseWriter, r *http.Request) {
		json200(w, `{"results":[{"id":"q1","kind":"choice","answer":"a","probs":{},"layer":"L0","escalate":false,"ms":1}]}`)
	})
	c := clienteDe(s.URL, nil, ConAPIKey(" k\n"))
	if _, err := c.Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil); err != nil {
		t.Fatal(err)
	}
	if got := reg.cabs[0].Get("Authorization"); got != "Bearer k" {
		t.Errorf("Authorization: %q", got)
	}
}

func TestR6ClaveInvalidaSinRedNiReintentos(t *testing.T) {
	s, reg := servidor(t, func(n int, w http.ResponseWriter, r *http.Request) { json200(w, `{}`) })
	c := clienteDe(s.URL, nil, ConAPIKey("a\nb"))
	_, err := c.Decidir(context.Background(), "x", []Pregunta{ferreteria}, nil)
	if e := comoError(t, err); e.Codigo != "invalid_api_key" {
		t.Errorf("código %q", e.Codigo)
	}
	if len(reg.cabs) != 0 {
		t.Errorf("peticiones al servidor: %d", len(reg.cabs))
	}
}

func TestR6HealthzSinClave(t *testing.T) {
	var got string
	s, _ := servidor(t, func(n int, w http.ResponseWriter, r *http.Request) {
		got = r.Header.Get("Authorization")
		json200(w, `{"status":"ok"}`)
	})
	if err := clienteDe(s.URL, nil, ConAPIKey("k")).Salud(context.Background()); err != nil {
		t.Fatal(err)
	}
	if got != "" {
		t.Errorf("/healthz auth=%q", got)
	}
}

func TestR6LimiteCuentaBytesTrasSaneadoUTF8(t *testing.T) {
	q := ferreteria
	q.Texto = strings.Repeat("\xe9", 2000) // 2000 bytes en latin-1, 6000 tras U+FFFD
	_, err := clienteDe("http://127.0.0.1:1", nil).Decidir(context.Background(), "x", []Pregunta{q}, nil)
	if e := comoError(t, err); e.Codigo != "field_too_long" || e.Status != 0 {
		t.Errorf("se esperaba field_too_long local: %v", err)
	}
}

func TestMultiRespuestaConAnswers(t *testing.T) {
	s, reg := servidor(t, func(_ int, w http.ResponseWriter, _ *http.Request) {
		json200(w, `{"results":[{"id":"m","kind":"multi","answer":"cobro","answers":["cobro","atencion"],"probs":{"cobro":0.93,"atencion":0.81,"fraude":0.07},"layer":"L1","escalate":false,"ms":0.5},`+
			`{"id":"v","kind":"multi","answer":"","answers":[],"probs":{"cobro":0.1,"atencion":0.2,"fraude":0.07},"layer":"L1","escalate":false,"ms":0.5},`+
			`{"id":"c","kind":"choice","answer":"a","probs":{"a":0.6,"b":0.4},"layer":"L1","escalate":false,"ms":0.1}]}`)
	})
	ops := []Opcion{{ID: "cobro", Description: "habla de un cobro"}, {ID: "atencion"}, {ID: "fraude"}}
	qs := []Pregunta{
		{ID: "m", Texto: "¿Qué temas toca?", Kind: KindMulti, Opciones: ops},
		{ID: "v", Texto: "¿Qué temas toca?", Kind: KindMulti, Opciones: ops},
		{ID: "c", Texto: "¿Área?", Kind: KindChoice, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}},
	}
	rs, err := clienteDe(s.URL, nil).Decidir(context.Background(), "me cobraron dos veces", qs, nil)
	if err != nil {
		t.Fatal(err)
	}
	if rs[0].Kind != KindMulti || len(rs[0].Answers) != 2 || rs[0].Answers[1] != "atencion" || rs[0].Answer != "cobro" || len(rs[0].Probs) != 3 {
		t.Fatalf("multi: %+v", rs[0])
	}
	if rs[1].Answers == nil || len(rs[1].Answers) != 0 || rs[1].Answer != "" {
		t.Fatalf("multi sin activas: %+v", rs[1])
	}
	if rs[2].Answers != nil {
		t.Fatalf("choice no lleva answers: %+v", rs[2])
	}
	if reg.cuerpos[0].Questions[0].Kind != KindMulti {
		t.Fatalf("petición: %+v", reg.cuerpos[0])
	}
}
