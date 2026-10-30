package torre

import (
	"reflect"
	"testing"
)

// H3: con ids no canónicos la opción de consulta de score es la última declarada, no la de mayor Atoi.
func TestXAOpcionesConsultaNoCanonico(t *testing.T) {
	p := Pregunta{Kind: KindScore, Opciones: []Opcion{{ID: "01"}, {ID: "9"}, {ID: "+2"}}}
	// «01» y «+2» no son canónicos: solo «9» cuenta como nivel.
	if got := OpcionesConsulta(p); !reflect.DeepEqual(got, []Opcion{{ID: "9"}}) {
		t.Fatalf("%v", got)
	}
	p = Pregunta{Kind: KindScore, Opciones: []Opcion{{ID: "05"}, {ID: "2"}, {ID: "x"}}}
	if got := OpcionesConsulta(p); !reflect.DeepEqual(got, []Opcion{{ID: "2"}}) {
		t.Fatalf("%v", got)
	}
}
