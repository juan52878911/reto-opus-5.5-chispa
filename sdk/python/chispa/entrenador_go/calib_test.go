package main

import (
	"chispa/format/chispa3"
	"math"
	"testing"
)

func TestAjustarPlatt(t *testing.T) {
	var s []float64
	var y []int
	for i := 0; i < 200; i++ {
		v := float64(i)/100 - 1 // -1…1
		s = append(s, v)
		// etiqueta determinista con ruido: p = σ(6v-1)
		p := sigmoid(6*v - 1)
		if float64(i%10)/10 < p {
			y = append(y, 1)
		} else {
			y = append(y, 0)
		}
	}
	a, b := ajustarPlatt(s, y)
	if math.Abs(a-6) > 2 || math.Abs(b+1) > 1 {
		t.Fatalf("a=%v b=%v", a, b)
	}
	if th := umbralF1([]float64{.1, .2, .8, .9}, []int{0, 0, 1, 1}); th < 0.25 || th > 0.8 {
		t.Fatalf("θ=%v", th)
	}
}

func TestAjustarT(t *testing.T) {
	// cosenos muy separados con etiquetas correctas → T pequeña; etiquetas ruidosas → T mayor
	sims := [][]float64{{.9, .1}, {.1, .9}, {.8, .2}, {.2, .8}}
	limpio := ajustarT(sims, []int{0, 1, 0, 1})
	ruido := ajustarT(sims, []int{1, 0, 0, 1})
	if limpio >= ruido {
		t.Fatalf("T limpio %v ≥ T ruidoso %v", limpio, ruido)
	}
}

func TestTauEscalate(t *testing.T) {
	conf := []float64{.99, .95, .9, .8, .7, .6}
	ok := []bool{true, true, true, true, false, false}
	tau, hay := tauEscalate(conf, ok, 0.95, 3)
	if !hay || tau != .8 {
		t.Fatalf("τ=%v hay=%v", tau, hay)
	}
	if tau, hay = tauEscalate(conf, []bool{false, false, false, false, false, false}, 0.95, 3); hay || tau != 1 {
		t.Fatalf("sin objetivo: τ=%v hay=%v", tau, hay)
	}
}

func TestCopiarCalibL2UsaTiposL2(t *testing.T) {
	tau2 := 0.6
	c2 := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 0.05}}, TauEscalate: 0.9,
		TiposL2: map[string]chispa3.ParamsTipo{"choice": {T: 0.7}}, TauEscalateL2: &tau2}
	var c chispa3.Calib
	copiarCalibL2(&c, c2)
	if c.TiposL2["choice"].T != 0.7 || c.TauEscalateL2 == nil || *c.TauEscalateL2 != 0.6 {
		t.Fatalf("copió la CALIB de L1: %+v", c)
	}
	c2 = chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 0.3}}, TauEscalate: 0.4}
	c = chispa3.Calib{}
	copiarCalibL2(&c, c2)
	if c.TiposL2["choice"].T != 0.3 || *c.TauEscalateL2 != 0.4 {
		t.Fatalf("sin tipos_l2 debe copiar tipos/tau_escalate: %+v", c)
	}
}
