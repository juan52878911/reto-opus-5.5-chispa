// Package swarm calcula el veredicto del enjambre (§5 del PLAN).
package swarm

import (
	"math"

	"github.com/juan52878911/chispa/contracts"
)

// DisagreementGap: si la probabilidad de la etiqueta verdadera difiere más que
// esto entre detectores, el enjambre escala en vez de contestar.
const DisagreementGap = 0.5

const eps = 1e-4

func clamp(p float64) float64 { return math.Min(math.Max(p, eps), 1-eps) }

// Verdict agrega los votos de los detectores que contestaron (Error == "").
// La etiqueta del enjambre sale de la media de log-probabilidades por etiqueta
// (media geométrica normalizada); para dos etiquetas es exactamente la media
// de log-odds de la etiqueta verdadera.
func Verdict(attackID, dim, trueLabel string, votes []contracts.DetectorResult) contracts.SwarmResult {
	labels := contracts.Dimensions[dim]
	out := contracts.SwarmResult{AttackID: attackID, Dimension: dim}
	logp := make([]float64, len(labels))
	minT, maxT := 1.0, 0.0
	for _, v := range votes {
		if v.Error != "" {
			continue
		}
		out.Voters++
		for i, l := range labels {
			logp[i] += math.Log(clamp(v.Probs[l]))
		}
		pt := v.Probs[trueLabel]
		minT, maxT = math.Min(minT, pt), math.Max(maxT, pt)
	}
	if out.Voters == 0 {
		out.Escalated = true
		return out
	}
	// softmax de la media de log-probs
	mx := math.Inf(-1)
	for i := range logp {
		logp[i] /= float64(out.Voters)
		mx = math.Max(mx, logp[i])
	}
	sum := 0.0
	for i := range logp {
		logp[i] = math.Exp(logp[i] - mx)
		sum += logp[i]
	}
	best := 0
	for i := range logp {
		logp[i] /= sum
		if logp[i] > logp[best] {
			best = i
		}
	}
	out.SwarmLabel = labels[best]
	out.SwarmConfidence = logp[best]
	out.Escalated = maxT-minT > DisagreementGap
	out.Fooled = !out.Escalated && out.SwarmLabel != trueLabel
	return out
}
