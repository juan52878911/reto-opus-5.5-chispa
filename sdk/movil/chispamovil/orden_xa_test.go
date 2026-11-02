package chispamovil

import (
	"reflect"
	"testing"
)

// nivelesScore: solo ids exactamente 1..K canónicos, en cualquier orden; el resultado va por valor numérico.
func TestNivelesScore(t *testing.T) {
	for _, ids := range [][]string{{"3", "1", "2"}, {"1", "2", "3"}, {"2", "1"}} {
		got, ok := nivelesScore(ids)
		if !ok || got[0] != "1" || len(got) != len(ids) {
			t.Errorf("%v: %v %v", ids, got, ok)
		}
	}
	got, ok := nivelesScore([]string{"10", "2", "1", "3", "4", "5", "6", "7", "8", "9"})
	if !ok || !reflect.DeepEqual(got[8:], []string{"9", "10"}) {
		t.Errorf("K=10: %v %v", got, ok)
	}
	for _, ids := range [][]string{
		{"bajo", "medio", "alto"}, {"0", "1", "2"}, {"01", "1", "2"}, {"+1", "1", "2"},
		{"1", "3"}, {"1", "1"}, {"1", "2", "4"}, {"a"}, {"2"}, {"-1", "1"}, {},
	} {
		if got, ok := nivelesScore(ids); ok {
			t.Errorf("%v debería no valer: %v", ids, got)
		}
	}
}

func TestMotivoEscalada(t *testing.T) {
	ok := `{"question":"q","kind":"score","options":[{"id":"1"},{"id":"2"}]}`
	mal := `{"question":"q","kind":"score","options":[{"id":"bajo"},{"id":"alto"}]}`
	casos := []struct {
		q       string
		mejor   float64
		ninguna bool
		want    string
	}{
		{ok, 0.4, false, "baja_confianza"},
		{mal, 0.4, false, "baja_confianza"},
		{ok, 0, true, "sin_opinion"},
		{mal, 0, true, "score_ids_no_validos"},
		{ok, 0, false, ""}, // una capa falló: sin motivo
	}
	for _, c := range casos {
		if got := MotivoEscalada(c.q, c.mejor, c.ninguna); got != c.want {
			t.Errorf("%s %v %v: %q, quería %q", c.q, c.mejor, c.ninguna, got, c.want)
		}
	}
}
