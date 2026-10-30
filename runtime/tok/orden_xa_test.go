package tok

import (
	"reflect"
	"testing"
)

// H3: solo los enteros canónicos cuentan como enteros; «01» y «+1» van al orden declarado.
func TestXAIdsEnterosCanonicos(t *testing.T) {
	for _, ids := range [][]string{{"01", "1", "2"}, {"+1", "1"}, {"1", "02"}, {" 1", "2"}, {"-0", "1"}} {
		if IdsEnteros(ids) {
			t.Errorf("%v no es canónico", ids)
		}
		if got := OrdenNivel(ids); !reflect.DeepEqual(got, ids) {
			t.Errorf("%v: %v, esperaba el orden declarado", ids, got)
		}
	}
	if !IdsEnteros([]string{"-1", "0", "10"}) {
		t.Error("-1, 0 y 10 son canónicos")
	}
}
