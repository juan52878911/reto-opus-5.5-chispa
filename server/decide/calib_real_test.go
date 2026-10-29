package decide

import (
	"encoding/json"
	"math"
	"os"
	"sort"
	"strconv"
	"testing"

	"chispa/format/chispa3"
)

type esperadoCalibReal struct {
	TauEscalate float64                       `json:"tau_escalate"`
	ClavesScore map[string]chispa3.ParamsTipo `json:"claves_score"`
	TiposTodos  []string                      `json:"tipos_todos"`
}

// coralAMano calcula P(y>j), probs y mediana con la fórmula de a_calib_chispa, sin pasar por el runtime.
func coralAMano(cal chispa3.Calib, K int, s float64) (sup []float64, probs map[string]float64, mediana string) {
	clave := "score" + strconv.Itoa(K)
	a := cal.Tipos[clave].A
	b := cal.Tipos[clave].B
	for j := 1; j <= K-1; j++ {
		if j > 1 {
			b += cal.Tipos[clave+"#"+strconv.Itoa(j-1)].A
		}
		sup = append(sup, 1/(1+math.Exp(-(a*s-b))))
	}
	probs = map[string]float64{}
	cuenta := 0
	for i := 1; i <= K; i++ {
		hi, lo := 1.0, 0.0
		if i > 1 {
			hi = sup[i-2]
		}
		if i < K {
			lo = sup[i-1]
		}
		probs[strconv.Itoa(i)] = math.Max(hi-lo, 0)
	}
	for _, x := range sup {
		if x > 0.5 {
			cuenta++
		}
	}
	return sup, probs, strconv.Itoa(cuenta + 1)
}

func TestCalibRealG8CoralAManoIgualQueL2Score(t *testing.T) {
	f, err := chispa3.Abrir("testdata/calib-score.chispa")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	cal, err := f.Calib()
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile("testdata/calib-score.esperado.json")
	if err != nil {
		t.Fatal(err)
	}
	var esp esperadoCalibReal
	if err := json.Unmarshal(raw, &esp); err != nil {
		t.Fatal(err)
	}

	var got []string
	for k := range cal.Tipos {
		got = append(got, k)
	}
	sort.Strings(got)
	want := append([]string(nil), esp.TiposTodos...)
	sort.Strings(want)
	if len(got) != len(want) {
		t.Fatalf("tipos de CALIB %v ≠ tipos_todos %v", got, want)
	}
	for i := range got {
		if got[i] != want[i] {
			t.Fatalf("tipos de CALIB %v ≠ tipos_todos %v", got, want)
		}
	}
	if cal.TauEscalate != esp.TauEscalate {
		t.Fatalf("tau_escalate %v ≠ %v", cal.TauEscalate, esp.TauEscalate)
	}
	for k, p := range esp.ClavesScore {
		if cal.Tipos[k] != p {
			t.Fatalf("tipos[%s] %+v ≠ %+v", k, cal.Tipos[k], p)
		}
	}

	l := &L2{calib: cal}
	for _, K := range []int{4, 5} {
		for _, s := range []float64{-2, 0, 0.3, 0.5, 0.8, 2} {
			sup, probs, med := coralAMano(cal, K, s)
			r, err := l.score(preguntaScore(K), s)
			if err != nil || len(r.Probs) != K {
				t.Fatalf("K=%d s=%v: L2 no opinó: %+v %v", K, s, r, err)
			}
			if r.Answer != med {
				t.Fatalf("K=%d s=%v: mediana %q ≠ a mano %q (P(y>j)=%v)", K, s, r.Answer, med, sup)
			}
			for id, v := range probs {
				if math.Abs(r.Probs[id]-v) > 1e-9 {
					t.Fatalf("K=%d s=%v probs[%s]: %v ≠ a mano %v", K, s, id, r.Probs[id], v)
				}
			}
			if math.Abs(r.Conf-probs[med]) > 1e-9 {
				t.Fatalf("K=%d s=%v conf %v ≠ %v", K, s, r.Conf, probs[med])
			}
		}
	}
}
