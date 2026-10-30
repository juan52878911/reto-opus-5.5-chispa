package tok

import "testing"

// En score la mediana de la agregación no depende del orden en que se declaran las opciones.
func TestWAAgregarProbsScorePermutacion(t *testing.T) {
	p := map[string]float64{"1": 0.45, "2": 0.1, "3": 0.45}
	for _, agg := range []string{AggMax, AggMedia} {
		for _, ids := range [][]string{{"1", "2", "3"}, {"3", "1", "2"}, {"2", "3", "1"}, {"3", "2", "1"}} {
			_, ans, _, ok := AgregarProbs("score", ids, []map[string]float64{p, p}, agg, 0.5)
			if !ok || ans != "2" {
				t.Fatalf("%s %v: %q ok=%v, esperaba 2", agg, ids, ans, ok)
			}
		}
	}
	// ids no numéricos: se conserva el orden declarado
	q := map[string]float64{"bajo": 0.6, "medio": 0.3, "alto": 0.1}
	if _, ans, _, _ := AgregarProbs("score", []string{"bajo", "medio", "alto"}, []map[string]float64{q}, AggMedia, 0.5); ans != "bajo" {
		t.Fatalf("declarado: %q", ans)
	}
}
