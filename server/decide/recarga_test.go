package decide

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// decisorModelo contesta siempre con su etiqueta (el «modelo» que lo armó) y cuenta cuántas peticiones lleva en vuelo.
type decisorModelo struct {
	etiqueta string
	enVuelo  atomic.Int64
	pausa    time.Duration
}

func (d *decisorModelo) Nombre() string { return "L0" }
func (d *decisorModelo) Decidir(_ context.Context, p Pregunta) (Respuesta, error) {
	d.enVuelo.Add(1)
	defer d.enVuelo.Add(-1)
	time.Sleep(d.pausa)
	return Respuesta{Answer: d.etiqueta, Conf: 0.9, Probs: map[string]float64{d.etiqueta: 0.9}}, nil
}

// armadorModelos arma un modelo por llamada: etiquetas[0], etiquetas[1]... (la última se repite). Un error en errs[i] hace fallar esa llamada.
type armadorModelos struct {
	t         *testing.T
	met       *Metricas
	etiquetas []string
	pausa     time.Duration
	llamadas  atomic.Int64
	errs      map[int]error
	cerrados  atomic.Int64
	cerradoEn atomic.Int64 // peticiones en vuelo vistas al cerrar un modelo (debe ser 0)
}

func (a *armadorModelos) armar() (*Armado, error) {
	i := int(a.llamadas.Add(1)) - 1
	if err := a.errs[i]; err != nil {
		return nil, err
	}
	e := a.etiquetas[min(i, len(a.etiquetas)-1)]
	d := &decisorModelo{etiqueta: e, pausa: a.pausa}
	c, err := NuevaCascada([]Capa{{"L0", 0.8}}, []Decisor{d}, a.met)
	if err != nil {
		return nil, err
	}
	return &Armado{Cascada: c, CacheRespuestas: 16, Limites: LimitesPorDefecto(), Cerrar: func() error {
		a.cerrados.Add(1)
		a.cerradoEn.Add(d.enVuelo.Load())
		return nil
	}}, nil
}

func servidorRecargable(t *testing.T, a *armadorModelos, token string) (*Servidor, http.Handler) {
	t.Helper()
	a.t, a.met = t, NuevasMetricas()
	ar, err := a.armar()
	if err != nil {
		t.Fatal(err)
	}
	s := NuevoServidorDe(ar, a.met).ConRecarga(a.armar, token)
	return s, s.Handler()
}

const cuerpoNonce = `{"state":"s","questions":[{"id":"q","question":"¿?","kind":"choice","nonce":"n1","options":[{"id":"a"},{"id":"b"}]}]}`

func respuesta(t *testing.T, h http.Handler, cuerpo string) string {
	t.Helper()
	rr := post(h, cuerpo)
	if rr.Code != 200 {
		t.Fatalf("estado %d: %s", rr.Code, rr.Body)
	}
	var r struct{ Results []Resultado }
	if err := json.Unmarshal(rr.Body.Bytes(), &r); err != nil || len(r.Results) != 1 {
		t.Fatalf("respuesta ilegible: %v %s", err, rr.Body)
	}
	if _, ok := r.Results[0].Probs[r.Results[0].Answer]; !ok {
		t.Fatalf("answer y probs de modelos distintos: %+v", r.Results[0])
	}
	return r.Results[0].Answer
}

func metricaRecargas(s *Servidor, resultado string) string {
	rr := httptest.NewRecorder()
	s.Handler().ServeHTTP(rr, httptest.NewRequest("GET", "/metrics", nil))
	for _, l := range strings.Split(rr.Body.String(), "\n") {
		if strings.HasPrefix(l, `chispa_recargas_total{resultado="`+resultado+`"}`) {
			return strings.TrimPrefix(l, `chispa_recargas_total{resultado="`+resultado+`"} `)
		}
	}
	return "ausente"
}

// Los nonces de un modelo no devuelven su respuesta con el modelo nuevo.
func TestRecargaVaciaNonces(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"v1", "v2"}}
	s, h := servidorRecargable(t, a, "")
	if g := respuesta(t, h, cuerpoNonce); g != "v1" {
		t.Fatalf("antes de recargar: %s", g)
	}
	if g := respuesta(t, h, cuerpoNonce); g != "v1" || s.Met.NonceHits.Load() != 1 {
		t.Fatalf("el nonce debía salir de caché: %s, hits %d", g, s.Met.NonceHits.Load())
	}
	if err := s.Recargar(); err != nil {
		t.Fatal(err)
	}
	if g := respuesta(t, h, cuerpoNonce); g != "v2" {
		t.Fatalf("tras recargar, el nonce viejo devolvió %s", g)
	}
	if s.Generacion() != 2 || a.cerrados.Load() != 1 || metricaRecargas(s, "ok") != "1" {
		t.Fatalf("generación %d, cerrados %d, ok %s", s.Generacion(), a.cerrados.Load(), metricaRecargas(s, "ok"))
	}
}

// Un .chispa que no abre o no valida deja el modelo viejo, cuenta el error y no cierra nada.
func TestRecargaFallidaConservaModelo(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"v1", "v2"}, errs: map[int]error{1: errors.New(".chispa corrupto")}}
	s, h := servidorRecargable(t, a, "")
	if err := s.Recargar(); err == nil {
		t.Fatal("debía fallar")
	}
	if g := respuesta(t, h, cuerpoNonce); g != "v1" || s.Generacion() != 1 || a.cerrados.Load() != 0 {
		t.Fatalf("modelo %s gen %d cerrados %d", g, s.Generacion(), a.cerrados.Load())
	}
	if metricaRecargas(s, "error") != "1" || metricaRecargas(s, "ok") != "0" {
		t.Fatalf("métricas: error %s ok %s", metricaRecargas(s, "error"), metricaRecargas(s, "ok"))
	}
	if err := s.Recargar(); err != nil { // la siguiente (ya sin error) sí prospera
		t.Fatal(err)
	}
	if g := respuesta(t, h, cuerpoNonce); g != "v2" {
		t.Fatalf("tras la recarga buena: %s", g)
	}
}

func recargar(h http.Handler, auth string) *httptest.ResponseRecorder {
	rr := httptest.NewRecorder()
	r := httptest.NewRequest("POST", "/v1/admin/recargar", nil)
	if auth != "" {
		r.Header.Set("Authorization", auth)
	}
	h.ServeHTTP(rr, r)
	return rr
}

func TestAdminRecargarToken(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"v1", "v2"}}
	s, h := servidorRecargable(t, a, "secreto")
	for _, auth := range []string{"", "Bearer otro", "secreto", "Basic secreto", "Bearer "} {
		if rr := recargar(h, auth); rr.Code != 401 || rr.Header().Get("WWW-Authenticate") == "" || !strings.Contains(rr.Body.String(), `"unauthorized"`) {
			t.Fatalf("auth %q: %d %s", auth, rr.Code, rr.Body)
		}
	}
	if s.Generacion() != 1 || a.llamadas.Load() != 1 {
		t.Fatal("un token incorrecto recargó")
	}
	if rr := httptest.NewRecorder(); true {
		h.ServeHTTP(rr, httptest.NewRequest("GET", "/v1/admin/recargar", nil))
		if rr.Code != 405 {
			t.Fatalf("GET: %d", rr.Code)
		}
	}
	rr := recargar(h, "Bearer secreto")
	if rr.Code != 200 || !strings.Contains(rr.Body.String(), `"generation":2`) || respuesta(t, h, cuerpoNonce) != "v2" {
		t.Fatalf("recarga con token: %d %s", rr.Code, rr.Body)
	}
}

func TestAdminRecargarFallaConserva500(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"v1"}, errs: map[int]error{1: errors.New("roto")}}
	s, h := servidorRecargable(t, a, "t")
	if rr := recargar(h, "Bearer t"); rr.Code != 500 || !strings.Contains(rr.Body.String(), "reload_failed") {
		t.Fatalf("%d %s", rr.Code, rr.Body)
	}
	if s.Generacion() != 1 || respuesta(t, h, cuerpoNonce) != "v1" {
		t.Fatal("no conservó el modelo")
	}
}

// Sin admin_token la ruta no existe.
func TestAdminRecargarSinTokenEs404(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"v1", "v2"}}
	s, h := servidorRecargable(t, a, "")
	rr := recargar(h, "Bearer ")
	if rr.Code != 404 || s.Generacion() != 1 {
		t.Fatalf("%d gen %d", rr.Code, s.Generacion())
	}
}

// Recargas concurrentes con carga: ninguna petición falla, cada respuesta es de un solo modelo y un modelo no se cierra con
// peticiones sobre él.
func TestRecargaConcurrenteConCarga(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"m0", "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10"}, pausa: 200 * time.Microsecond}
	s, h := servidorRecargable(t, a, "")
	stop := make(chan struct{})
	var wg sync.WaitGroup
	var peticiones, malas atomic.Int64
	for g := 0; g < 8; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; ; i++ {
				select {
				case <-stop:
					return
				default:
				}
				cuerpo := cuerpoNonce
				if i%2 == 1 {
					cuerpo = strings.Replace(cuerpoNonce, `"n1"`, `"n`+string(rune('a'+i%7))+`"`, 1)
				}
				rr := post(h, cuerpo)
				var r struct{ Results []Resultado }
				if rr.Code != 200 || json.Unmarshal(rr.Body.Bytes(), &r) != nil || len(r.Results) != 1 {
					malas.Add(1)
				} else if _, ok := r.Results[0].Probs[r.Results[0].Answer]; !ok || !strings.HasPrefix(r.Results[0].Answer, "m") {
					malas.Add(1)
				}
				peticiones.Add(1)
			}
		}()
	}
	for i := 0; i < 10; i++ {
		time.Sleep(3 * time.Millisecond)
		if err := s.Recargar(); err != nil {
			t.Error(err)
		}
	}
	close(stop)
	wg.Wait()
	if malas.Load() != 0 || peticiones.Load() == 0 {
		t.Fatalf("%d peticiones malas de %d", malas.Load(), peticiones.Load())
	}
	if s.Generacion() != 11 || a.cerrados.Load() != 10 || a.cerradoEn.Load() != 0 {
		t.Fatalf("gen %d, cerrados %d, peticiones en vuelo al cerrar %d", s.Generacion(), a.cerrados.Load(), a.cerradoEn.Load())
	}
}

// Una petición en vuelo termina sobre el modelo viejo aunque la recarga ocurra a mitad.
func TestRecargaEnVueloTerminaEnElViejo(t *testing.T) {
	a := &armadorModelos{etiquetas: []string{"v1", "v2"}, pausa: 80 * time.Millisecond}
	s, h := servidorRecargable(t, a, "")
	res := make(chan string, 1)
	go func() { res <- respuesta(t, h, cuerpoNonce) }()
	time.Sleep(20 * time.Millisecond)
	if err := s.Recargar(); err != nil {
		t.Fatal(err)
	}
	if a.cerrados.Load() != 0 {
		t.Fatal("cerró el modelo viejo con una petición en vuelo")
	}
	if g := <-res; g != "v1" {
		t.Fatalf("la petición en vuelo acabó en %s", g)
	}
	time.Sleep(10 * time.Millisecond)
	if a.cerrados.Load() != 1 || respuesta(t, h, cuerpoNonce) != "v2" {
		t.Fatalf("cerrados %d", a.cerrados.Load())
	}
}
