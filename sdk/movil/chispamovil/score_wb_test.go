package chispamovil

import (
	"encoding/json"
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

// score con ids que no son 1..K: ninguna capa opina (L0, L1, agregación, L2, torre de consulta) y lo dice.
func TestScoreWBNoCanonicosNoOpinaPorCapa(t *testing.T) {
	for _, ids := range [][]string{{"bajo", "medio", "alto"}, {"0", "1", "2"}, {"01", "2", "3"}, {"+1", "2", "3"}, {"1", "2", "4"}, {"1", "1", "2"}} {
		p := pregunta{Kind: "score", Opciones: opsIDs(ids...)}
		probs := map[string]float64{ids[0]: 0.1, ids[1]: 0.5, ids[2]: 0.4}
		malo := func(capa string, r respuesta) {
			if r.Opina || r.Conf != 0 || r.Answer != "" || r.EscalateReason != "score_ids_no_validos" {
				t.Errorf("%s con %v debería no opinar: %+v", capa, ids, r)
			}
		}
		malo("L0", ordinal(p, respuesta{Ok: true, Opina: true, Answer: ids[1], Conf: 0.5, Probs: probs}))
		malo("L1", puntuarNiveles(p, []float64{0.1, 0.5, 0.4}, 1))
		malo("agregación", agregarVentanas(p, []respuesta{{Ok: true, Opina: true, Probs: probs}, {Ok: true, Opina: true, Probs: probs}}, "mean", 0.5))
		if got := idsOrdenados(p); len(got) != 0 {
			t.Errorf("idsOrdenados con %v: %v", ids, got)
		}
		c := &Chispa{calib: calibNiveles(3), tieneL2: true}
		malo("L2", c.score(p, 1))
		pj, _ := json.Marshal(p)
		if c.TorresL2(string(pj)) || c.TextosTorreL2(string(pj)) != "[]" || c.InstalarTorresL2(string(pj), make([]byte, 4*3), 1) {
			t.Errorf("torre de consulta con %v debería no existir", ids)
		}
	}
}

// La respuesta de las capas lleva escalate_reason solo cuando ids no válidos; con 1..K opina y no lo lleva.
func TestScoreWBValidoOpinaSinMotivo(t *testing.T) {
	p := pregunta{Kind: "score", Opciones: opsIDs("2", "1", "3")}
	r := puntuarNiveles(p, []float64{math.Log(0.5), math.Log(0.1), math.Log(0.4)}, 1)
	if !r.Opina || r.Answer != "2" || r.EscalateReason != "" {
		t.Errorf("%+v", r)
	}
}
