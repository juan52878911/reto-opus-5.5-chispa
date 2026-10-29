package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/juan52878911/chispa/server/decide"
)

// Con `l3` en la config, armarModelo monta L3 y lo escalado sale con layer "L3" por /v1/decide; sin ella, escala como antes.
func TestL3DesdeConfig(t *testing.T) {
	llm := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"choices":[{"message":{"content":"{\"probs\":{\"a\":0.1,\"b\":0.9}}"}}]}`)
	}))
	defer llm.Close()
	dir := t.TempDir()
	cfgPath := filepath.Join(dir, "c.json")
	cfg := `{"capas":[{"nombre":"L0","tau":0.8},{"nombre":"L1","tau":0.8},{"nombre":"L2","tau":0.7},{"nombre":"L3","tau":0.6}],"l3":{"url":"` + llm.URL + `/v1","modelo":"m","tau":0.85}}`
	req := `{"state":"hola","questions":[{"id":"q","question":"¿?","kind":"choice","options":[{"id":"a"},{"id":"b"}]}]}`
	servir := func(cfg string) string {
		if err := os.WriteFile(cfgPath, []byte(cfg), 0o600); err != nil {
			t.Fatal(err)
		}
		met := decide.NuevasMetricas()
		a, err := armarModelo(met, cfgPath, "", "")
		if err != nil {
			t.Fatal(err)
		}
		if a.Cerrar != nil {
			defer a.Cerrar()
		}
		s := httptest.NewServer(decide.NuevoServidorDe(a, met).Handler())
		defer s.Close()
		r, err := http.Post(s.URL+"/v1/decide", "application/json", strings.NewReader(req))
		if err != nil {
			t.Fatal(err)
		}
		defer r.Body.Close()
		b, _ := io.ReadAll(r.Body)
		return string(b)
	}
	if b := servir(cfg); !strings.Contains(b, `"layer":"L3"`) || !strings.Contains(b, `"answer":"b"`) {
		t.Fatalf("con l3: %s", b)
	}
	if b := servir(strings.Replace(cfg, `"tau":0.85`, `"tau":0.95`, 1)); !strings.Contains(b, `"layer":"escalar"`) {
		t.Fatalf("τ de l3 por encima de la confianza debe escalar: %s", b)
	}
	if b := servir(`{}`); !strings.Contains(b, `"layer":"escalar"`) {
		t.Fatalf("sin l3 (apagada) debe escalar: %s", b)
	}
}
