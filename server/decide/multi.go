package decide

import (
	"encoding/hex"
	"log"
	"math"
	"strings"
	"sync"

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

// ClaveCalibMulti es el sufijo de esquema de las claves de CALIB de multi: «@» y HashEsquema2 (pregunta, kind, opciones con su
// descripción) en hex. Con él, «multi@<hex>» / «multi@<hex>#<id>» (y las de «multi_l2») valen solo para ese esquema: una opción
// «si» o «otro» de un esquema nuevo no hereda el θ ni la a, b de otro entrenado.
func ClaveCalibMulti(p Pregunta) string {
	h := chispa3.HashEsquema2(p.Texto, p.Kind, clavesDe(p.Opciones))
	return "@" + hex.EncodeToString(h[:])
}

// calibPorEsquema dice si CALIB trae alguna clave de multi con esquema (la escribe `chispa train` desde que indexa por esquema).
// Si la trae, las claves sin esquema (ficheros antiguos, sin saber de qué esquema salieron) ya no se aplican.
func calibPorEsquema(c chispa3.Calib) bool {
	for k := range c.Tipos {
		if strings.HasPrefix(k, claveMultiL1+"@") || strings.HasPrefix(k, claveMultiL2+"@") {
			return true
		}
	}
	return false
}

// paramsMulti son (a, b, θ) de una opción en la capa de clave `clave` para el esquema `esq` (ClaveCalibMulti): «<clave><esq>#<id>»
// si existe (θ por opción), si no «<clave><esq>»; sin ellas, en ficheros antiguos (sin ninguna clave con esquema) «<clave>#<id>» y
// «<clave>»; y si tampoco la de «noul» (aproximación sin calibrar para multi), y si tampoco la de por defecto. L2 nunca usa «multi».
func paramsMulti(c chispa3.Calib, clave, esq, id string) chispa3.ParamsTipo {
	p, _ := buscarParamsMulti(c, clave, esq, id)
	return p
}

// buscarParamsMulti es paramsMulti diciendo además si salió de una CALIB de multi (true) o es el respaldo de noul / por defecto.
func buscarParamsMulti(c chispa3.Calib, clave, esq, id string) (chispa3.ParamsTipo, bool) {
	if p, ok := c.Tipos[clave+esq+"#"+id]; ok {
		return p, true
	}
	if p, ok := c.Tipos[clave+esq]; ok {
		return p, true
	}
	if !calibPorEsquema(c) {
		if p, ok := c.Tipos[clave+"#"+id]; ok {
			return p, true
		}
		if p, ok := c.Tipos[clave]; ok {
			return p, true
		}
	}
	return paramsDe(c, "noul"), false
}

// respuestaMulti pone las puntuaciones s de cada opción (en el orden de la pregunta; el coseno de L1 con clave «multi» o el
// MaxSim de L2 con «multi_l2», ver respuestaMulti y respuestaMultiL2) en probabilidades calibradas por opción y en la lista de activas.
// respuestaMulti es la de L1 (y la de L3 si la usa): CALIB «multi».
func respuestaMulti(p Pregunta, s []float64, c chispa3.Calib) Respuesta {
	return respuestaMultiCapa(p, s, c, claveMultiL1)
}

// respuestaMultiL2 es la de L2: CALIB «multi_l2» del esquema. Sin ella L2 no opina en multi (τ de L2 = ∞): el MaxSim de L2 tiene otra
// escala que el coseno de L1, y con la CALIB de noul marcaría activas casi todas las opciones. La cascada escala a la capa siguiente.
func respuestaMultiL2(p Pregunta, s []float64, c chispa3.Calib) Respuesta {
	esq := ClaveCalibMulti(p)
	for _, o := range p.Opciones {
		if _, ok := buscarParamsMulti(c, claveMultiL2, esq, o.ID); ok {
			return respuestaMultiCapa(p, s, c, claveMultiL2)
		}
	}
	avisoSinMultiL2.Do(func() {
		log.Printf("AVISO: el .chispa no trae CALIB multi_l2 para este esquema de multi: L2 no opina en multi y escala (reentrena con `chispa train` y ejemplos multi, y L2)")
	})
	return Respuesta{}
}

var avisoSinMultiL2 sync.Once

func respuestaMultiCapa(p Pregunta, s []float64, c chispa3.Calib, clave string) Respuesta {
	esq := ClaveCalibMulti(p)
	pr := make([]float64, len(p.Opciones))
	th := make([]float64, len(p.Opciones))
	for i, o := range p.Opciones {
		prm := paramsMulti(c, clave, esq, o.ID)
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
