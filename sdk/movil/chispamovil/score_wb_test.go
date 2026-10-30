package chispamovil

import (
	"math"
	"testing"
)

// score: L0 (ordinal), L1 (puntuarNiveles) y la agregación de ventanas dan lo mismo con cualquier orden declarado de las opciones.
func TestScoreWBPermutacionPorCapa(t *testing.T) {
	probs := map[string]float64{"1": 0.1, "2": 0.5, "3": 0.4}
	perms := [][]string{{"1", "2", "3"}, {"3", "2", "1"}, {"2", "3", "1"}, {"1", "3", "2"}}
	for _, ids := range perms {
		p := pregunta{Kind: "score", Opciones: opsIDs(ids...)}
		// L0: mediana = nivel 2 (0,1+0,5 ≥ 0,5) con conf 0,5.
		r := ordinal(p, respuesta{Ok: true, Opina: true, Answer: "2", Conf: 0.5, Probs: probs})
		if r.Answer != "2" || r.Conf != 0.5 {
			t.Errorf("L0 orden %v: %+v", ids, r)
		}
		// L1: sims con la misma distribución (T=1 → softmax de ln p).
		sims := make([]float64, len(ids))
		for i, id := range ids {
			sims[i] = math.Log(probs[id])
		}
		r = puntuarNiveles(p, sims, 1)
		if r.Answer != "2" {
			t.Errorf("L1 orden %v: %+v", ids, r)
		}
		// ventanas: los ids que van a AgregarProbs están por nivel.
		got := idsOrdenados(p)
		for i, id := range []string{"1", "2", "3"} {
			if got[i] != id {
				t.Errorf("ids de agregación con orden %v: %v", ids, got)
				break
			}
		}
		rs := []respuesta{{Ok: true, Opina: true, Probs: probs}, {Ok: true, Opina: true, Probs: probs}}
		if a := agregarVentanas(p, rs, "mean", 0.5); a.Ok && a.Answer != "2" {
			t.Errorf("ventanas orden %v: %+v", ids, a)
		}
	}
}
