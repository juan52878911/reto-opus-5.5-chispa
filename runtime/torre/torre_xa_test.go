package torre

import "testing"

// Score: solo hay torre si los ids son exactamente 1..K canónicos (en cualquier orden); si no, no hay opción de consulta.
func TestXAOpcionesConsultaScoreSoloUnoAK(t *testing.T) {
	validos := [][]string{{"1"}, {"1", "2", "3"}, {"3", "1", "2"}, {"2", "1"}}
	for _, ids := range validos {
		ops := make([]Opcion, len(ids))
		for i, id := range ids {
			ops[i] = Opcion{ID: id, Description: "d" + id}
		}
		got := OpcionesConsulta(Pregunta{Kind: KindScore, Opciones: ops})
		k := string(rune('0' + len(ids)))
		if len(got) != 1 || got[0].ID != k || got[0].Description != "d"+k {
			t.Errorf("%v: %v, esperaba el nivel %s", ids, got, k)
		}
	}
	for _, ids := range [][]string{
		{"bajo", "medio", "alto"}, {"0", "1", "2"}, {"1", "2", "4"}, {"01", "2", "3"}, {"+1", "2"}, {"1", "1", "3"}, {"2", "3"},
		{"01", "9", "+2"}, {"05", "2", "x"},
	} {
		ops := make([]Opcion, len(ids))
		for i, id := range ids {
			ops[i] = Opcion{ID: id}
		}
		if got := OpcionesConsulta(Pregunta{Kind: KindScore, Opciones: ops}); got != nil {
			t.Errorf("%v: %v, esperaba ninguna torre", ids, got)
		}
		if got := Textos(Pregunta{Texto: "q", Kind: KindScore, Opciones: ops}); len(got) != 0 {
			t.Errorf("%v: textos %v", ids, got)
		}
	}
}
