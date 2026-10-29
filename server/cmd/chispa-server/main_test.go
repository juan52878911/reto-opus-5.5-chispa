package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/juan52878911/chispa/server/decide"
)

type lento struct{}

func (lento) Nombre() string { return "L0" }
func (lento) Decidir(context.Context, decide.Pregunta) (decide.Respuesta, error) {
	return decide.Respuesta{}, nil
}

// R4-8: una recarga más lenta que -timeout no responde 503.
func TestAdminFueraDelTimeout(t *testing.T) {
	met := decide.NuevasMetricas()
	armar := func() (*decide.Armado, error) {
		time.Sleep(80 * time.Millisecond)
		c, err := decide.NuevaCascada([]decide.Capa{{Nombre: "L0", Tau: 0.5}}, []decide.Decisor{lento{}}, met)
		return &decide.Armado{Cascada: c}, err
	}
	a, _ := armar()
	srv := decide.NuevoServidorDe(a, met).ConRecarga(armar, "tok")
	h := montarHandler(srv, "tok", 20*time.Millisecond, met)
	r := httptest.NewRequest(http.MethodPost, "/v1/admin/recargar", nil)
	r.Header.Set("Authorization", "Bearer tok")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != 200 {
		t.Fatalf("recarga lenta: %d %s", w.Code, w.Body)
	}
	if srv.Generacion() != 2 {
		t.Fatalf("generación %d", srv.Generacion())
	}
}
