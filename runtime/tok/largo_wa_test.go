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
	// ids que no son 1..K: sin escala, no hay respuesta
	for _, c := range []struct {
		ids []string
		p   map[string]float64
	}{
		{[]string{"bajo", "medio", "alto"}, map[string]float64{"bajo": 0.6, "medio": 0.3, "alto": 0.1}},
		{[]string{"0", "1", "2"}, map[string]float64{"0": 0.6, "1": 0.3, "2": 0.1}},
		{[]string{"1", "2", "4"}, map[string]float64{"1": 0.6, "2": 0.3, "4": 0.1}},
		{[]string{"01", "2", "3"}, map[string]float64{"01": 0.6, "2": 0.3, "3": 0.1}},
	} {
		for _, n := range []int{1, 2} {
			ps := []map[string]float64{c.p, c.p}[:n]
			if _, ans, conf, ok := AgregarProbs("score", c.ids, ps, AggMedia, 0.5); ok || ans != "" || conf != 0 {
				t.Fatalf("%v (%d ventanas): %q %v ok=%v, esperaba que no opinara", c.ids, n, ans, conf, ok)
			}
		}
	}
}
