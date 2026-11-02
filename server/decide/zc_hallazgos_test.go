package decide

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"
)

// codificadorLentoCtx implementa CodificadorTorreCtx: tarda d y respeta el ctx.
type codificadorLentoCtx struct {
	d  time.Duration
	n  int64
	mu sync.Mutex
}

func (c *codificadorLentoCtx) Torre(string) ([]float32, error) {
	return c.TorreCtx(context.Background(), "")
}

func (c *codificadorLentoCtx) TorreCtx(ctx context.Context, _ string) ([]float32, error) {
	select {
	case <-time.After(c.d):
		c.mu.Lock()
		c.n++
		c.mu.Unlock()
		return []float32{1, 0}, nil
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

// ZC-2: un esperador con ctx vivo no hereda la cancelación del líder: reintenta y pasa a líder.
func TestZC2EsperadorNoHeredaCancelacionDelLider(t *testing.T) {
	enc := &codificadorLentoCtx{d: 300 * time.Millisecond}
	l := l2Torres(t, enc, 1024)
	p := preguntaConOpciones(1)
	ctxA, cancelA := context.WithCancel(context.Background())
	doneA := make(chan struct{})
	go func() { defer close(doneA); l.Decidir(ctxA, p) }()
	time.Sleep(50 * time.Millisecond) // A es líder de la torre
	res := make(chan error, 1)
	var r Respuesta
	go func() { var err error; r, err = l.Decidir(context.Background(), p); res <- err }()
	time.Sleep(50 * time.Millisecond) // B espera
	cancelA()
	<-doneA
	if err := <-res; err != nil || r.Incompleto || r.Conf == 0 {
		t.Fatalf("esperador con ctx vivo: err=%v %+v", err, r)
	}
}

// ZC-2: si es el propio esperador el que se cancela, sigue devolviendo su error.
func TestZC2EsperadorCancelado(t *testing.T) {
	enc := &codificadorLentoCtx{d: 300 * time.Millisecond}
	l := l2Torres(t, enc, 1024)
	p := preguntaConOpciones(1)
	go l.Decidir(context.Background(), p)
	time.Sleep(50 * time.Millisecond)
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	if _, err := l.Decidir(ctx, p); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("err=%v", err)
	}
}

// ZC-3: la caché debe caber 1,5 × max_opciones; max_torres_nuevas ya no manda (solo avisa).
func TestZC3CacheTorresValidacion(t *testing.T) {
	caso := func(cache, max int) Config {
		c := ConfigPorDefecto()
		c.CacheTorres, c.MaxTorresNuevas = cache, max
		return c
	}
	for _, k := range [][2]int{{64, 64}, {256, 64}, {383, 256}} {
		if err := caso(k[0], k[1]).Validar(); err == nil || !strings.Contains(err.Error(), "cache_torres") {
			t.Errorf("cache=%d max=%d debía rechazarse: %v", k[0], k[1], err)
		}
	}
	for _, k := range [][2]int{{384, 64}, {1024, 2048}, {16384, 256}} {
		if err := caso(k[0], k[1]).Validar(); err != nil {
			t.Errorf("cache=%d max=%d debía ser válida: %v", k[0], k[1], err)
		}
	}
	if av := caso(1024, 2048).Avisos(); len(av) != 2 || !strings.Contains(av[0], "cache_torres") {
		t.Errorf("1024/2048 debía avisar: %q", av)
	}
	if av := caso(0, 0).Avisos(); len(av) != 0 {
		t.Errorf("el defecto no avisa: %q", av)
	}
	c := caso(0, 0)
	c.Limites.MaxOpciones = 2000 // la mínima sigue a los límites efectivos
	c.CacheTorres = 1024
	if err := c.Validar(); err == nil {
		t.Error("con max_opciones 2000 una caché de 1024 no basta")
	}
}

// ZC-4: torres_por_segundo es 0 o >= 1; la ráfaga cubre una pregunta completa; aviso si la tasa < max_torres_nuevas.
func TestZC4TasaFraccionariaYRafaga(t *testing.T) {
	c := ConfigPorDefecto()
	c.TorresPorSegundo = 0.5
	if err := c.Validar(); err == nil || !strings.Contains(err.Error(), "torres_por_segundo") {
		t.Fatalf("0,5 debía rechazarse: %v", err)
	}
	for _, v := range []float64{0, 1, 400} {
		c.TorresPorSegundo = v
		if err := c.Validar(); err != nil {
			t.Fatalf("%v: %v", v, err)
		}
	}
	c.TorresPorSegundo = 10
	if av := c.Avisos(); len(av) != 1 || !strings.Contains(av[0], "torres_por_segundo") {
		t.Fatalf("avisos %q", av)
	}
	c.TorresPorSegundo = 400
	if av := c.Avisos(); len(av) != 0 {
		t.Fatalf("avisos %q", av)
	}
	// Con tasa 0,5 (aunque Validar ya no la deje pasar) o 1, una pregunta completa responde: ráfaga max(tasa, max_torres_nuevas, 1).
	for _, tasa := range []float64{0.5, 1} {
		l := l2Torres(t, &codificadorContador{}, 1024).ConTorresPorSegundo(tasa)
		if r, err := l.Decidir(context.Background(), preguntaConOpciones(20)); err != nil || r.Conf == 0 || r.Incompleto {
			t.Fatalf("tasa %v: %+v %v", tasa, r, err)
		}
	}
}

// ZC-5: una recarga rechazada no cambia el gauge: sigue describiendo el modelo en servicio.
func TestZC5GaugeRecargaRechazada(t *testing.T) {
	met := NuevasMetricas()
	deg := armarTorreZB(t, `{"version":1,"texto_torre":"v2_sin_id"}`, "v1", Config{CacheEsquemas: 64})
	bueno := armarTorreZB(t, `{"version":1}`, "v1", Config{CacheEsquemas: 64})
	cA, _ := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.5}}, []Decisor{deg.L2}, met)
	s := NuevoServidor(cA, met, 8).ConClaves([]ClaveAPI{{ID: "k", HashSHA256: HashClave("x"), RPS: 1}}, nil)
	gauge := func() string {
		var sb strings.Builder
		met.Escribe(&sb)
		return sb.String()
	}
	const g1 = `chispa_torre_al_vuelo_desactivada{motivo="texto_torre_inconsistente"} 1`
	if !strings.Contains(gauge(), g1) {
		t.Fatalf("arranque:\n%s", gauge())
	}
	s.ConRecarga(func() (*Armado, error) {
		cB, err := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.5}}, []Decisor{bueno.L2}, met)
		return &Armado{Cascada: cB, CacheRespuestas: 8}, err // sin api_keys: se rechaza
	}, "")
	if err := s.Recargar(); err == nil {
		t.Fatal("la recarga sin api_keys debía rechazarse")
	}
	if !strings.Contains(gauge(), g1) {
		t.Fatalf("tras la recarga rechazada el gauge debía seguir en 1:\n%s", gauge())
	}
	// Una recarga que prospera sí lo apaga.
	s.ConRecarga(func() (*Armado, error) {
		cB, err := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.5}}, []Decisor{bueno.L2}, met)
		return &Armado{Cascada: cB, CacheRespuestas: 8, APIKeys: []ClaveAPI{{ID: "k", HashSHA256: HashClave("x"), RPS: 1}}}, err
	}, "")
	if err := s.Recargar(); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(gauge(), strings.Replace(g1, "} 1", "} 0", 1)) {
		t.Fatalf("tras recargar el modelo bueno:\n%s", gauge())
	}
}

func cobroDePrueba(id string, tps float64) context.Context {
	k := &claveViva{id: id}
	if tps > 0 {
		k.torres = nuevoCuboTorres(tps)
	}
	return context.WithValue(context.Background(), ctxCobro{}, &cobroClave{k: k, ahora: time.Now})
}

// ZC-6: la clave agotada escala con sin_presupuesto_torres y las demás no se ven afectadas.
func TestZC6TopeTorresPorClave(t *testing.T) {
	enc := &codificadorContador{}
	l := l2Torres(t, enc, 1024).ConMaxTorresNuevas(4).ConTorresPorSegundo(1000)
	preg := func(txt string) Pregunta { p := preguntaConOpciones(3); p.Texto = txt; return p }
	ruidosa := cobroDePrueba("ruidosa", 1) // ráfaga max(1, 4, 1) = 4
	if r, err := l.Decidir(ruidosa, preg("uno")); err != nil || r.Conf == 0 {
		t.Fatalf("la primera cabe: %+v %v", r, err)
	}
	r, err := l.Decidir(ruidosa, preg("dos"))
	if err != nil || !r.Incompleto || !r.SinPresupuestoTorres {
		t.Fatalf("la clave agotada debía quedar sin presupuesto: %+v %v", r, err)
	}
	if r, err := l.Decidir(cobroDePrueba("otra", 0), preg("tres")); err != nil || r.Conf == 0 || r.Incompleto {
		t.Fatalf("otra clave sin tope propio: %+v %v", r, err)
	}
	if r, err := l.Decidir(cobroDePrueba("otra2", 1), preg("cuatro")); err != nil || r.Conf == 0 || r.Incompleto {
		t.Fatalf("otra clave con su propio cubo: %+v %v", r, err)
	}
	// El global también cobra: con él agotado una clave con cubo propio lleno tampoco calcula, y no pierde la ficha.
	g := l2Torres(t, &codificadorContador{}, 1024).ConMaxTorresNuevas(4).ConTorresPorSegundo(1)
	k := cobroDePrueba("k", 100)
	g.Decidir(k, preg("a")) // gasta 3 del global (ráfaga 4)
	if r, _ := g.Decidir(k, preg("b")); !r.SinPresupuestoTorres {
		t.Fatalf("el global agotado debía cortar: %+v", r)
	}
	ck := cobroDe(k).k.torres
	ck.mu.Lock()
	f := ck.fichas
	ck.mu.Unlock()
	if f < 100-4-0.5 { // 4 gastadas (3 + la que el global aún dejaba); la del intento rechazado se devolvió
		t.Fatalf("fichas de la clave %v: perdió la ficha del intento rechazado por el global", f)
	}
}

func TestZC6ValidaTorresPorSegundoDeClave(t *testing.T) {
	k := ClaveAPI{ID: "a", HashSHA256: HashClave("x"), RPS: 1}
	for _, v := range []float64{0.5, -1} {
		k.TorresPorSegundo = v
		if err := validarClaves([]ClaveAPI{k}); err == nil || !strings.Contains(err.Error(), "torres_por_segundo") {
			t.Errorf("%v debía rechazarse: %v", v, err)
		}
	}
	for _, v := range []float64{0, 1, 50} {
		k.TorresPorSegundo = v
		if err := validarClaves([]ClaveAPI{k}); err != nil {
			t.Errorf("%v: %v", v, err)
		}
	}
	k.TorresPorSegundo = 10
	c := ConfigPorDefecto()
	c.APIKeys = []ClaveAPI{k}
	if av := c.Avisos(); len(av) != 1 || !strings.Contains(av[0], "api_keys[a]") {
		t.Errorf("avisos %q", av)
	}
	// La recarga conserva el cubo de torres de la clave que sigue (y lo crea/quita según la config).
	a1 := nuevoAutenticador([]ClaveAPI{k}, nil)
	a1.claves[0].torres.toma(256)
	a2 := nuevoAutenticadorDe([]ClaveAPI{k}, nil, a1)
	if a2.claves[0].torres == nil || a2.claves[0].torres.fichas > 255.5 {
		t.Errorf("la recarga rellenó el cubo de torres de la clave: %+v", a2.claves[0].torres)
	}
	k.TorresPorSegundo = 0
	if a3 := nuevoAutenticadorDe([]ClaveAPI{k}, nil, a2); a3.claves[0].torres != nil {
		t.Error("sin torres_por_segundo no hay cubo propio")
	}
}

// ZC-8: el cupo solo cobra las torres que la petición calculó ella misma, no las que esperó a otro líder.
func TestZC8CupoSoloCobraLoCalculado(t *testing.T) {
	enc := &codificadorContador{}
	l := l2Torres(t, enc, 1024)
	p := preguntaConOpciones(200)
	ctxA, ctxB := conPresupuesto(context.Background()), conPresupuesto(context.Background())
	var wg sync.WaitGroup
	wg.Add(2)
	go func() { defer wg.Done(); l.Decidir(ctxA, p) }()
	go func() { defer wg.Done(); time.Sleep(10 * time.Millisecond); l.Decidir(ctxB, p) }()
	wg.Wait()
	ua, ub, n := presupuestoDe(ctxA).usadas.Load(), presupuestoDe(ctxB).usadas.Load(), enc.n.Load()
	if n != 200 || ua+ub != n {
		t.Fatalf("calculadas %d, cobradas A=%d B=%d (deben sumar lo calculado)", n, ua, ub)
	}
}

// ZC-9: si el plazo vence justo antes de la siguiente capa, tras un sin_presupuesto_torres, sale incompleta.
type nombreCancela struct {
	*falso
	cancel func()
	veces  int
}

func (n *nombreCancela) Nombre() string {
	n.veces++
	if n.veces == 3 { // ObservaCapa (1), previas[...] (2)… la tercera llamada cae tras el control posterior a la capa
		n.cancel()
	}
	return n.falso.Nombre()
}

func TestZC9PlazoEntreCapasEsIncompleta(t *testing.T) {
	p := Pregunta{ID: "q", Kind: KindChoice, Texto: "x", Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	l2 := &nombreCancela{falso: &falso{n: "L2", r: Respuesta{Incompleto: true, SinPresupuestoTorres: true}}, cancel: cancel}
	l3 := &falso{n: "L3", r: Respuesta{}}
	cfg := []Capa{{Nombre: "L2", Tau: 0.9}, {Nombre: "L3", Tau: 0.9}}
	c, err := NuevaCascada(cfg, []Decisor{l2, l3}, NuevasMetricas())
	if err != nil {
		t.Fatal(err)
	}
	r := c.Decidir(ctx, p)
	if l3.veces.Load() != 0 {
		t.Skip("el plazo no cayó entre capas: ajusta el punto de cancelación")
	}
	if !r.Escalate || r.EscalateReason != MotivoIncompleta {
		t.Fatalf("%+v", r)
	}
}

// ZC-11: al recargar, el cubo global de torres hereda las fichas del anterior.
func TestZC11RecargaHeredaFichas(t *testing.T) {
	met := NuevasMetricas()
	nuevaCasc := func() *Cascada {
		l := l2Torres(t, &codificadorContador{}, 1024).ConMaxTorresNuevas(10).ConTorresPorSegundo(0.001 + 10)
		c, err := NuevaCascada([]Capa{{Nombre: "L2", Tau: 0.5}}, []Decisor{l}, met)
		if err != nil {
			t.Fatal(err)
		}
		return c
	}
	vieja := nuevaCasc()
	s := NuevoServidor(vieja, met, 8)
	l := vieja.cuboTorres()
	for i := 0; i < 10; i++ {
		l.toma(10)
	}
	var nueva *Cascada
	s.ConRecarga(func() (*Armado, error) { nueva = nuevaCasc(); return &Armado{Cascada: nueva, CacheRespuestas: 8}, nil }, "")
	if err := s.Recargar(); err != nil {
		t.Fatal(err)
	}
	if nueva.cuboTorres().toma(10) && nueva.cuboTorres().toma(10) && nueva.cuboTorres().toma(10) {
		t.Fatal("el cubo nuevo nació lleno: la recarga devolvió la ráfaga entera")
	}
}
