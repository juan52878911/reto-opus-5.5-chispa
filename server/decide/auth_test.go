package decide

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

// reloj es un reloj manual y seguro para goroutines.
type reloj struct {
	mu sync.Mutex
	t  time.Time
}

func (r *reloj) ahora() time.Time { r.mu.Lock(); defer r.mu.Unlock(); return r.t }
func (r *reloj) avanza(d time.Duration) {
	r.mu.Lock()
	r.t = r.t.Add(d)
	r.mu.Unlock()
}

func servidorConClaves(t *testing.T, ks []ClaveAPI) (*Servidor, http.Handler, *reloj) {
	t.Helper()
	a := &armadorModelos{etiquetas: []string{"x"}}
	s, _ := servidorRecargable(t, a, "")
	rl := &reloj{t: time.Unix(1000, 0)}
	s.ConClaves(ks, rl.ahora)
	return s, s.Handler(), rl
}

func conClave(h http.Handler, clave string) *httptest.ResponseRecorder {
	r := httptest.NewRequest("POST", "/v1/decide", strings.NewReader(cuerpoNonce))
	if clave != "" {
		r.Header.Set("Authorization", "Bearer "+clave)
	}
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, r)
	return rr
}

func TestAuthSinClavesTodoPasa(t *testing.T) {
	_, h, _ := servidorConClaves(t, nil)
	for i := 0; i < 50; i++ {
		if rr := conClave(h, ""); rr.Code != 200 {
			t.Fatalf("sin api_keys: %d %s", rr.Code, rr.Body)
		}
	}
	// Una cabecera cualquiera tampoco molesta.
	if rr := conClave(h, "lo-que-sea"); rr.Code != 200 {
		t.Fatalf("%d", rr.Code)
	}
}

func TestAuthClaveMala401(t *testing.T) {
	s, h, _ := servidorConClaves(t, []ClaveAPI{{ID: "a", HashSHA256: HashClave("buena"), RPS: 100, Rafaga: 100}})
	for _, c := range []string{"", "mala", "buen", "buena "} {
		rr := conClave(h, c)
		if rr.Code != 401 || !strings.Contains(rr.Body.String(), `"unauthorized"`) || rr.Header().Get("WWW-Authenticate") != "Bearer" {
			t.Errorf("clave %q: %d %s", c, rr.Code, rr.Body)
		}
	}
	// Esquema distinto de Bearer, y el hash en lugar de la clave.
	r := httptest.NewRequest("POST", "/v1/decide", strings.NewReader(cuerpoNonce))
	r.Header.Set("Authorization", "Basic buena")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, r)
	if rr.Code != 401 {
		t.Errorf("Basic: %d", rr.Code)
	}
	if rr := conClave(h, HashClave("buena")); rr.Code != 401 {
		t.Errorf("el hash no es la clave: %d", rr.Code)
	}
	if rr := conClave(h, "buena"); rr.Code != 200 {
		t.Errorf("clave buena: %d %s", rr.Code, rr.Body)
	}
	if got := s.Met.AuthRechazos.Load(); got != 6 {
		t.Errorf("rechazos = %d, quería 6", got)
	}
}

func TestAuthRafagaAgotada429(t *testing.T) {
	_, h, rl := servidorConClaves(t, []ClaveAPI{{ID: "a", HashSHA256: HashClave("k"), RPS: 0.5, Rafaga: 2}})
	for i := 0; i < 2; i++ {
		if rr := conClave(h, "k"); rr.Code != 200 {
			t.Fatalf("ráfaga %d: %d", i, rr.Code)
		}
	}
	rr := conClave(h, "k")
	if rr.Code != 429 || rr.Header().Get("Retry-After") != "2" || !strings.Contains(rr.Body.String(), `"rate_limited"`) {
		t.Fatalf("%d Retry-After=%q %s", rr.Code, rr.Header().Get("Retry-After"), rr.Body)
	}
	if rr.Header().Get("Content-Type") != "application/json" {
		t.Errorf("content-type %q", rr.Header().Get("Content-Type"))
	}
	rl.avanza(time.Second) // medio token: aún no
	if rr := conClave(h, "k"); rr.Code != 429 || rr.Header().Get("Retry-After") != "1" {
		t.Fatalf("a 1 s: %d Retry-After=%q", rr.Code, rr.Header().Get("Retry-After"))
	}
	rl.avanza(time.Second) // un token entero
	if rr := conClave(h, "k"); rr.Code != 200 {
		t.Fatalf("tras recargar: %d", rr.Code)
	}
}

func TestAuthDosClavesLimitesIndependientes(t *testing.T) {
	s, h, _ := servidorConClaves(t, []ClaveAPI{
		{ID: "chica", HashSHA256: HashClave("kc"), RPS: 1, Rafaga: 1},
		{ID: "grande", HashSHA256: HashClave("kg"), RPS: 1, Rafaga: 5},
	})
	if rr := conClave(h, "kc"); rr.Code != 200 {
		t.Fatal(rr.Code)
	}
	if rr := conClave(h, "kc"); rr.Code != 429 {
		t.Fatalf("chica debía agotarse: %d", rr.Code)
	}
	for i := 0; i < 5; i++ {
		if rr := conClave(h, "kg"); rr.Code != 200 {
			t.Fatalf("grande %d: %d (la chica no debe gastarle cupo)", i, rr.Code)
		}
	}
	if rr := conClave(h, "kg"); rr.Code != 429 {
		t.Fatalf("grande debía agotarse: %d", rr.Code)
	}
	m := httptest.NewRecorder()
	h.ServeHTTP(m, httptest.NewRequest("GET", "/metrics", nil))
	for _, want := range []string{
		`chispa_clave_peticiones_total{clave="chica",resultado="ok"} 1`,
		`chispa_clave_peticiones_total{clave="chica",resultado="limitada"} 1`,
		`chispa_clave_peticiones_total{clave="grande",resultado="ok"} 5`,
		`chispa_clave_peticiones_total{clave="grande",resultado="limitada"} 1`,
		`chispa_peticiones_total{codigo="429"} 2`,
		`chispa_auth_rechazos_total 0`,
	} {
		if !strings.Contains(m.Body.String(), want) {
			t.Errorf("falta en /metrics: %s", want)
		}
	}
	if strings.Contains(m.Body.String(), "kc") || strings.Contains(m.Body.String(), HashClave("kc")) {
		t.Error("/metrics no debe llevar la clave ni su hash")
	}
	_ = s
}

func TestAuthHealthzMetricsAbiertos(t *testing.T) {
	_, h, _ := servidorConClaves(t, []ClaveAPI{{ID: "a", HashSHA256: HashClave("k"), RPS: 1}})
	for _, p := range []string{"/healthz", "/metrics"} {
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, httptest.NewRequest("GET", p, nil))
		if rr.Code != 200 {
			t.Errorf("%s con api_keys sin clave: %d", p, rr.Code)
		}
	}
}

// admin_token sigue mandando en /v1/admin/recargar: una clave de API no sirve ahí, y el token de admin no sirve en /v1/decide.
func TestAuthAdminSigueConAdminToken(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"x"}}
	s, _ := servidorRecargable(t, a, "adm")
	s.ConClaves([]ClaveAPI{{ID: "a", HashSHA256: HashClave("k"), RPS: 10}}, nil)
	h := s.Handler()
	pide := func(ruta, tok string) int {
		r := httptest.NewRequest("POST", ruta, strings.NewReader(cuerpoNonce))
		r.Header.Set("Authorization", "Bearer "+tok)
		rr := httptest.NewRecorder()
		h.ServeHTTP(rr, r)
		return rr.Code
	}
	if c := pide("/v1/admin/recargar", "k"); c != 401 {
		t.Errorf("clave de API en admin: %d", c)
	}
	if c := pide("/v1/decide", "adm"); c != 401 {
		t.Errorf("admin_token en decide: %d", c)
	}
	if c := pide("/v1/admin/recargar", "adm"); c != 200 {
		t.Errorf("admin_token en admin: %d", c)
	}
}

// Las claves se releen en cada recarga (rotación sin reiniciar).
func TestAuthRecargaCambiaClaves(t *testing.T) {
	var ks atomicClaves
	ks.set([]ClaveAPI{{ID: "a", HashSHA256: HashClave("vieja"), RPS: 10}})
	a := &armadorModelos{etiquetas: []string{"x"}}
	a.met = NuevasMetricas()
	armar := func() (*Armado, error) {
		ar, err := a.armar()
		if ar != nil {
			ar.APIKeys = ks.get()
		}
		return ar, err
	}
	ar, _ := armar()
	s := NuevoServidorDe(ar, a.met).ConRecarga(armar, "")
	h := s.Handler()
	if conClave(h, "vieja").Code != 200 || conClave(h, "nueva").Code != 401 {
		t.Fatal("estado inicial")
	}
	ks.set([]ClaveAPI{{ID: "b", HashSHA256: HashClave("nueva"), RPS: 10}})
	if err := s.Recargar(); err != nil {
		t.Fatal(err)
	}
	if conClave(h, "vieja").Code != 401 || conClave(h, "nueva").Code != 200 {
		t.Fatal("tras recargar")
	}
}

type atomicClaves struct {
	mu sync.Mutex
	v  []ClaveAPI
}

func (a *atomicClaves) set(v []ClaveAPI) { a.mu.Lock(); a.v = v; a.mu.Unlock() }
func (a *atomicClaves) get() []ClaveAPI  { a.mu.Lock(); defer a.mu.Unlock(); return a.v }

// Con carga concurrente (para -race): exactamente rafaga peticiones pasan.
func TestAuthConcurrenciaRespetaRafaga(t *testing.T) {
	_, h, _ := servidorConClaves(t, []ClaveAPI{{ID: "a", HashSHA256: HashClave("k"), RPS: 1, Rafaga: 20}})
	var wg sync.WaitGroup
	var mu sync.Mutex
	ok, lim := 0, 0
	for i := 0; i < 100; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			c := conClave(h, "k").Code
			mu.Lock()
			defer mu.Unlock()
			switch c {
			case 200:
				ok++
			case 429:
				lim++
			}
		}()
	}
	wg.Wait()
	if ok != 20 || lim != 80 {
		t.Fatalf("ok=%d limitadas=%d, quería 20 y 80", ok, lim)
	}
}

func TestConfigApiKeys(t *testing.T) {
	h := HashClave("x")
	c, err := CargarConfig(escribirConfig(t, `{"api_keys":[{"id":"piloto","hash_sha256":"`+h+`","rps":5,"rafaga":10}]}`))
	if err != nil || len(c.APIKeys) != 1 || c.APIKeys[0].ID != "piloto" || c.APIKeys[0].Rafaga != 10 {
		t.Fatalf("%+v %v", c, err)
	}
	malas := map[string]string{
		"clave en claro": `{"id":"a","clave":"secreto","rps":1}`,
		"sin id":         `{"hash_sha256":"` + h + `","rps":1}`,
		"hash corto":     `{"id":"a","hash_sha256":"abc","rps":1}`,
		"hash no hex":    `{"id":"a","hash_sha256":"` + strings.Repeat("z", 64) + `","rps":1}`,
		"rps cero":       `{"id":"a","hash_sha256":"` + h + `","rps":0}`,
		"rps negativo":   `{"id":"a","hash_sha256":"` + h + `","rps":-1}`,
		"rafaga neg":     `{"id":"a","hash_sha256":"` + h + `","rps":1,"rafaga":-1}`,
		"id repetido":    `{"id":"a","hash_sha256":"` + h + `","rps":1},{"id":"a","hash_sha256":"` + HashClave("y") + `","rps":1}`,
		"hash repetido":  `{"id":"a","hash_sha256":"` + h + `","rps":1},{"id":"b","hash_sha256":"` + h + `","rps":1}`,
	}
	for n, k := range malas {
		if _, err := CargarConfig(escribirConfig(t, `{"api_keys":[`+k+`]}`)); err == nil {
			t.Errorf("%s: debía fallar", n)
		}
	}
}

func TestRafagaPorDefectoEsRps(t *testing.T) {
	_, h, _ := servidorConClaves(t, []ClaveAPI{{ID: "a", HashSHA256: HashClave("k"), RPS: 3}})
	for i := 0; i < 3; i++ {
		if rr := conClave(h, "k"); rr.Code != 200 {
			t.Fatalf("%d: %d", i, rr.Code)
		}
	}
	if rr := conClave(h, "k"); rr.Code != 429 {
		t.Fatalf("4.ª: %d", rr.Code)
	}
}
