package tok

import (
	"reflect"
	"slices"
	"testing"
)

func TestNivelesScore(t *testing.T) {
	validos := []struct{ in, want []string }{
		{[]string{"1"}, []string{"1"}},
		{[]string{"3", "1", "2"}, []string{"1", "2", "3"}},
		{[]string{"10", "2", "1", "3", "4", "5", "6", "7", "8", "9"}, []string{"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}},
	}
	for _, c := range validos {
		in := slices.Clone(c.in)
		got, ok := NivelesScore(c.in)
		if !ok || !reflect.DeepEqual(got, c.want) {
			t.Errorf("%v: %v ok=%v, esperaba %v", c.in, got, ok, c.want)
		}
		if !reflect.DeepEqual(in, c.in) {
			t.Errorf("modificó la entrada %v", c.in)
		}
	}
	for _, ids := range [][]string{
		nil, {}, {"bajo", "medio", "alto"}, {"0", "1", "2"}, {"1", "2", "4"}, {"01", "2", "3"}, {"+1", "2"}, {"1", "1"},
		{"1", "2", "x"}, {" 1", "2"}, {"-1", "1"}, {"2", "3"}, {"1", "3"},
	} {
		if got, ok := NivelesScore(ids); ok || got != nil {
			t.Errorf("%v debía ser inválido: %v ok=%v", ids, got, ok)
		}
	}
}
