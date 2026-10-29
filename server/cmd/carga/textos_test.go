package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestCargarTextos(t *testing.T) {
	p := filepath.Join(t.TempDir(), "t.txt")
	os.WriteFile(p, []byte("hola\n\n# nota\n  quiero \"pagar\"  \n"), 0o644)
	got, err := cargarTextos(p)
	if err != nil || len(got) != 2 || got[1] != `quiero "pagar"` {
		t.Fatalf("got %q err %v", got, err)
	}
	os.WriteFile(p, []byte("\n#x\n"), 0o644)
	if _, err := cargarTextos(p); err == nil {
		t.Fatal("fichero vacío debe fallar")
	}
}

func TestConstruirCuerpos(t *testing.T) {
	c := construirCuerpos([]string{"a \"b\"", "c"}, 3)
	if len(c) != 2 {
		t.Fatal(len(c))
	}
	var r struct {
		State     string            `json:"state"`
		Questions []json.RawMessage `json:"questions"`
	}
	if err := json.Unmarshal(c[0], &r); err != nil || r.State != `a "b"` || len(r.Questions) != 3 {
		t.Fatalf("%v %+v", err, r)
	}
}

func TestFijoConservaCuerpo(t *testing.T) {
	c := construirCuerpos([]string{estadoFijo}, 1)
	want := `{"state":"¿cómo hago el reclamo de la garantía? quiero saber el proceso","questions":[{"id":"q0","question":"¿Qué quiere hacer el cliente?","kind":"choice","options":[{"id":"compra"},{"id":"queja"},{"id":"saludo"},{"id":"soporte"}]}]}`
	if string(c[0]) != want {
		t.Fatalf("cuerpo cambiado:\n%s", c[0])
	}
}

func TestCapasYCSV(t *testing.T) {
	cn := map[string]int{}
	contarCapas([]byte(`{"results":[{"layer":"L1"},{"layer":"L2"},{"layer":"L1"}]}`), cn)
	contarCapas([]byte(`basura`), cn)
	if s := formatoCapas(cn); s != "L1:2,L2:1" {
		t.Fatal(s)
	}
	if s := lineaCSV(100, 2, 2, 10, 1500*time.Microsecond, 9*time.Millisecond); s != "20,10,1.500,9.000,100,2" {
		t.Fatal(s)
	}
}
