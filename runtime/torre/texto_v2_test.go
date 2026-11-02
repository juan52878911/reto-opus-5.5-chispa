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
	if len(cs) < 25 {
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

// Descripciones repetidas: en v2 solo esas opciones usan el texto v1 (con id); la comparación es tras strip de Python.
func TestTextoOpcionDescripcionesRepetidas(t *testing.T) {
	ops := []Opcion{{"a", "igual"}, {"b", " \tigual\x1c"}, {"c", "otra"}, {"d", "  "}, {"e", ""}}
	want := []string{"passage: q · a · igual", "passage: q · b ·  \tigual\x1c", "passage: q · otra", "passage: q · d ·   ", "passage: q · e · "}
	got := Textos("v2_sin_id", Pregunta{Texto: "q", Kind: KindChoice, Opciones: ops})
	if !reflect.DeepEqual(got, want) {
		t.Errorf("v2: %q, quería %q", got, want)
	}
	if v1 := Textos("v1", Pregunta{Texto: "q", Kind: KindChoice, Opciones: ops}); v1[2] != "passage: q · c · otra" || v1[0] != want[0] {
		t.Errorf("v1 no cambia: %q", v1)
	}
	if ids := DescripcionesRepetidas(ops); !reflect.DeepEqual(ids, []string{"a", "b"}) {
		t.Errorf("repetidas %q", ids)
	}
	// Tres con dos iguales: la tercera no se toca. Mayúsculas distintas no son repetidas. Vacías repetidas no cuentan.
	if ids := DescripcionesRepetidas([]Opcion{{"a", "x"}, {"b", "y"}, {"c", "x"}}); !reflect.DeepEqual(ids, []string{"a", "c"}) {
		t.Errorf("tres: %q", ids)
	}
	if ids := DescripcionesRepetidas([]Opcion{{"a", "Saldo"}, {"b", "saldo"}, {"c", ""}, {"d", " "}}); len(ids) != 0 {
		t.Errorf("sin repetidas: %q", ids)
	}
	// noul y score: la opción de consulta se compara con el resto de la pregunta.
	if got := Textos("v2_sin_id", Pregunta{Texto: "q", Kind: KindNoul, Opciones: []Opcion{{"false", "no hay"}, {"true", "no hay"}}}); got[0] != "passage: q · true · no hay" {
		t.Errorf("noul: %q", got)
	}
	if got := Textos("v2_sin_id", Pregunta{Texto: "q", Kind: KindScore, Opciones: []Opcion{{"1", "igual"}, {"2", "igual"}, {"3", "alta"}}}); got[0] != "passage: q · alta" {
		t.Errorf("score: %q", got)
	}
}
