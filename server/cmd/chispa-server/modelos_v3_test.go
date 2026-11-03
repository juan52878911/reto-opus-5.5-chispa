package main

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"github.com/juan52878911/chispa/server/decide"
)

// "modelos" con un v3 solo-L0 funciona en el arranque y en cada recarga (armarModelo es el mismo camino), y max_fichero lo acota.
func TestArmarModeloConModelosV3(t *testing.T) {
	l0b, err := os.ReadFile("../../testdata/intencion.chispa")
	if err != nil {
		t.Fatal(err)
	}
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, []chispa3.Seccion{{Tipo: chispa3.L0, Datos: l0b}}); err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	v3 := filepath.Join(dir, "colocacion.chispa")
	if err := os.WriteFile(v3, buf.Bytes(), 0o644); err != nil {
		t.Fatal(err)
	}
	cfg := filepath.Join(dir, "config.json")
	escribir := func(extra string) {
		js := `{"modelos": ["` + v3 + `"]` + extra + `}`
		if err := os.WriteFile(cfg, []byte(js), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	escribir("")
	for i := 0; i < 2; i++ { // arranque y recarga
		a, err := armarModelo(decide.NuevasMetricas(), cfg, "", "")
		if err != nil {
			t.Fatalf("armado %d: %v", i, err)
		}
		if a.L0.NumModelos() != 1 {
			t.Fatalf("armado %d: %d modelos en L0", i, a.L0.NumModelos())
		}
	}
	escribir(`, "max_fichero": 100`)
	if _, err := armarModelo(decide.NuevasMetricas(), cfg, "", ""); err == nil || !strings.Contains(err.Error(), "max_fichero") {
		t.Fatalf("max_fichero: %v", err)
	}
}
