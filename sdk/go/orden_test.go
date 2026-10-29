package chispa

import (
	"strings"
	"testing"
)

// Mismo orden que el servidor: largo y separadores de la opción antes que el duplicado.
func TestOrdenValidacionOpcionAntesQueDuplicado(t *testing.T) {
	l := LimitesPorDefecto()
	largo := make([]byte, l.MaxTexto+1)
	for i := range largo {
		largo[i] = 'x'
	}
	casos := map[string]Opcion{
		"invalid_characters": {ID: "a", Description: "d\x1f"},
		"field_too_long":     {ID: "a", Description: string(largo)},
	}
	for want, dup := range casos {
		q := Pregunta{ID: "q1", Kind: KindChoice, Texto: "x", Opciones: []Opcion{{ID: "a"}, dup}}
		if e := l.validarOpciones(q, "q[0]"); e == nil || e.Codigo != want {
			t.Errorf("%s: got %v", want, e)
		}
	}
}

// Mismo orden que el servidor: el nonce largo se rechaza antes que el kind vacío.
func TestOrdenValidacionNonceAntesQueKind(t *testing.T) {
	l := LimitesPorDefecto()
	q := Pregunta{ID: "q1", Texto: "x", Kind: "", Nonce: strings.Repeat("n", l.MaxID+1)}
	if e := l.validar("", []Pregunta{q}); e == nil || e.Codigo != "field_too_long" {
		t.Errorf("got %v", e)
	}
}

// R13: too_many_options sale antes que los errores de la pregunta (kind, id, noul), como el escáner del servidor.
func TestR13TooManyOptionsAntesQueErroresDePregunta(t *testing.T) {
	l := LimitesPorDefecto()
	l.MaxOpciones = 3
	cuatro := []Opcion{{ID: "a"}, {ID: "b"}, {ID: "c"}, {ID: "d"}}
	casos := []struct {
		nombre string
		qs     []Pregunta
		qid    string
	}{
		{"sin kind", []Pregunta{{ID: "1", Texto: "q", Opciones: cuatro}}, "1"},
		{"id vacío antes", []Pregunta{{Kind: KindNoul, Texto: "q"}, {ID: "2", Texto: "q", Kind: KindChoice, Opciones: cuatro}}, "2"},
		{"noul con 4", []Pregunta{{ID: "1", Texto: "q", Kind: KindNoul, Opciones: cuatro}}, "1"},
	}
	for _, c := range casos {
		e := l.validar("", c.qs)
		if e == nil || e.Codigo != "too_many_options" || e.IDPregunta != c.qid {
			t.Errorf("%s: got %+v", c.nombre, e)
		}
	}
}
