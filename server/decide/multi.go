package decide

import (
	"math"

	"chispa/format/chispa3"
)

// multi: cada opción es un sí/no independiente sobre «pregunta · opción · descripción». Cada una lleva su sigmoide
// σ(a·s + b) y su umbral θ; la respuesta es la lista de opciones con p ≥ θ y probs trae la p de cada opción (no suman 1).

// Claves de CALIB de multi por capa: la puntuación de L1 (coseno) y la de L2 (MaxSim e5) tienen escalas distintas, así que cada
// capa lleva las suyas: «multi» / «multi#<id>» para L1 y «multi_l2» / «multi_l2#<id>» para L2.
const (
	claveMultiL1 = "multi"
	claveMultiL2 = "multi_l2"
)

// paramsMulti son (a, b, θ) de una opción en la capa de clave `clave`: «<clave>#<id>» si existe (θ por opción), si no «<clave>»,
// y si tampoco la de «noul» (aproximación sin calibrar para multi), y si tampoco la de por defecto. L2 nunca usa «multi» (de L1).
func paramsMulti(c chispa3.Calib, clave, id string) chispa3.ParamsTipo {
	if p, ok := c.Tipos[clave+"#"+id]; ok {
		return p
	}
	if p, ok := c.Tipos[clave]; ok {
		return p
	}
	return paramsDe(c, "noul")
}

// respuestaMulti pone las puntuaciones s de cada opción (en el orden de la pregunta; el coseno de L1 con clave «multi» o el
// MaxSim de L2 con «multi_l2», ver respuestaMulti y respuestaMultiL2) en probabilidades calibradas por opción y en la lista de activas.
// respuestaMulti es la de L1 (y la de L3 si la usa): CALIB «multi».
func respuestaMulti(p Pregunta, s []float64, c chispa3.Calib) Respuesta {
	return respuestaMultiCapa(p, s, c, claveMultiL1)
}

// respuestaMultiL2 es la de L2: CALIB «multi_l2», o la de noul sin ella.
func respuestaMultiL2(p Pregunta, s []float64, c chispa3.Calib) Respuesta {
	return respuestaMultiCapa(p, s, c, claveMultiL2)
}

func respuestaMultiCapa(p Pregunta, s []float64, c chispa3.Calib, clave string) Respuesta {
	pr := make([]float64, len(p.Opciones))
	th := make([]float64, len(p.Opciones))
	for i, o := range p.Opciones {
		prm := paramsMulti(c, clave, o.ID)
		pr[i] = 1 / (1 + math.Exp(-(prm.A*s[i] + prm.B)))
		th[i] = prm.Theta
	}
	return multiDeProbs(p, pr, th)
}

// multiDeProbs arma la Respuesta de multi desde p por opción y θ por opción. Conf es la de la opción más dudosa:
// min de p (si activa) o 1−p (si no), así la capa solo acepta si todas sus decisiones pasan τ.
func multiDeProbs(p Pregunta, pr, th []float64) Respuesta {
	r := Respuesta{Probs: make(map[string]float64, len(pr)), Answers: []string{}, Conf: 1}
	var top float64
	for i, o := range p.Opciones {
		r.Probs[o.ID] = pr[i]
		c := 1 - pr[i]
		if pr[i] >= th[i] {
			c = pr[i]
			r.Answers = append(r.Answers, o.ID)
			if pr[i] > top {
				top, r.Answer = pr[i], o.ID
			}
		}
		r.Conf = math.Min(r.Conf, c)
	}
	if !(r.Conf > 0) { // p exactamente en el extremo: confianza 0 = «sin opinión»; se deja un mínimo para que cuente
		r.Conf = math.SmallestNonzeroFloat64
	}
	return r
}
