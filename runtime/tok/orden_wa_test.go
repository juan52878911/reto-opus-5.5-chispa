package tok

import (
	"reflect"
	"slices"
	"testing"
)

func TestWAOrdenNivel(t *testing.T) {
	casos := []struct{ in, want []string }{
		{[]string{"10", "2", "1"}, []string{"1", "2", "10"}},
		{[]string{"3", "1", "2"}, []string{"1", "2", "3"}},
		{[]string{"alto", "bajo", "medio"}, []string{"alto", "bajo", "medio"}},
		{[]string{"3", "x", "1"}, []string{"3", "x", "1"}},
		{[]string{"2", "02", "1"}, []string{"2", "02", "1"}}, // «02» no es canónico: orden declarado (H3)
		{[]string{}, []string{}},
	}
	for _, c := range casos {
		in := slices.Clone(c.in)
		if got := OrdenNivel(c.in); !reflect.DeepEqual(got, c.want) {
			t.Errorf("%v: %v, esperaba %v", c.in, got, c.want)
		}
		if !reflect.DeepEqual(in, c.in) {
			t.Errorf("modificó la entrada %v", c.in)
		}
	}
}
