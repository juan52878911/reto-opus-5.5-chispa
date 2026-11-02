package decide

import (
	"context"
	"fmt"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

func armarL2Torres(t *testing.T, enc CodificadorTorre, maxNuevas int) *L2 {
	t.Helper()
	cfg := Config{CacheEsquemas: 64, MaxTorresNuevas: maxNuevas}
	mt, err := ArmarDesde(conTorreSeccion(t), NuevoL0(8), &cfg, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{3, 0}}}), ConCodificadorTorre(enc))
	if err != nil {
		t.Fatal(err)
	}
	return mt.L2.(*L2)
}

// El presupuesto de torres nuevas es de la petición entera, no de cada pregunta.
func TestPresupuestoTorresPorPeticion(t *testing.T) {
	enc := &codificadorPorTexto{clave: "zzz"}
	l2 := armarL2Torres(t, enc, 4)
	casc, err := NuevaCascada([]Capa{{"L2", 0.5}}, []Decisor{l2}, NuevasMetricas())
	if err != nil {
		t.Fatal(err)
	}
	h := NuevoServidor(casc, NuevasMetricas(), 0).Handler()
	var qs []string
	for i := 0; i < 5; i++ {
		qs = append(qs, fmt.Sprintf(`{"id":"q%d","kind":"choice","question":"esquema %d","options":[{"id":"a"},{"id":"b"}]}`, i, i))
	}
	rr := post(h, `{"state":"hola","questions":[`+strings.Join(qs, ",")+`]}`)
	if rr.Code != 200 {
		t.Fatalf("%d %s", rr.Code, rr.Body)
	}
	if len(enc.textos) != 4 {
		t.Fatalf("%d torres calculadas en una petición, el tope es 4", len(enc.textos))
	}
	// Otra petición tiene presupuesto propio.
	post(h, `{"state":"hola","questions":[{"id":"x","kind":"choice","question":"otro","options":[{"id":"a"},{"id":"b"}]}]}`)
	if len(enc.textos) != 6 {
		t.Fatalf("la segunda petición debía calcular 2 torres más: %d", len(enc.textos))
	}
}

type codificadorPanico struct {
	mu    sync.Mutex
	veces int
}

func (c *codificadorPanico) Torre(string) ([]float32, error) {
	c.mu.Lock()
	c.veces++
	n := c.veces
	c.mu.Unlock()
	if n == 1 {
		panic("tensor mal formado")
	}
	return []float32{1, 0}, nil
}

func TestSingleflightPanicoLiberaLaClave(t *testing.T) {
	enc := &codificadorPanico{}
	l2 := armarL2Torres(t, enc, 0)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	// El líder entra en pánico: recibe el error (no una torre vacía) y la clave queda libre.
	if _, _, err := l2.torreUnica(ctx, "k", "texto"); err == nil || !strings.Contains(err.Error(), "pánico") {
		t.Fatalf("el líder debía recibir el error de pánico: %v", err)
	}
	if _, _, err := l2.torreUnica(ctx, "k", "texto"); err != nil {
		t.Fatalf("la clave quedó en vuelo: %v", err)
	}
	if enc.veces != 2 {
		t.Fatalf("pasadas %d", enc.veces)
	}
}

// Un seguidor que espera al líder que entra en pánico despierta con error.
func TestSingleflightPanicoDespiertaEsperas(t *testing.T) {
	entra, suelta := make(chan struct{}), make(chan struct{})
	l2 := armarL2Torres(t, codificadorFn(func() ([]float32, error) { close(entra); <-suelta; panic("x") }), 0)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	go func() { defer func() { recover() }(); l2.torreUnica(ctx, "k", "t") }()
	<-entra
	res := make(chan error, 1)
	go func() { _, _, err := l2.torreUnica(ctx, "k", "t"); res <- err }()
	time.Sleep(50 * time.Millisecond)
	close(suelta)
	if err := <-res; err == nil || !strings.Contains(err.Error(), "pánico") {
		t.Fatalf("esperaba error de pánico, llegó %v", err)
	}
}

type codificadorFn func() ([]float32, error)

func (f codificadorFn) Torre(string) ([]float32, error) { return f() }

type lentoLuegoSeguro struct {
	veces int
}

func (*lentoLuegoSeguro) Nombre() string { return "L0" }
func (d *lentoLuegoSeguro) Decidir(ctx context.Context, p Pregunta) (Respuesta, error) {
	d.veces++
	if d.veces == 1 {
		<-ctx.Done()
		return Respuesta{}, ctx.Err()
	}
	return resp("a", 0.99), nil
}

func TestNonceNoGuardaPeticionCancelada(t *testing.T) {
	d := &lentoLuegoSeguro{}
	_, h := servidorFalso(t, d)
	body := `{"state":"hola","questions":[{"id":"1","question":"q","kind":"choice","options":[{"id":"a"},{"id":"b"}],"nonce":"n1"}]}`
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, httptest.NewRequest("POST", "/v1/decide", strings.NewReader(body)).WithContext(ctx))
	if rr.Body.Len() != 0 {
		t.Fatalf("con el cliente ido no se escribe nada: %s", rr.Body)
	}
	r2 := post(h, body)
	if !strings.Contains(r2.Body.String(), `"layer":"L0"`) || strings.Contains(r2.Body.String(), `"escalate":true`) {
		t.Fatalf("el reintento recibió la escalada cacheada: %s", r2.Body)
	}
}

type cuenta struct{ n int }

func (c *cuenta) Nombre() string { return "L0" }
func (c *cuenta) Decidir(context.Context, Pregunta) (Respuesta, error) {
	c.n++
	return Respuesta{}, nil
}

func TestCascadaNoEjecutaConCtxCancelado(t *testing.T) {
	a, b := &cuenta{}, &falso{n: "L1", r: resp("a", 0.1)}
	c, _ := cascadaFalsa(t, []float64{0.8, 0.8}, a, b)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	r := c.Decidir(ctx, Pregunta{ID: "1", Kind: KindChoice, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}})
	if a.n != 0 || b.veces.Load() != 0 || !r.Escalate || !r.Incompleto {
		t.Fatalf("capas ejecutadas con ctx cancelado: %d %d %+v", a.n, b.veces.Load(), r)
	}
}
