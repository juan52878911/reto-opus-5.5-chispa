package decide

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func metricasTexto(m *Metricas) string {
	var b bytes.Buffer
	m.Escribe(&b)
	return b.String()
}

func quiero(t *testing.T, m *Metricas, linea string) {
	t.Helper()
	if txt := metricasTexto(m); !strings.Contains(txt, linea+"\n") {
		t.Fatalf("falta %q en /metrics:\n%s", linea, txt)
	}
}

func l2Met(t *testing.T, enc CodificadorTorre) (*L2, *Metricas) {
	t.Helper()
	m := NuevasMetricas()
	l := l2Torres(t, enc, 1024)
	l.UsaMetricas(m)
	return l, m
}

func TestMetricasTorresCalculadasYCache(t *testing.T) {
	l, m := l2Met(t, &codificadorContador{})
	for i := 0; i < 2; i++ {
		if _, err := l.Decidir(context.Background(), preguntaConOpciones(3)); err != nil {
			t.Fatal(err)
		}
	}
	quiero(t, m, "chispa_torres_calculadas_total 3")
	quiero(t, m, "chispa_torres_cache_aciertos_total 3")
	quiero(t, m, "chispa_torre_latencia_segundos_count 3")
	quiero(t, m, "chispa_torres_errores_total 0")
}

type codificadorFalla struct{}

func (codificadorFalla) Torre(string) ([]float32, error) { return nil, errors.New("boom") }

func TestMetricasTorresErrores(t *testing.T) {
	l, m := l2Met(t, codificadorFalla{})
	if _, err := l.Decidir(context.Background(), preguntaConOpciones(2)); err == nil {
		t.Fatal("esperaba error")
	}
	quiero(t, m, "chispa_torres_errores_total 1")
	quiero(t, m, "chispa_torres_calculadas_total 0")
}

// Un codificador que espera a que lo suelten: la segunda petición de la misma torre espera en vuelo.
type codificadorBloqueado struct{ entra, suelta chan struct{} }

func (c codificadorBloqueado) Torre(string) ([]float32, error) {
	c.entra <- struct{}{}
	<-c.suelta
	return []float32{1, 0}, nil
}

func TestMetricasTorresEsperasSingleflight(t *testing.T) {
	enc := codificadorBloqueado{make(chan struct{}, 1), make(chan struct{})}
	l, m := l2Met(t, enc)
	hecho := make(chan struct{}, 2)
	decide := func() {
		l.Decidir(context.Background(), preguntaConOpciones(1+1))
		hecho <- struct{}{}
	}
	go decide()
	<-enc.entra // la primera calcula la torre o0 y se queda dentro
	go decide()
	for deadline := time.Now().Add(5 * time.Second); m.TorresEsperas.Load() == 0; {
		if time.Now().After(deadline) {
			t.Fatal("la segunda petición no esperó en vuelo")
		}
		time.Sleep(time.Millisecond)
	}
	close(enc.suelta)
	<-hecho
	<-hecho
	if m.TorresEsperas.Load() < 1 || m.TorresCalculadas.Load() != 2 {
		t.Fatalf("esperas %d, calculadas %d", m.TorresEsperas.Load(), m.TorresCalculadas.Load())
	}
	quiero(t, m, "chispa_torres_calculadas_total 2")
}

func TestMetricasPresupuestoAgotado(t *testing.T) {
	enc := &codificadorContador{}
	l, m := l2Met(t, enc)
	l.ConMaxTorresNuevas(4)
	if r, err := l.Decidir(context.Background(), preguntaConOpciones(5)); err != nil || r.Conf != 0 {
		t.Fatalf("%+v %v", r, err)
	}
	quiero(t, m, "chispa_torres_presupuesto_agotado_total 1")
	quiero(t, m, "chispa_torres_calculadas_total 4") // las que cabían en el tope quedan en la caché
}

func TestMetricasEsquemaNuevo(t *testing.T) {
	m := NuevasMetricas()
	tau := 0.5
	c, err := NuevaCascadaConTauNuevo([]Capa{{"L2", 0.7}}, []Decisor{decisorNuevo{0.6, true}}, m, &tau)
	if err != nil {
		t.Fatal(err)
	}
	m.FijaTauNuevo(c.tauNuevo)
	c.Decidir(context.Background(), Pregunta{ID: "q", Kind: KindChoice})
	quiero(t, m, "chispa_esquema_nuevo_preguntas_total 1")
	quiero(t, m, "chispa_esquema_nuevo_decididas_total 1")
	quiero(t, m, "chispa_esquema_nuevo_tau 0.5")

	// Sin conf suficiente ni con el τ nuevo: cuenta como pregunta, no como decidida.
	m2 := NuevasMetricas()
	c, _ = NuevaCascadaConTauNuevo([]Capa{{"L2", 0.7}}, []Decisor{decisorNuevo{0.4, true}}, m2, &tau)
	c.Decidir(context.Background(), Pregunta{ID: "q", Kind: KindChoice})
	quiero(t, m2, "chispa_esquema_nuevo_preguntas_total 1")
	quiero(t, m2, "chispa_esquema_nuevo_decididas_total 0")

	// Pregunta conocida: no cuenta, y sin τ nuevo no hay gauge.
	m3 := NuevasMetricas()
	c, _ = NuevaCascada([]Capa{{"L2", 0.7}}, []Decisor{decisorNuevo{0.9, false}}, m3)
	c.Decidir(context.Background(), Pregunta{ID: "q", Kind: KindChoice})
	quiero(t, m3, "chispa_esquema_nuevo_preguntas_total 0")
	if strings.Contains(metricasTexto(m3), "chispa_esquema_nuevo_tau ") {
		t.Fatal("gauge de τ sin τ nuevo")
	}
}

// NuevaCascada entrega las métricas al L2 que lleva dentro una L2c (incrustación).
func TestMetricasCascadaConectaL2c(t *testing.T) {
	m := NuevasMetricas()
	l := l2Torres(t, &codificadorContador{}, 16)
	if _, err := NuevaCascada([]Capa{{"L2", 0.5}}, []Decisor{NuevoL2cCon(l, nil, nil)}, m); err != nil {
		t.Fatal(err)
	}
	if l.met != m {
		t.Fatal("L2 sin métricas")
	}
}

func TestMetricasTimeouts(t *testing.T) {
	casc, err := NuevaCascada([]Capa{{"L2", 0.5}}, []Decisor{decisorNuevo{0.9, false}}, NuevasMetricas())
	if err != nil {
		t.Fatal(err)
	}
	s := NuevoServidor(casc, casc.met, 0)
	cuerpo := `{"questions":[{"id":"q","question":"x","kind":"choice","options":[{"id":"a"},{"id":"b"}]}]}`
	pide := func(ctx context.Context) {
		r := httptest.NewRequest(http.MethodPost, "/v1/decide", strings.NewReader(cuerpo)).WithContext(ctx)
		s.Handler().ServeHTTP(httptest.NewRecorder(), r)
	}
	ctx, cancel := context.WithTimeout(context.Background(), -time.Second)
	defer cancel()
	pide(ctx)
	quiero(t, casc.met, "chispa_timeouts_total 1")
	// Cancelación del cliente: no es timeout.
	ctx2, cancel2 := context.WithCancel(context.Background())
	cancel2()
	pide(ctx2)
	quiero(t, casc.met, "chispa_timeouts_total 1")
	// Petición normal: tampoco.
	pide(context.Background())
	quiero(t, casc.met, "chispa_timeouts_total 1")
}

func TestMetricasNonceEnTexto(t *testing.T) {
	m := NuevasMetricas()
	m.NonceHits.Add(2)
	quiero(t, m, "chispa_cache_nonce_aciertos_total 2")
}
