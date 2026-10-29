package decide

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type sesionCerrable struct {
	sesionFalsa
	cierres *atomic.Int64
}

func (s sesionCerrable) Close() error { s.cierres.Add(1); return nil }

type torreCerrable struct {
	codificadorContador
	cierres *atomic.Int64
}

func (c *torreCerrable) Close() error { c.cierres.Add(1); return nil }

// R4-3: Montaje.Cerrar cierra la sesión de L2 y la de torre, una sola vez.
func TestR4CerrarSesionesDelMontaje(t *testing.T) {
	var cierres atomic.Int64
	ses := sesionCerrable{sesionFalsa{[][]float32{{3, 0}}}, &cierres}
	enc := &torreCerrable{cierres: &cierres}
	mt, err := ArmarDesde(conTorreSeccion(t), NuevoL0(8), &Config{Capas: ConfigPorDefecto().Capas}, false, tokFalso{}, ConSesionS(ses), ConCodificadorTorre(enc))
	if err != nil {
		t.Fatal(err)
	}
	if mt.Cerrar == nil {
		t.Fatal("Montaje sin Cerrar")
	}
	mt.Cerrar()
	mt.Cerrar()
	if n := cierres.Load(); n != 2 {
		t.Fatalf("cierres = %d, quiero 2 (L2 y torre, una vez cada una)", n)
	}
}

// R4-5: el contador de la caché de esquemas no baja al recargar.
func TestR4CacheEsquemasAcumulaTrasRecarga(t *testing.T) {
	met := NuevasMetricas()
	mk := func(hits uint64) *Armado {
		l0 := NuevoL0(8)
		l0.Hits.Add(hits)
		c, _ := NuevaCascada([]Capa{{"L0", 0.8}}, []Decisor{&decisorModelo{etiqueta: "x"}}, met)
		return &Armado{Cascada: c, L0: l0}
	}
	n := 0
	s := NuevoServidorDe(mk(100), met).ConRecarga(func() (*Armado, error) { n++; return mk(5), nil }, "")
	quiero(t, met, `chispa_cache_esquemas_total{resultado="acierto"} 100`)
	if err := s.Recargar(); err != nil {
		t.Fatal(err)
	}
	quiero(t, met, `chispa_cache_esquemas_total{resultado="acierto"} 105`)
}

// R4-6: una recarga fallida no toca el gauge del τ de esquema nuevo; una buena sí.
func TestR4RecargaFallidaNoCambiaTau(t *testing.T) {
	met := NuevasMetricas()
	tau, tau2 := 0.5, 0.99
	c, _ := NuevaCascadaConTauNuevo([]Capa{{"L0", 0.8}}, []Decisor{&decisorModelo{etiqueta: "x"}}, met, &tau)
	llamada := 0
	s := NuevoServidorDe(&Armado{Cascada: c}, met).ConRecarga(func() (*Armado, error) {
		llamada++
		_, err := NuevaCascadaConTauNuevo([]Capa{{"L1", 0.8}}, []Decisor{&decisorModelo{etiqueta: "x"}}, met, &tau2)
		if err == nil {
			t.Fatal("la cascada mal ordenada debía fallar")
		}
		return nil, err
	}, "")
	quiero(t, met, "chispa_esquema_nuevo_tau 0.5")
	if s.Recargar() == nil {
		t.Fatal("esperaba error")
	}
	quiero(t, met, "chispa_esquema_nuevo_tau 0.5")
	s.armador = func() (*Armado, error) {
		c2, _ := NuevaCascadaConTauNuevo([]Capa{{"L0", 0.8}}, []Decisor{&decisorModelo{etiqueta: "x"}}, met, &tau2)
		return &Armado{Cascada: c2}, nil
	}
	if err := s.Recargar(); err != nil {
		t.Fatal(err)
	}
	quiero(t, met, "chispa_esquema_nuevo_tau 0.99")
}

// R4-11: el 503 del timeout suma en peticiones_total{codigo="503"}; y si el plazo vence tras el último Decidir no se cuenta 200.
func TestR4Timeout503Cuenta(t *testing.T) {
	met := NuevasMetricas()
	lento := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { <-r.Context().Done() })
	w := httptest.NewRecorder()
	ConTimeoutMet(lento, 10*time.Millisecond, met).ServeHTTP(w, httptest.NewRequest("POST", "/v1/decide", nil))
	if w.Code != 503 {
		t.Fatalf("código %d", w.Code)
	}
	quiero(t, met, `chispa_peticiones_total{codigo="503"} 1`)

	// Decisor que agota el plazo justo al terminar la última pregunta.
	met2 := NuevasMetricas()
	casc, _ := NuevaCascada([]Capa{{"L0", 0.5}}, []Decisor{&decisorModelo{etiqueta: "a", pausa: 60 * time.Millisecond}}, met2)
	s := NuevoServidor(casc, met2, 0)
	h := ConTimeoutMet(s.Handler(), 30*time.Millisecond, met2)
	cuerpo := `{"questions":[{"id":"q","question":"x","kind":"choice","options":[{"id":"a"},{"id":"b"}]}]}`
	w = httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "/v1/decide", strings.NewReader(cuerpo)))
	if w.Code != 503 {
		t.Fatalf("código %d", w.Code)
	}
	quiero(t, met2, `chispa_peticiones_total{codigo="503"} 1`)
	if strings.Contains(metricasTexto(met2), `codigo="200"`) {
		t.Error("el timeout no debe contar 200")
	}
	_ = context.Background
	_ = errors.New
}
