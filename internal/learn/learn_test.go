package learn

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/juan52878911/chispa/contracts"
	"github.com/juan52878911/chispa/internal/dataset"
	"github.com/juan52878911/chispa/internal/detectors"
)

type fakeTeacher struct{ n atomic.Int64 }

func (f *fakeTeacher) Name() string            { return "fake" }
func (f *fakeTeacher) Up(context.Context) bool { return true }
func (f *fakeTeacher) Label(_ context.Context, _ string, l []string, _ string) (string, error) {
	f.n.Add(1)
	return l[0], nil
}

func round(dim, text string, fooled, esc bool) contracts.AttackRound {
	return contracts.AttackRound{Attack: contracts.Attack{Dimension: dim, AttackedText: text, TrueLabel: contracts.Dimensions[dim][0]},
		Swarm: contracts.SwarmResult{Fooled: fooled, Escalated: esc}}
}

func TestOfferNonBlocking(t *testing.T) {
	l := New(Config{BatchSize: 1 << 30, Teacher: &fakeTeacher{}})
	t0 := time.Now()
	for i := 0; i < 200000; i++ {
		l.Offer(round("spam", "x", i%2 == 0, i%3 == 0))
	}
	if d := time.Since(t0); d > 2*time.Second {
		t.Fatalf("Offer lento: %v", d)
	}
	if got := len(l.pending["spam"]); got > 4*l.cfg.BatchSize {
		t.Fatal("cola sin acotar")
	}
	if l.Flow().Escalated == 0 {
		t.Fatal("sin escaladas")
	}
}

func TestPoolCacheAndStats(t *testing.T) {
	var reqs atomic.Int64
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		reqs.Add(1)
		json.NewEncoder(w).Encode(map[string]any{
			"choices": []any{map[string]any{"message": map[string]string{"content": "spam"}}},
			"usage":   map[string]int{"prompt_tokens": 100, "completion_tokens": 2}})
	}))
	defer srv.Close()
	p := NewVONPool([]string{srv.URL}, "m")
	ctx := context.Background()
	if err := p.Prime(ctx); err != nil {
		t.Fatal(err)
	}
	labels := contracts.Dimensions["spam"]
	for _, txt := range []string{"Gana  un PREMIO", "gana un premio", "otro"} {
		got, err := p.Label(ctx, "spam", labels, txt)
		if err != nil || got != "spam" {
			t.Fatal(got, err)
		}
	}
	s := p.Stats()
	if s.Calls != 2 || s.CacheHits != 1 || s.TokensIn != 200 || s.TokensOut != 4 || s.Replicas != 1 {
		t.Fatalf("%+v", s)
	}
	p.AddURL(srv.URL + "/")
	p.RemoveURL(srv.URL)
	if p.Stats().Replicas != 0 {
		t.Fatal("RemoveURL")
	}
}

func TestBatchOracle(t *testing.T) {
	data, models := t.TempDir(), t.TempDir()
	if _, err := dataset.Generate(data, 7); err != nil {
		t.Fatal(err)
	}
	if _, err := detectors.TrainAll(data, models); err != nil {
		t.Fatal(err)
	}
	var got contracts.LearnBatch
	l := New(Config{DataDir: data, ModelsDir: models, BatchSize: 16, Publish: func(b contracts.LearnBatch) { got = b }})
	dim := "spam"
	te, _ := detectors.ReadSplit(data, dim, "test")
	n := 0
	for _, e := range te {
		if n >= 40 {
			break
		}
		a := contracts.Attack{AttackID: e.ID, Dimension: dim, AttackedText: e.Text + " zzq" + e.ID, TrueLabel: e.Label}
		l.Offer(contracts.AttackRound{Attack: a, Swarm: contracts.SwarmResult{Escalated: n%2 == 0, Fooled: n%2 == 1}})
		n++
	}
	deadline := time.Now().Add(60 * time.Second)
	for time.Now().Before(deadline) {
		l.mu.Lock()
		done, run := len(l.batches) > 0, l.running
		l.mu.Unlock()
		if done && !run {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}
	if got.ID == 0 || got.Dimension != dim {
		t.Fatalf("sin lote: %+v", got)
	}
	f := l.Flow()
	if len(f.Efficiency) == 0 || f.Efficiency[0].Generation != 0 || f.Escalated == 0 {
		t.Fatalf("%+v note=%s", f, got.Note)
	}
	t.Logf("batch=%+v points=%d", got, len(f.Efficiency))
}

func TestDedupeCap(t *testing.T) {
	xs := []contracts.Example{{Text: "a"}, {Text: "A "}, {Text: "b"}, {Text: "c"}}
	out := dedupeCap(xs, 2)
	if len(out) != 2 || out[0].Text != "b" || out[1].Text != "c" {
		t.Fatalf("%+v", out)
	}
}
