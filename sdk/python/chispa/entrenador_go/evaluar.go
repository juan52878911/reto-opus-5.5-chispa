package main

import (
	"fmt"
	"time"

	"chispa/format/chispa3"
	"chispa/runtime/l1"

	"github.com/juan52878911/kindling/pkg/chispa"
)

type InformeEval struct {
	N             int                `json:"n"`
	Secciones     []string           `json:"secciones"`
	L0Acc         float64            `json:"l0_acc"`       // el argmax de L0 sobre todo el test
	L0Cobert      float64            `json:"l0_cobertura"` // fracción con prob ≥ tau_l0
	L0AccConf     float64            `json:"l0_acc_confiada"`
	L1Acc         float64            `json:"l1_acc,omitempty"`
	CascadaAcc    float64            `json:"cascada_acc"`      // L0 → L1 → escala (lo escalado cuenta como fallo)
	CascadaRes    float64            `json:"cascada_resuelta"` // fracción no escalada
	CascadaAccRes float64            `json:"cascada_acc_resuelta"`
	Tiempos       map[string]float64 `json:"tiempos_s"`
	UsPorDecision float64            `json:"us_por_decision_cascada"`
}

// evaluar abre la salida con chispa3 (como lo hace el servidor) y mide en plan.prueba.
func evaluar(p *Plan) (*InformeEval, error) {
	f, err := chispa3.AbrirCon(p.Salida, p.limites())
	if err != nil {
		return nil, err
	}
	defer f.Close()
	if err := f.Verificar(); err != nil {
		return nil, err
	}
	te, err := leerEjemplos(p.Prueba, idsDe(p.Pregunta))
	if err != nil {
		return nil, err
	}
	inf := &InformeEval{N: len(te), Tiempos: map[string]float64{}}
	for _, t := range f.Tipos() {
		inf.Secciones = append(inf.Secciones, t.String())
	}
	calib, err := f.Calib()
	if err != nil {
		return nil, err
	}
	var m0 *chispa.Model
	if f.Tiene(chispa3.L0) {
		if m0, err = f.L0Modelo(); err != nil {
			return nil, err
		}
	}
	var m1 *l1.Modelo
	var ops [][]float32
	if f.Tiene(chispa3.L1) {
		b, err := f.L1()
		if err != nil {
			return nil, err
		}
		if m1, err = l1.Desde(b); err != nil {
			return nil, err
		}
		ops = embebeOpciones(m1, p.Pregunta)
	}
	if m0 == nil {
		return nil, fmt.Errorf("el modelo no tiene L0")
	}
	var ok0, conf0, okConf0, ok1, okC, res, okRes int
	t0 := time.Now()
	for _, e := range te {
		pr := m0.Predict(chispa.Input{Text: e.Text})
		if pr.Label == e.Label {
			ok0++
		}
		resp, acierto := "", false
		if pr.Prob >= p.TauL0 { // como el servidor: confianza calibrada ≥ τ de la capa
			conf0++
			if pr.Label == e.Label {
				okConf0++
			}
			resp = pr.Label
		}
		var l1Lab string
		if m1 != nil && p.Pregunta.Kind != "score" {
			if s := cosenos(m1, ops, e.Text); s != nil {
				var c float64
				if p.Pregunta.Kind == "noul" {
					prm := calib.Tipos["noul"]
					pt := sigmoid(prm.A*s[indiceDe(p.Pregunta, "true")] + prm.B)
					l1Lab, c = "false", 1-pt
					if pt >= prm.Theta {
						l1Lab, c = "true", pt
					}
				} else {
					pb := softmax(s, calib.Tipos["choice"].T)
					k := argmax(pb)
					l1Lab, c = p.Pregunta.Opciones[k].ID, pb[k]
				}
				if l1Lab == e.Label {
					ok1++
				}
				if resp == "" && c >= calib.TauEscalate {
					resp = l1Lab
				}
			}
		}
		if resp != "" {
			res++
			acierto = resp == e.Label
			if acierto {
				okRes++
				okC++
			}
		}
	}
	d := time.Since(t0)
	n := float64(len(te))
	inf.L0Acc, inf.L0Cobert = float64(ok0)/n, float64(conf0)/n
	if conf0 > 0 {
		inf.L0AccConf = float64(okConf0) / float64(conf0)
	}
	inf.L1Acc = float64(ok1) / n
	inf.CascadaAcc, inf.CascadaRes = float64(okC)/n, float64(res)/n
	if res > 0 {
		inf.CascadaAccRes = float64(okRes) / float64(res)
	}
	inf.Tiempos["evaluar"] = d.Seconds()
	inf.UsPorDecision = float64(d.Microseconds()) / n
	return inf, nil
}
