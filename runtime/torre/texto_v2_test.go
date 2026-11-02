package torre

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"
)

type casoV2 struct {
	Kind     string   `json:"kind"`
	Pregunta string   `json:"pregunta"`
	Opciones []Opcion `json:"opciones"`
	V1       []string `json:"v1"`
	V2       []string `json:"v2_sin_id"`
}

// Paridad con el generador de Python (server/decide/testdata/gen_texto_torre_v2.py): v1 y v2 de los mismos casos.
func TestParidadTextoV2(t *testing.T) {
	var cs []casoV2
	leerJSON(t, "../../server/decide/testdata/texto_torre_v2.json", &cs)
	if len(cs) < 15 {
		t.Fatalf("solo %d casos", len(cs))
	}
	for i, c := range cs {
		k := c.Kind
		if k == "multi" {
			k = KindChoice
		}
		p := Pregunta{Texto: c.Pregunta, Kind: k, Opciones: c.Opciones}
		for ver, want := range map[string][]string{"v1": c.V1, "v2_sin_id": c.V2} {
			if got := Textos(ver, p); !reflect.DeepEqual(got, want) {
				t.Errorf("caso %d (%s, %s): Go %q, Python %q", i, c.Kind, ver, got, want)
			}
		}
		if got := Textos("", p); !reflect.DeepEqual(got, c.V1) {
			t.Errorf("caso %d: versión vacía debe ser v1: %q", i, got)
		}
	}
}

func TestTextoTorreVersiones(t *testing.T) {
	casos := []struct{ ver, id, desc, want string }{
		{"v1", "a", "x", "passage: q · a · x"},
		{"v1", "a", "", "passage: q · a · "},
		{"v2_sin_id", "a", "x", "passage: q · x"},
		{"v2_sin_id", "a", "  x  ", "passage: q ·   x  "},
		{"v2_sin_id", "a", "", "passage: q · a · "},
		{"v2_sin_id", "a", " \t", "passage: q · a ·  \t"},
	}
	for _, c := range casos {
		if got := TextoTorre(c.ver, "q", c.id, c.desc); got != c.want {
			t.Errorf("%s %q %q: %q, quería %q", c.ver, c.id, c.desc, got, c.want)
		}
	}
	// La torre solo cambia si hay descripción.
	if TextoTorre("v1", "q", "a", "") != TextoTorre("v2_sin_id", "q", "a", "") {
		t.Error("sin descripción v1 y v2 deben coincidir")
	}
	if TextoTorre("v1", "q", "a", "d") == TextoTorre("v2_sin_id", "q", "a", "d") {
		t.Error("con descripción v1 y v2 deben diferir")
	}
}

func leerJSON(t testing.TB, ruta string, dst any) {
	b, err := os.ReadFile(ruta)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(b, dst); err != nil {
		t.Fatal(err)
	}
}
