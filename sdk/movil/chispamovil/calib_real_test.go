package chispamovil

import (
	"math"
	"strconv"
	"testing"

	"chispa/format/chispa3"
)

// Mismo CALIB real (G.8) que server/decide/testdata/calib-score.chispa, leído por ruta relativa al repo.
func TestCalibRealG8CoralAManoIgualQueMovil(t *testing.T) {
	f, err := chispa3.Abrir("../../../server/decide/testdata/calib-score.chispa")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	cal, err := f.Calib()
	if err != nil {
		t.Fatal(err)
	}
	if len(cal.Tipos) != 9 || cal.TauEscalate != 0.7785095572471619 {
		t.Fatalf("CALIB inesperado: %d tipos, tau %v", len(cal.Tipos), cal.TauEscalate)
	}
	c := &Chispa{calib: cal}
	for _, K := range []int{4, 5} {
		clave := "score" + strconv.Itoa(K)
		var ops []opcion
		for i := 1; i <= K; i++ {
			ops = append(ops, opcion{ID: strconv.Itoa(i)})
		}
		for _, s := range []float64{-2, 0, 0.3, 0.5, 0.8, 2} {
			a, b := cal.Tipos[clave].A, cal.Tipos[clave].B
			var sup []float64
			for j := 1; j <= K-1; j++ {
				if j > 1 {
					b += cal.Tipos[clave+"#"+strconv.Itoa(j-1)].A
				}
				sup = append(sup, 1/(1+math.Exp(-(a*s-b))))
			}
			cuenta := 0
			for _, x := range sup {
				if x > 0.5 {
					cuenta++
				}
			}
			got := c.score(pregunta{Kind: "score", Opciones: ops}, s)
			if !got.Ok || len(got.Probs) != K {
				t.Fatalf("K=%d s=%v: el móvil no opinó: %+v", K, s, got)
			}
			if got.Answer != strconv.Itoa(cuenta+1) {
				t.Fatalf("K=%d s=%v: mediana %q ≠ a mano %d", K, s, got.Answer, cuenta+1)
			}
			for i := 1; i <= K; i++ {
				hi, lo := 1.0, 0.0
				if i > 1 {
					hi = sup[i-2]
				}
				if i < K {
					lo = sup[i-1]
				}
				w := math.Max(hi-lo, 0)
				if d := math.Abs(got.Probs[strconv.Itoa(i)] - w); d > 1e-9 {
					t.Fatalf("K=%d s=%v probs[%d]: %v ≠ a mano %v", K, s, i, got.Probs[strconv.Itoa(i)], w)
				}
			}
		}
	}
}
