package attacks

import (
	"context"
	"math/rand/v2"
	"strings"
	"testing"
)

const sample = "hola gana dinero gratis ahora porque es urgente por favor"

func rng() *rand.Rand { return rand.New(rand.NewPCG(1, 2)) }

func isSubseq(orig, mut []string) bool {
	j := 0
	for _, w := range mut {
		if j < len(orig) && w == orig[j] {
			j++
		}
	}
	return j == len(orig)
}

func TestOpsDeterministicAndChange(t *testing.T) {
	for _, op := range Ops() {
		changed := false
		for seed := uint64(0); seed < 20; seed++ {
			a, _ := op.Apply(rand.New(rand.NewPCG(seed, 9)), sample)
			b, p := op.Apply(rand.New(rand.NewPCG(seed, 9)), sample)
			if a != b {
				t.Fatalf("%s not deterministic", op.Name)
			}
			if p == nil {
				t.Fatalf("%s no params", op.Name)
			}
			if a != sample {
				changed = true
			}
		}
		if !changed {
			t.Errorf("%s never changed text", op.Name)
		}
	}
}

func TestInsertOnlyKeepWords(t *testing.T) {
	orig := strings.Fields(sample)
	for _, name := range []string{"benign_pad", "emoji_inject"} {
		for _, op := range Ops() {
			if op.Name != name {
				continue
			}
			for seed := uint64(0); seed < 50; seed++ {
				out, _ := op.Apply(rand.New(rand.NewPCG(seed, 3)), sample)
				if !isSubseq(orig, strings.Fields(out)) {
					t.Fatalf("%s removed words: %q", name, out)
				}
			}
		}
	}
}

func TestMutate(t *testing.T) {
	out, ops := Mutate(rng(), sample, 3)
	out2, _ := Mutate(rng(), sample, 3)
	if out != out2 || len(ops) != 3 || out == sample {
		t.Fatalf("bad mutate: %q %v", out, ops)
	}
}

func TestSearchFindsFragment(t *testing.T) {
	pool := []string{"jajaja", "saludos", "BUENO", "ok", "gracias"}
	score := func(_ context.Context, texts []string) ([]float64, error) {
		out := make([]float64, len(texts))
		for i, s := range texts {
			out[i] = 0.9
			if strings.Contains(s, "BUENO") {
				out[i] = 0.2
			}
		}
		return out, nil
	}
	out, ops, it, sc, err := Search(context.Background(), rng(), sample, pool, 20, 8, score)
	if err != nil || !strings.Contains(out, "BUENO") || sc >= 0.5 || len(ops) != 1 || it < 1 {
		t.Fatalf("search failed: %q %v %d %v %v", out, ops, it, sc, err)
	}
	if !isSubseq(strings.Fields(sample), strings.Fields(out)) {
		t.Fatal("search removed words")
	}
}
