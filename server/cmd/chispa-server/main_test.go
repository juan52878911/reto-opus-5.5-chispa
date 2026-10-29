package main

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
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

func TestImprimirHashClave(t *testing.T) {
	var out strings.Builder
	if err := imprimirHashClave(strings.NewReader("abc\n"), &out); err != nil {
		t.Fatal(err)
	}
	// sha256("abc"), vector estándar.
	if want := "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad\n"; out.String() != want {
		t.Fatalf("%q", out.String())
	}
	if err := imprimirHashClave(strings.NewReader("\n"), &out); err == nil {
		t.Fatal("clave vacía debía fallar")
	}
}
