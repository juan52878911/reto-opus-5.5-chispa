package detsrv

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"

	"github.com/juan52878911/chispa/internal/dataset"
	"github.com/juan52878911/chispa/internal/detectors"
)

func TestBankConfigure(t *testing.T) {
	data, models := t.TempDir(), t.TempDir()
	if _, err := dataset.Generate(data, 1); err != nil {
		t.Fatal(err)
	}
	if _, err := detectors.TrainAll(data, models); err != nil {
		t.Fatal(err)
	}
	bank, err := detectors.LoadBank(models)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := bank.Get("spam", detectors.KindWords); !ok {
		t.Fatal("falta spam-chispa-words en el banco")
	}
	if _, ok := bank.Get("spam", detectors.KindRules); !ok {
		t.Fatal("faltan reglas en el banco")
	}
	// servidor en modo banco, sin red real
	srv := newTestServer(bank, 3)
	defer srv.Close()
	c := NewClient(srv.URL)
	ctx := t.Context()

	if err := c.Configure(ctx, "r1", "spam", detectors.KindWords, nil); err != nil {
		t.Fatal(err)
	}
	bi, err := c.Bank(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if bi.Generation != 3 || !bi.Shared || bi.Active != "spam-chispa-words" || len(bi.Models) < 4 {
		t.Fatalf("bank info: %+v", bi)
	}
	for _, m := range bi.Models {
		if strings.HasSuffix(m.ID, "chispa-words") && (m.Bytes == 0 || len(m.SHA256) != 64) {
			t.Fatalf("modelo sin bytes/sha: %+v", m)
		}
	}
	// fuera del banco
	if err := c.Configure(ctx, "r1", "spam", "nope", nil); err == nil {
		t.Fatal("esperaba error fuera del banco")
	}
	// override con cuerpo: copia privada
	raw, err := os.ReadFile(detectors.ModelPath(models, "spam", detectors.KindChar))
	if err != nil {
		t.Fatal(err)
	}
	if err := c.Configure(ctx, "r1", "spam", detectors.KindChar, raw); err != nil {
		t.Fatal(err)
	}
	bi, _ = c.Bank(ctx)
	if bi.Shared || bi.Active != "spam-chispa-char" {
		t.Fatalf("override: %+v", bi)
	}
	// decide funciona
	body, _ := json.Marshal(map[string]any{"items": []map[string]string{{"id": "1", "text": "gana un premio gratis"}}})
	res, err := http.Post(srv.URL+"/decide_batch", "application/json", bytes.NewReader(body))
	if err != nil || res.StatusCode != 200 {
		t.Fatalf("decide: %v %v", err, res)
	}
	res.Body.Close()
}

func newTestServer(bank *detectors.Bank, gen int) *httptest.Server {
	mux, err := buildMux("", "", nil, bank, gen)
	if err != nil {
		panic(err)
	}
	return httptest.NewServer(mux)
}
