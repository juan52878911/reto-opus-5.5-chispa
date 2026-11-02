package torre

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"
)

func TestTextosYOpciones(t *testing.T) {
	ch := Pregunta{Texto: "q", Kind: KindChoice, Opciones: []Opcion{{ID: "a", Description: "x"}, {ID: "b"}}}
	want := []string{"passage: q · a · x", "passage: q · b · "}
	if got := Textos(ch); !reflect.DeepEqual(got, want) {
		t.Fatalf("choice: %q", got)
	}
	if got := OpcionesConsulta(Pregunta{Kind: KindNoul}); !reflect.DeepEqual(got, []Opcion{{ID: "true"}}) {
		t.Fatalf("noul sin true: %v", got)
	}
	nu := Pregunta{Kind: KindNoul, Opciones: []Opcion{{ID: "false"}, {ID: "true", Description: "d"}}}
	if got := OpcionesConsulta(nu); !reflect.DeepEqual(got, []Opcion{{ID: "true", Description: "d"}}) {
		t.Fatalf("noul: %v", got)
	}
	sc := Pregunta{Kind: KindScore, Opciones: []Opcion{{ID: "1"}, {ID: "3"}, {ID: "2"}}}
	if got := OpcionesConsulta(sc); !reflect.DeepEqual(got, []Opcion{{ID: "3"}}) {
		t.Fatalf("score numérico: %v", got)
	}
	sc = Pregunta{Kind: KindScore, Opciones: []Opcion{{ID: "bajo"}, {ID: "alto"}}}
	if got := OpcionesConsulta(sc); got != nil {
		t.Fatalf("score no numérico: %v", got)
	}
	if OpcionesConsulta(Pregunta{Kind: KindScore}) != nil {
		t.Fatal("score sin opciones")
	}
}

func TestClave(t *testing.T) {
	if Clave("q", Opcion{ID: "a", Description: "x"}) == Clave("q", Opcion{ID: "a", Description: "y"}) {
		t.Fatal("la descripción debe cambiar la clave")
	}
	if Clave("q", Opcion{ID: "a"}) != Clave("q", Opcion{ID: "a"}) {
		t.Fatal("clave no determinista")
	}
}

func TestCuantizar(t *testing.T) {
	v, e := Cuantizar([]float32{0, 0})
	if e != 1 || v[0] != 0 || v[1] != 0 {
		t.Fatalf("cero: %v %v", v, e)
	}
	v, e = Cuantizar([]float32{127, -127, 63.5})
	if e != 1 || int8(v[0]) != 127 || int8(v[1]) != -127 || int8(v[2]) != 64 {
		t.Fatalf("%v %v", v, e)
	}
}

// CasoParidad es un caso de testdata/paridad_textos.json, generado por gen_paridad.py con texto_opcion/texto_consulta de
// model/l2/modelo.py (torre) y texto_opcion de sdk/python/chispa/multi.py (l1, el de chispa train).
type CasoParidad struct {
	Kind     string   `json:"kind"`
	Pregunta string   `json:"pregunta"`
	Opciones []Opcion `json:"opciones"`
	Torre    []string `json:"torre"`
	L1       []string `json:"l1"`
}

// CargarParidad lee el JSON de paridad (ruta relativa a este paquete).
func CargarParidad(t testing.TB, ruta string) []CasoParidad {
	b, err := os.ReadFile(ruta)
	if err != nil {
		t.Fatal(err)
	}
	var cs []CasoParidad
	if err := json.Unmarshal(b, &cs); err != nil {
		t.Fatal(err)
	}
	if len(cs) < 20 {
		t.Fatalf("solo %d casos de paridad", len(cs))
	}
	return cs
}

func TestParidadPython(t *testing.T) {
	for i, c := range CargarParidad(t, "testdata/paridad_textos.json") {
		k := c.Kind
		if k == "multi" {
			k = KindChoice
		}
		if got := Textos(Pregunta{Texto: c.Pregunta, Kind: k, Opciones: c.Opciones}); !reflect.DeepEqual(got, c.Torre) {
			t.Errorf("caso %d (%s): Go %q, Python %q", i, c.Kind, got, c.Torre)
		}
	}
}
