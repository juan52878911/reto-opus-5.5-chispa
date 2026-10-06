package detectors

import (
	"bufio"
	"encoding/json"
	"fmt"
	"math/rand/v2"
	"os"
	"path/filepath"

	"github.com/juan52878911/chispa/contracts"
	"github.com/juan52878911/kindling/pkg/chispa"
	"github.com/juan52878911/kindling/pkg/chispa/train"
)

// Info es lo que se guarda junto a cada modelo: models/<id>.json.
type Info struct {
	ID           string  `json:"id"`
	Dimension    string  `json:"dimension"`
	Kind         string  `json:"kind"`
	TrainN       int     `json:"train_n"`
	TestN        int     `json:"test_n"`
	TestAccuracy float64 `json:"test_accuracy"`
	TestCoverage float64 `json:"test_coverage"` // fracción confiada
}

func ReadSplit(dataDir, dim, split string) ([]contracts.Example, error) {
	f, err := os.Open(filepath.Join(dataDir, dim, split+".jsonl"))
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var out []contracts.Example
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		var e contracts.Example
		if err := json.Unmarshal(sc.Bytes(), &e); err != nil {
			return nil, err
		}
		out = append(out, e)
	}
	return out, sc.Err()
}

func toChispa(exs []contracts.Example) []chispa.Example {
	out := make([]chispa.Example, len(exs))
	for i, e := range exs {
		out[i] = chispa.Example{Text: e.Text, Label: e.Label, Fields: e.Fields}
	}
	return out
}

// TrainAll entrena las variantes Chispa de cada dimensión y mide la exactitud
// en test de todas (reglas incluidas).
func TrainAll(dataDir, modelsDir string) ([]Info, error) {
	if err := os.MkdirAll(modelsDir, 0o755); err != nil {
		return nil, err
	}
	var infos []Info
	for _, dim := range contracts.DimensionOrder {
		tr, err := ReadSplit(dataDir, dim, "train")
		if err != nil {
			return nil, err
		}
		va, err := ReadSplit(dataDir, dim, "valid")
		if err != nil {
			return nil, err
		}
		te, err := ReadSplit(dataDir, dim, "test")
		if err != nil {
			return nil, err
		}
		for _, kind := range Kinds {
			n := len(tr)
			if kind != KindRules {
				m, used, err := TrainKind(kind, tr, va)
				if err != nil {
					return nil, fmt.Errorf("%s: %w", ID(dim, kind), err)
				}
				n = used
				if err := m.Save(ModelPath(modelsDir, dim, kind)); err != nil {
					return nil, err
				}
			}
			d, err := Load(modelsDir, dim, kind)
			if err != nil {
				return nil, err
			}
			ok, conf := 0, 0
			for _, e := range te {
				dec := d.Decide(e.Text)
				if dec.Label == e.Label {
					ok++
				}
				if !dec.Escalate {
					conf++
				}
			}
			info := Info{ID: ID(dim, kind), Dimension: dim, Kind: kind, TrainN: n, TestN: len(te)}
			if len(te) > 0 {
				info.TestAccuracy = float64(ok) / float64(len(te))
				info.TestCoverage = float64(conf) / float64(len(te))
			}
			b, _ := json.MarshalIndent(info, "", "  ")
			if err := os.WriteFile(filepath.Join(modelsDir, info.ID+".json"), b, 0o644); err != nil {
				return nil, err
			}
			infos = append(infos, info)
		}
	}
	return infos, nil
}

// ReadInfo lee models/<id>.json; si no existe devuelve un Info vacío.
func ReadInfo(modelsDir, id string) Info {
	var i Info
	b, err := os.ReadFile(filepath.Join(modelsDir, id+".json"))
	if err == nil {
		_ = json.Unmarshal(b, &i)
	}
	return i
}

// TrainKind entrena la variante kind. Devuelve el modelo y cuántos ejemplos
// usó. Las variantes difieren a propósito (rasgos, subconjunto y semilla).
func TrainKind(kind string, tr, va []contracts.Example) (*chispa.Model, int, error) {
	cfg := train.Config{Spec: chispa.DefaultSpec(), Seed: 1}
	trEx := tr
	switch kind {
	case KindChar:
		cfg.Spec.Bigrams = false
		cfg.Spec.CharMin, cfg.Spec.CharMax = 3, 5
		cfg.Seed = 7
	case KindSub:
		// DECISIÓN — 60% del train y otra semilla: diversidad barata.
		r := rand.New(rand.NewPCG(2, 2))
		trEx = nil
		for _, e := range tr {
			if r.Float64() < 0.6 {
				trEx = append(trEx, e)
			}
		}
		cfg.Spec.Fields = false
		cfg.Seed = 2
	}
	res, err := train.Train(toChispa(trEx), toChispa(va), cfg)
	if err != nil {
		return nil, 0, err
	}
	return res.Model, len(trEx), nil
}

// SplitTest parte el test por plantilla: por cada etiqueta, la primera
// plantilla (en orden) queda como conjunto limpio y el resto son semillas de
// ataque. Así lo que el bucle de aprendizaje entrena (ataques sobre semillas)
// nunca comparte plantilla con lo que mide la exactitud limpia.
func SplitTest(te []contracts.Example) (seeds, clean []contracts.Example) {
	first := map[string]string{}
	for _, e := range te {
		if t, ok := first[e.Label]; !ok || e.Template < t {
			first[e.Label] = e.Template
		}
	}
	for _, e := range te {
		if e.Template == first[e.Label] {
			clean = append(clean, e)
		} else {
			seeds = append(seeds, e)
		}
	}
	return
}
