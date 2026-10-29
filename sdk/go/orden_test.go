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
