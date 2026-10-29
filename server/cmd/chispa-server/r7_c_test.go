package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/juan52878911/chispa/server/decide"
)

func TestR7AdminAddrSeparaRutas(t *testing.T) {
	base := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { io.WriteString(w, "ok:"+r.URL.Path) })
	for _, c := range []struct {
		h    http.Handler
		ruta string
		code int
	}{
		{soloAdmin(base), "/v1/admin/recargar", 200}, {soloAdmin(base), "/v1/decide", 404}, {soloAdmin(base), "/metrics", 404},
		{sinAdmin(base), "/v1/admin/recargar", 404}, {sinAdmin(base), "/v1/decide", 200},
	} {
		w := httptest.NewRecorder()
		c.h.ServeHTTP(w, httptest.NewRequest("POST", c.ruta, nil))
		if w.Code != c.code {
			t.Errorf("%s: %d, quería %d", c.ruta, w.Code, c.code)
		}
	}
}

func TestR7MetricasIncluyenRechazosAdmin(t *testing.T) {
	met := decide.NuevasMetricas()
	h := conMetricasAdmin(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		io.WriteString(w, "chispa_x 1\n")
	}), met)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, httptest.NewRequest("GET", "/metrics", nil))
	if !strings.Contains(w.Body.String(), "chispa_admin_rechazos_total 0") || !strings.HasPrefix(w.Body.String(), "chispa_x 1") {
		t.Fatalf("%q", w.Body.String())
	}
	h401 := conMetricasAdmin(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(401) }), met)
	w = httptest.NewRecorder()
	h401.ServeHTTP(w, httptest.NewRequest("GET", "/metrics", nil))
	if w.Code != 401 || strings.Contains(w.Body.String(), "admin_rechazos") {
		t.Fatalf("%d %q", w.Code, w.Body.String())
	}
}
