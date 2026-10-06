// Package detectors define la interfaz común de un detector de la arena y sus
// implementaciones: tres variantes de Chispa y una de reglas.
package detectors

import (
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/juan52878911/chispa/contracts"
	"github.com/juan52878911/chispa/internal/dataset"
	"github.com/juan52878911/kindling/pkg/chispa"
)

// Tipos de detector. Los tres de Chispa difieren a propósito (rasgos,
// subconjunto y semilla) para que sus errores no estén del todo correlacionados.
const (
	KindWords = "chispa-words"
	KindChar  = "chispa-char"
	KindSub   = "chispa-sub"
	KindRules = "rules"
)

var Kinds = []string{KindWords, KindChar, KindSub, KindRules}

// Decision es la respuesta de un detector a un texto.
type Decision struct {
	Label    string
	Probs    map[string]float64
	Escalate bool
}

type Detector interface {
	Version() string
	Decide(text string) Decision
}

// ID es el identificador estable de un detector: "<dim>-<kind>".
func ID(dim, kind string) string { return dim + "-" + kind }

// ModelPath es dónde vive el .chispa de un detector.
func ModelPath(modelsDir, dim, kind string) string {
	return filepath.Join(modelsDir, ID(dim, kind)+".chispa")
}

// Load construye el detector de (dim, kind).
func Load(modelsDir, dim, kind string) (Detector, error) {
	labels, ok := contracts.Dimensions[dim]
	if !ok {
		return nil, fmt.Errorf("dimensión desconocida %q", dim)
	}
	if kind == KindRules {
		return newRules(dim, labels), nil
	}
	path := ModelPath(modelsDir, dim, kind)
	m, err := chispa.LoadFile(path)
	if err != nil {
		return nil, err
	}
	st, _ := os.Stat(path)
	v := kind
	if st != nil {
		v = fmt.Sprintf("%s@%s", kind, st.ModTime().UTC().Format("20060102T150405"))
	}
	return &chispaDet{m: m, labels: labels, version: v}, nil
}

// FromBytes construye un detector desde un .chispa en memoria (vacío = reglas).
// Lo usa la microVM: arranca sin modelo y lo recibe por HTTP.
func FromBytes(dim, kind string, model []byte) (Detector, error) {
	labels, ok := contracts.Dimensions[dim]
	if !ok {
		return nil, fmt.Errorf("dimensión desconocida %q", dim)
	}
	if kind == KindRules {
		return newRules(dim, labels), nil
	}
	m, err := chispa.Unmarshal(model)
	if err != nil {
		return nil, err
	}
	return &chispaDet{m: m, labels: labels, version: fmt.Sprintf("%s@%x", kind, m.SpecHash&0xffffff)}, nil
}

type chispaDet struct {
	m       *chispa.Model
	labels  []string
	version string
}

func (c *chispaDet) Version() string { return c.version }

func (c *chispaDet) Decide(text string) Decision {
	p := c.m.PredictFull(chispa.Input{Text: text, Fields: dataset.Fields(text)}, 0)
	probs := make(map[string]float64, len(c.labels))
	for _, cp := range p.Probs {
		probs[cp.Label] = cp.Prob
	}
	// Binario: puede venir solo una fila; el resto es el complemento.
	if len(probs) < len(c.labels) {
		rest := 1.0
		for _, v := range probs {
			rest -= v
		}
		missing := 0
		for _, l := range c.labels {
			if _, ok := probs[l]; !ok {
				missing++
			}
		}
		for _, l := range c.labels {
			if _, ok := probs[l]; !ok {
				probs[l] = math.Max(rest, 0) / float64(missing)
			}
		}
	}
	return Decision{Label: p.Label, Probs: probs, Escalate: !p.Confident}
}

// rules es el detector sin aprendizaje: listas de patrones por etiqueta. Es
// deliberadamente distinto de Chispa (no hashea, no pondera) para diversificar.
type rules struct {
	labels   []string
	fallback string
	pats     map[string][]*regexp.Regexp
}

func (r *rules) Version() string { return "rules@v1" }

func newRules(dim string, labels []string) *rules {
	src := map[string]map[string][]string{
		"spam": {
			"spam": {`https?://`, `www\.`, `gan(a|aste|ador)`, `premio`, `gratis`, `free`, `promo`, `oferta`, `descuento`, `click|clic`, `link`, `bit\.ly`, `inversi[oó]n`, `bitcoin|cripto`, `prestamo|préstamo`, `sorteo`, `reclama`, `\$\s?\d`, `ganancias`, `trabaja desde casa`},
		},
		"injection": {
			"injection": {`ignora`, `ignore`, `olvida (tus|las|todas)`, `instrucciones (anteriores|previas)`, `previous instructions`, `prompt del sistema|system prompt`, `act[uú]a como`, `act as`, `\bdan\b`, `jailbreak`, `sin restricciones`, `modo desarrollador|developer mode`, `revela`, `reveal`, `<\s*/?\s*system`, `\[system\]`, `eres ahora|you are now`},
		},
		"urgencia": {
			"alta":  {`urgente`, `asap`, `ya mismo`, `emergencia`, `ayuda`, `auxilio`, `ahora`, `inmediat`, `r[aá]pido`, `se cay[oó]`, `hospital`, `accidente`, `!!+`},
			"media": {`hoy`, `esta tarde`, `antes de`, `cuando puedas`, `pronto`, `mañana`},
		},
	}[dim]
	r := &rules{labels: labels, pats: map[string][]*regexp.Regexp{}}
	for l, ps := range src {
		for _, p := range ps {
			r.pats[l] = append(r.pats[l], regexp.MustCompile(`(?i)`+p))
		}
	}
	// La etiqueta por defecto es la «inocente»: la última de la lista.
	r.fallback = labels[len(labels)-1]
	return r
}

func (r *rules) Decide(text string) Decision {
	t := strings.ToLower(text)
	hits := map[string]int{}
	total := 0
	for _, l := range r.labels {
		for _, p := range r.pats[l] {
			if p.MatchString(t) {
				hits[l]++
				total++
			}
		}
	}
	best, bestN := r.fallback, 0
	for _, l := range r.labels {
		if hits[l] > bestN {
			best, bestN = l, hits[l]
		}
	}
	// Probabilidad «a ojo»: más coincidencias, más seguridad; nunca 0 ni 1.
	conf := 0.6
	if bestN > 0 {
		conf = math.Min(0.6+0.12*float64(bestN), 0.95)
	}
	probs := map[string]float64{}
	for _, l := range r.labels {
		probs[l] = (1 - conf) / float64(len(r.labels)-1)
	}
	probs[best] = conf
	_ = total
	return Decision{Label: best, Probs: probs, Escalate: false}
}
