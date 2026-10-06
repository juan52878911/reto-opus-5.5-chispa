// Package learn es la corrección por lotes: los ataques que engañaron al
// enjambre pasan por un maestro (VON), se reentrena Chispa en sombra con los
// que el maestro confirma, y el modelo nuevo solo se promociona si gana.
package learn

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/juan52878911/chispa/contracts"
	"github.com/juan52878911/chispa/internal/detectors"
	"github.com/juan52878911/chispa/internal/swarm"
)

type Config struct {
	DataDir, ModelsDir string
	BatchSize          int
	Teacher            Teacher // nil = oráculo de la semilla (sin VON)
	Parallel           int     // peticiones concurrentes al maestro
	MaxCleanDrop       float64 // cuánto puede bajar la exactitud limpia: 0.02
	// Promote recarga los detectores de dim tras escribir los modelos nuevos.
	Promote func(dim string) error
	Publish func(contracts.LearnBatch)
}

type Learner struct {
	cfg      Config
	mu       sync.Mutex
	enabled  bool
	running  bool
	pending  map[string][]contracts.Attack
	hardened map[string][]contracts.Example
	gen      int
	batches  []contracts.LearnBatch
	teachUp  bool
}

func New(cfg Config) *Learner {
	if cfg.BatchSize <= 0 {
		cfg.BatchSize = 64
	}
	if cfg.Parallel <= 0 {
		cfg.Parallel = 4
	}
	if cfg.MaxCleanDrop == 0 {
		cfg.MaxCleanDrop = 0.02
	}
	return &Learner{cfg: cfg, enabled: true, pending: map[string][]contracts.Attack{}, hardened: map[string][]contracts.Example{}}
}

func (l *Learner) teacherName() string {
	if l.cfg.Teacher == nil {
		return "oráculo-semilla (sin VON)"
	}
	return l.cfg.Teacher.Name()
}

// Watch comprueba cada pocos segundos si el maestro contesta.
func (l *Learner) Watch(ctx context.Context) {
	for ctx.Err() == nil {
		up := l.cfg.Teacher == nil || l.cfg.Teacher.Up(ctx)
		l.mu.Lock()
		l.teachUp = up
		l.mu.Unlock()
		select {
		case <-ctx.Done():
		case <-time.After(5 * time.Second):
		}
	}
}

// Offer recibe cada ronda; guarda los ataques que engañaron al enjambre.
func (l *Learner) Offer(r contracts.AttackRound) {
	if !r.Swarm.Fooled {
		return
	}
	l.mu.Lock()
	dim := r.Attack.Dimension
	if len(l.pending[dim]) < 4*l.cfg.BatchSize {
		l.pending[dim] = append(l.pending[dim], r.Attack)
	}
	ready := l.enabled && !l.running && len(l.pending[dim]) >= l.cfg.BatchSize
	if ready {
		l.running = true
	}
	l.mu.Unlock()
	if ready {
		go l.run(dim)
	}
}

func (l *Learner) Toggle() bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.enabled = !l.enabled
	return l.enabled
}

// RunNow lanza un lote con la dimensión que más ataques pendientes tenga.
func (l *Learner) RunNow() error {
	l.mu.Lock()
	if l.running {
		l.mu.Unlock()
		return fmt.Errorf("ya hay un lote en marcha")
	}
	best, n := "", 0
	for d, p := range l.pending {
		if len(p) > n {
			best, n = d, len(p)
		}
	}
	if n < 4 {
		l.mu.Unlock()
		return fmt.Errorf("muy pocos ataques exitosos pendientes (%d)", n)
	}
	l.running = true
	l.mu.Unlock()
	go l.run(best)
	return nil
}

func (l *Learner) Snapshot() contracts.Learning {
	l.mu.Lock()
	defer l.mu.Unlock()
	p := 0
	for _, v := range l.pending {
		p = max(p, len(v))
	}
	bs := append([]contracts.LearnBatch(nil), l.batches...)
	if len(bs) > 20 {
		bs = bs[len(bs)-20:]
	}
	return contracts.Learning{Enabled: l.enabled, Teacher: l.teacherName(), TeacherUp: l.teachUp,
		Generation: l.gen, Pending: p, BatchSize: l.cfg.BatchSize, Batches: bs}
}

type pool map[string]detectors.Detector

func loadPool(dir, dim string) (pool, error) {
	p := pool{}
	for _, k := range detectors.Kinds {
		d, err := detectors.Load(dir, dim, k)
		if err != nil {
			return nil, err
		}
		p[k] = d
	}
	return p, nil
}

// swarmEval: ASR del enjambre sobre ataques y exactitud del enjambre en limpio.
func (p pool) swarmEval(dim string, atk []contracts.Attack, clean []contracts.Example) (asr, acc float64) {
	verdict := func(text, truth string) contracts.SwarmResult {
		votes := make([]contracts.DetectorResult, 0, len(p))
		for _, k := range detectors.Kinds {
			d := p[k].Decide(text)
			votes = append(votes, contracts.DetectorResult{PredictedLabel: d.Label, Probs: d.Probs, Escalate: d.Escalate})
		}
		return swarm.Verdict("", dim, truth, votes)
	}
	fooled := 0
	for _, a := range atk {
		if verdict(a.AttackedText, a.TrueLabel).Fooled {
			fooled++
		}
	}
	ok := 0
	for _, e := range clean {
		if verdict(e.Text, e.Label).SwarmLabel == e.Label {
			ok++
		}
	}
	if len(atk) > 0 {
		asr = float64(fooled) / float64(len(atk))
	}
	if len(clean) > 0 {
		acc = float64(ok) / float64(len(clean))
	}
	return
}

func (l *Learner) run(dim string) {
	defer func() { l.mu.Lock(); l.running = false; l.mu.Unlock() }()
	l.mu.Lock()
	n := min(l.cfg.BatchSize, len(l.pending[dim]))
	batch := append([]contracts.Attack(nil), l.pending[dim][:n]...)
	l.pending[dim] = l.pending[dim][n:]
	id := len(l.batches) + 1
	l.mu.Unlock()

	lb := contracts.LearnBatch{ID: id, TS: time.Now().UTC(), Dimension: dim, Size: len(batch), Teacher: l.teacherName()}
	fail := func(note string) {
		lb.Note = note
		l.mu.Lock()
		lb.Generation = l.gen
		l.batches = append(l.batches, lb)
		l.mu.Unlock()
		if l.cfg.Publish != nil {
			l.cfg.Publish(lb)
		}
	}

	// 1. El maestro etiqueta en paralelo.
	t0 := time.Now()
	labels := contracts.Dimensions[dim]
	got := make([]string, len(batch))
	errs := make([]error, len(batch))
	sem := make(chan struct{}, l.cfg.Parallel)
	var wg sync.WaitGroup
	for i, a := range batch {
		if l.cfg.Teacher == nil {
			got[i] = a.TrueLabel
			continue
		}
		wg.Add(1)
		sem <- struct{}{}
		go func(i int, a contracts.Attack) {
			defer wg.Done()
			defer func() { <-sem }()
			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()
			got[i], errs[i] = l.cfg.Teacher.Label(ctx, dim, labels, a.AttackedText)
		}(i, a)
	}
	wg.Wait()
	lb.TeacherMS = float64(time.Since(t0).Milliseconds())
	var kept []contracts.Attack
	nerr := 0
	for i, a := range batch {
		switch {
		case errs[i] != nil:
			nerr++
		case got[i] == a.TrueLabel:
			kept = append(kept, a)
		default:
			lb.Discarded++
		}
	}
	lb.TeacherAgree = len(kept)
	if nerr == len(batch) {
		fail(fmt.Sprintf("el maestro no contestó: %v", firstErr(errs)))
		return
	}
	if len(kept) < 4 {
		fail("muy pocos ataques confirmados por el maestro")
		return
	}

	// 2. Mitad para entrenar, mitad de reto (nunca vista al entrenar).
	var trainAtk, challenge []contracts.Attack
	for i, a := range kept {
		if i%2 == 0 {
			trainAtk = append(trainAtk, a)
		} else {
			challenge = append(challenge, a)
		}
	}
	tr, err1 := detectors.ReadSplit(l.cfg.DataDir, dim, "train")
	va, err2 := detectors.ReadSplit(l.cfg.DataDir, dim, "valid")
	te, err3 := detectors.ReadSplit(l.cfg.DataDir, dim, "test")
	if err := firstErr([]error{err1, err2, err3}); err != nil {
		fail(err.Error())
		return
	}
	_, clean := detectors.SplitTest(te)
	cur, err := loadPool(l.cfg.ModelsDir, dim)
	if err != nil {
		fail(err.Error())
		return
	}
	lb.ASRBefore, lb.CleanBefore = cur.swarmEval(dim, challenge, clean)

	// 3. Reentreno en sombra con lo acumulado + este lote.
	t1 := time.Now()
	l.mu.Lock()
	hard := append([]contracts.Example(nil), l.hardened[dim]...)
	gen := l.gen + 1
	l.mu.Unlock()
	for _, a := range trainAtk {
		hard = append(hard, contracts.Example{ID: a.AttackID, Text: a.AttackedText, Label: a.TrueLabel, Template: "attack/" + a.SeedID})
	}
	shadow := filepath.Join(l.cfg.ModelsDir, "shadow", fmt.Sprintf("gen-%d-%s", gen, dim))
	if err := os.MkdirAll(shadow, 0o755); err != nil {
		fail(err.Error())
		return
	}
	trainSet := append(append([]contracts.Example(nil), tr...), hard...)
	for _, k := range detectors.Kinds {
		if k == detectors.KindRules {
			continue
		}
		m, _, err := detectors.TrainKind(k, trainSet, va)
		if err != nil {
			fail(err.Error())
			return
		}
		if err := m.Save(detectors.ModelPath(shadow, dim, k)); err != nil {
			fail(err.Error())
			return
		}
	}
	lb.TrainMS = float64(time.Since(t1).Milliseconds())
	sh, err := loadPool(shadow, dim)
	if err != nil {
		fail(err.Error())
		return
	}
	lb.ASRAfter, lb.CleanAfter = sh.swarmEval(dim, challenge, clean)

	// 4. Promoción solo si gana en el reto sin estropear lo limpio.
	lb.Promoted = lb.ASRAfter < lb.ASRBefore && lb.CleanAfter >= lb.CleanBefore-l.cfg.MaxCleanDrop
	if lb.Promoted {
		for _, k := range detectors.Kinds {
			if k == detectors.KindRules {
				continue
			}
			dst := detectors.ModelPath(l.cfg.ModelsDir, dim, k)
			b, err := os.ReadFile(detectors.ModelPath(shadow, dim, k))
			if err == nil {
				err = os.WriteFile(dst+".tmp", b, 0o644)
			}
			if err == nil {
				err = os.Rename(dst+".tmp", dst)
			}
			if err != nil {
				fail(err.Error())
				return
			}
		}
		l.mu.Lock()
		l.gen = gen
		l.hardened[dim] = hard
		l.mu.Unlock()
		if l.cfg.Promote != nil {
			if err := l.cfg.Promote(dim); err != nil {
				lb.Note = "promocionado, pero la recarga falló: " + err.Error()
			}
		}
	} else {
		lb.Note = "no gana: se descarta el modelo en sombra"
	}
	l.mu.Lock()
	lb.Generation = l.gen
	l.batches = append(l.batches, lb)
	l.mu.Unlock()
	if l.cfg.Publish != nil {
		l.cfg.Publish(lb)
	}
}

func firstErr(errs []error) error {
	for _, e := range errs {
		if e != nil {
			return e
		}
	}
	return nil
}
