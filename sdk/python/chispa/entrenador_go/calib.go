package main

import (
	"math"
	"sort"
)

// Cosenos de L1 en la validación, ya calculados: una fila por ejemplo.
// sims[i][j] = coseno(mensaje i, opción j); y[i] = índice de la opción correcta.

// ajustarT elige la temperatura de softmax(coseno/T) que minimiza la NLL (rejilla log, 0,005…1).
func ajustarT(sims [][]float64, y []int) float64 {
	mejor, mejorNLL := 0.05, math.Inf(1)
	for k := 0; k <= 60; k++ {
		T := 0.005 * math.Pow(200, float64(k)/60)
		var nll float64
		for i, s := range sims {
			nll -= math.Log(math.Max(softmax(s, T)[y[i]], 1e-12))
		}
		if nll < mejorNLL {
			mejor, mejorNLL = T, nll
		}
	}
	return mejor
}

func softmax(s []float64, T float64) []float64 {
	mx := math.Inf(-1)
	for _, v := range s {
		mx = math.Max(mx, v)
	}
	out := make([]float64, len(s))
	var z float64
	for i, v := range s {
		out[i] = math.Exp((v - mx) / T)
		z += out[i]
	}
	for i := range out {
		out[i] /= z
	}
	return out
}

// ajustarPlatt ajusta σ(a·s+b) por Newton amortiguado sobre y∈{0,1}.
func ajustarPlatt(s []float64, y []int) (a, b float64) {
	a, b = 4, -2
	for it := 0; it < 200; it++ {
		var ga, gb, haa, hab, hbb float64
		for i, v := range s {
			p := 1 / (1 + math.Exp(-(a*v + b)))
			d := p - float64(y[i])
			w := math.Max(p*(1-p), 1e-6)
			ga += d * v
			gb += d
			haa += w*v*v + 1e-6
			hab += w * v
			hbb += w + 1e-6
		}
		det := haa*hbb - hab*hab
		if math.Abs(det) < 1e-12 {
			break
		}
		da, db := (hbb*ga-hab*gb)/det, (haa*gb-hab*ga)/det
		a, b = a-da, b-db
		if math.Abs(da)+math.Abs(db) < 1e-9 {
			break
		}
	}
	return a, b
}

// umbralF1 devuelve el θ de p(true) que maximiza el F1 macro (rejilla 0,05…0,95).
func umbralF1(p []float64, y []int) float64 {
	mejor, mejorF := 0.5, -1.0
	for k := 1; k < 20; k++ {
		th := float64(k) * 0.05
		var tp, fp, fn, tn float64
		for i, v := range p {
			switch pred := v >= th; {
			case pred && y[i] == 1:
				tp++
			case pred:
				fp++
			case y[i] == 1:
				fn++
			default:
				tn++
			}
		}
		f := (f1(tp, fp, fn) + f1(tn, fn, fp)) / 2
		if f > mejorF+1e-12 {
			mejor, mejorF = th, f
		}
	}
	return mejor
}

func f1(tp, fp, fn float64) float64 {
	if 2*tp+fp+fn == 0 {
		return 0
	}
	return 2 * tp / (2*tp + fp + fn)
}

// tauEscalate es el τ más bajo cuyo subconjunto confiado (conf ≥ τ) alcanza la precisión objetivo con
// al menos minSoporte ejemplos. Si ninguno llega, devuelve 1 (siempre escala) y ok=false.
func tauEscalate(conf []float64, acierto []bool, objetivo float64, minSoporte int) (tau float64, ok bool) {
	idx := make([]int, len(conf))
	for i := range idx {
		idx[i] = i
	}
	sort.Slice(idx, func(a, b int) bool { return conf[idx[a]] > conf[idx[b]] })
	mejor := -1
	var buenos int
	for r, i := range idx {
		if acierto[i] {
			buenos++
		}
		if r+1 >= minSoporte && float64(buenos)/float64(r+1) >= objetivo {
			mejor = r // el prefijo más largo que cumple
		}
	}
	if mejor < 0 {
		return 1, false
	}
	return conf[idx[mejor]], true
}
