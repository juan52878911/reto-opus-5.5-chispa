package chispamovil

import "testing"

// H3: ordenNivel exige ids enteros canónicos; con «01» o «+1» conserva el orden declarado.
func TestXAOrdenNivelNoCanonico(t *testing.T) {
	for _, ids := range [][]string{{"01", "1", "2"}, {"+1", "1", "2"}} {
		var ops []opcion
		for _, id := range ids {
			ops = append(ops, opcion{ID: id})
		}
		got, num := ordenNivel(ops)
		if num {
			t.Errorf("%v no es numérico canónico", ids)
		}
		for i := range ids {
			if got[i].ID != ids[i] {
				t.Errorf("%v reordenado: %v", ids, got)
			}
		}
	}
	got, num := ordenNivel([]opcion{{ID: "10"}, {ID: "2"}})
	if !num || got[0].ID != "2" {
		t.Errorf("canónicos: %v %v", got, num)
	}
}
