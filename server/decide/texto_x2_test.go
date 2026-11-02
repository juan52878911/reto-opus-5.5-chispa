package decide

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"
)

type casoParidad struct {
	Kind     string   `json:"kind"`
	Pregunta string   `json:"pregunta"`
	Opciones []Opcion `json:"opciones"`
	Torre    []string `json:"torre"`
	L1       []string `json:"l1"`
}

func cargarParidad(t *testing.T) []casoParidad {
	b, err := os.ReadFile("../../runtime/torre/testdata/paridad_textos.json")
	if err != nil {
		t.Fatal(err)
	}
	var cs []casoParidad
	if err := json.Unmarshal(b, &cs); err != nil || len(cs) < 20 {
		t.Fatalf("paridad: %d casos, %v", len(cs), err)
	}
	return cs
}

// La torre de L2 (TextosTorre) es idéntica a texto_opcion/texto_consulta de model/l2/modelo.py.
func TestTextosTorreParidadPython(t *testing.T) {
	for i, c := range cargarParidad(t) {
		if got := TextosTorre("v1", Pregunta{Texto: c.Pregunta, Kind: c.Kind, Opciones: c.Opciones}); !reflect.DeepEqual(got, c.Torre) {
			t.Errorf("caso %d (%s): Go %q, Python %q", i, c.Kind, got, c.Torre)
		}
	}
}

// El texto de L1 (prototipos, sin «passage: ») es el que arma chispa train (multi.texto_opcion): «pregunta · opción»
// y la descripción con su separador solo si no está vacía. No sigue a texto_opcion de L2 a propósito: entrenamiento y
// runtime deben armar exactamente el mismo texto.
func TestTextoL1ParidadEntrenamiento(t *testing.T) {
	for i, c := range cargarParidad(t) {
		got := make([]string, len(c.Opciones))
		for j, o := range c.Opciones {
			got[j] = textoOpcion(Pregunta{Texto: c.Pregunta}, o)
		}
		if !reflect.DeepEqual(got, c.L1) {
			t.Errorf("caso %d (%s): Go %q, entrenamiento %q", i, c.Kind, got, c.L1)
		}
	}
}
