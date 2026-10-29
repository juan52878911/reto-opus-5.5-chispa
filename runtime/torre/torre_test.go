package torre

import (
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
	if got := OpcionesConsulta(sc); !reflect.DeepEqual(got, []Opcion{{ID: "alto"}}) {
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
