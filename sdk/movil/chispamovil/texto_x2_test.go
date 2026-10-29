package chispamovil

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"

	"chispa/runtime/torre"
)

// Los textos de torre del motor móvil son los de texto_opcion/texto_consulta de model/l2/modelo.py.
func TestTextosTorreL2ParidadPython(t *testing.T) {
	b, err := os.ReadFile("../../../runtime/torre/testdata/paridad_textos.json")
	if err != nil {
		t.Fatal(err)
	}
	var cs []struct {
		Kind     string `json:"kind"`
		Pregunta string `json:"pregunta"`
		Opciones []struct {
			ID          string `json:"id"`
			Description string `json:"description"`
		} `json:"opciones"`
		Torre []string `json:"torre"`
	}
	if err := json.Unmarshal(b, &cs); err != nil || len(cs) < 20 {
		t.Fatalf("paridad: %d casos, %v", len(cs), err)
	}
	for i, k := range cs {
		p := pregunta{Texto: k.Pregunta, Kind: k.Kind}
		for _, o := range k.Opciones {
			p.Opciones = append(p.Opciones, opcion{ID: o.ID, Description: o.Description})
		}
		if got := torre.Textos(aTorre(p)); !reflect.DeepEqual(got, k.Torre) {
			t.Errorf("caso %d (%s): Go %q, Python %q", i, k.Kind, got, k.Torre)
		}
	}
}
