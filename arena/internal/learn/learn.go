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
	"sync/atomic"
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

	// v3: flujo Chispa → VON y eficiencia en el tiempo.
	decisions, escalated atomic.Int64
	teacherCalls         atomic.Int64 // etiquetas pedidas a un maestro que no es VONPool
	eff                  []contracts.EfficiencyPoint
	lastDec, lastEsc     int64
	lastCalls            int64
	lastTS               time.Time
	trainN               map[string]int
}

// MaxHardened acota los ejemplos endurecidos por dimensión (se queda lo más reciente).
const MaxHardened = 5000

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
	return &Learner{cfg: cfg, enabled: true, pending: map[string][]contracts.Attack{}, hardened: map[string][]contracts.Example{}, trainN: map[string]int{}, lastTS: time.Now().UTC()}
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

// OfferEscalated es Offer para una decisión escalada (Chispa no está seguro).
func (l *Learner) OfferEscalated(r contracts.AttackRound) {
	r.Swarm.Escalated = true
	l.Offer(r)
}

// Offer recibe cada ronda (cuenta una decisión). Guarda los ataques que
// engañaron al enjambre y los que escaló a VON. O(1), no bloquea: si la cola
// está llena descarta lo más antiguo.
func (l *Learner) Offer(r contracts.AttackRound) {
	l.decisions.Add(1)
	if r.Swarm.Escalated {
		l.escalated.Add(1)
	}
	if !r.Swarm.Fooled && !r.Swarm.Escalated {
		return
	}
	l.mu.Lock()
	dim := r.Attack.Dimension
	if q := l.pending[dim]; len(q) >= 4*l.cfg.BatchSize {
		copy(q, q[1:])
		q[len(q)-1] = r.Attack
	} else {
		l.pending[dim] = append(q, r.Attack)
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
	asr, acc, _ = p.swarmEval3(dim, atk, clean)
	return
}

// swarmEval3 añade la tasa de escalado en el reto: lo que el enjambre tendría
// que mandar a VON. Bajarla es lo que ahorra VON con cada generación.
func (p pool) swarmEval3(dim string, atk []contracts.Attack, clean []contracts.Example) (asr, acc, esc float64) {
	verdict := func(text, truth string) contracts.SwarmResult {
		votes := make([]contracts.DetectorResult, 0, len(p))
		for _, k := range detectors.Kinds {
			d := p[k].Decide(text)
			votes = append(votes, contracts.DetectorResult{PredictedLabel: d.Label, Probs: d.Probs, Escalate: d.Escalate})
		}
		return swarm.Verdict("", dim, truth, votes)
	}
	fooled, escalated := 0, 0
	for _, a := range atk {
		v := verdict(a.AttackedText, a.TrueLabel)
		if v.Fooled {
			fooled++
		}
		if v.Escalated {
			escalated++
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
		esc = float64(escalated) / float64(len(atk))
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
			l.teacherCalls.Add(1)
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
	var escBefore, escAfter float64
	lb.ASRBefore, lb.CleanBefore, escBefore = cur.swarmEval3(dim, challenge, clean)
	l.mu.Lock()
	if len(l.eff) == 0 {
		l.addPoint(0, lb.ASRBefore, lb.CleanBefore, len(tr))
	}
	l.mu.Unlock()

	// 3. Reentreno en sombra con lo acumulado + este lote.
	t1 := time.Now()
	l.mu.Lock()
	hard := append([]contracts.Example(nil), l.hardened[dim]...)
	gen := l.gen + 1
	l.mu.Unlock()
	for _, a := range trainAtk {
		hard = append(hard, contracts.Example{ID: a.AttackID, Text: a.AttackedText, Label: a.TrueLabel, Template: "attack/" + a.SeedID})
	}
	hard = dedupeCap(hard, MaxHardened)
	shadow := filepath.Join(l.cfg.ModelsDir, "shadow", fmt.Sprintf("gen-%d-%s", gen, dim))
	if err := os.MkdirAll(shadow, 0o755); err != nil {
		fail(err.Error())
		return
	}
	trainSet := append(append([]contracts.Example(nil), tr...), hard...)
	// Las variantes Chispa de la dimensión se entrenan en paralelo (TrainKind es puro).
	var tw sync.WaitGroup
	terrs := make([]error, len(detectors.Kinds))
	for ki, k := range detectors.Kinds {
		if k == detectors.KindRules {
			continue
		}
		tw.Add(1)
		go func() {
			defer tw.Done()
			m, _, err := detectors.TrainKind(k, trainSet, va)
			if err == nil {
				err = m.Save(detectors.ModelPath(shadow, dim, k))
			}
			terrs[ki] = err
		}()
	}
	tw.Wait()
	if err := firstErr(terrs); err != nil {
		fail(err.Error())
		return
	}
	lb.TrainMS = float64(time.Since(t1).Milliseconds())
	sh, err := loadPool(shadow, dim)
	if err != nil {
		fail(err.Error())
		return
	}
	lb.ASRAfter, lb.CleanAfter, escAfter = sh.swarmEval3(dim, challenge, clean)

	// 4. Promoción solo si gana en el reto sin estropear lo limpio. Ganar es
	// engañarse menos, o engañarse igual y escalar menos a VON (más barato).
	cleanOK := lb.CleanAfter >= lb.CleanBefore-l.cfg.MaxCleanDrop
	lessFooled := lb.ASRAfter < lb.ASRBefore
	lessVON := lb.ASRAfter <= lb.ASRBefore && escAfter < escBefore-0.02
	lb.Promoted = cleanOK && (lessFooled || lessVON)
	escNote := fmt.Sprintf("escala a VON %.0f%%→%.0f%%", 100*escBefore, 100*escAfter)
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
		l.trainN[dim] = len(tr) + len(hard)
		l.addPoint(gen, lb.ASRAfter, lb.CleanAfter, len(tr)+len(hard))
		l.mu.Unlock()
		if l.cfg.Promote != nil {
			if err := l.cfg.Promote(dim); err != nil {
				lb.Note = "promocionado, pero la recarga falló: " + err.Error()
			}
		}
		if lb.Note == "" {
			lb.Note = escNote
		}
	} else if !cleanOK {
		lb.Note = "no gana: baja la exactitud limpia · " + escNote
	} else {
		lb.Note = "no gana: " + escNote
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

// dedupeCap quita duplicados por texto normalizado (gana el más reciente) y
// se queda con los últimos max.
func dedupeCap(xs []contracts.Example, max int) []contracts.Example {
	seen := make(map[string]struct{}, len(xs))
	out := make([]contracts.Example, 0, len(xs))
	for i := len(xs) - 1; i >= 0; i-- {
		k := normalize(xs[i].Text)
		if _, ok := seen[k]; ok {
			continue
		}
		seen[k] = struct{}{}
		out = append(out, xs[i])
	}
	if len(out) > max {
		out = out[:max]
	}
	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	return out
}

func (l *Learner) vonCalls() int64 {
	if p, ok := l.cfg.Teacher.(*VONPool); ok {
		return p.Stats().Calls
	}
	return l.teacherCalls.Load()
}

// addPoint añade un punto de eficiencia con la ventana desde el anterior. Con l.mu tomado.
func (l *Learner) addPoint(gen int, asr, acc float64, trainN int) {
	dec, esc, calls := l.decisions.Load(), l.escalated.Load(), l.vonCalls()
	pt := contracts.EfficiencyPoint{TS: time.Now().UTC(), Generation: gen, SwarmASR: asr, CleanAcc: acc, TrainExamples: trainN}
	if d := dec - l.lastDec; d > 0 {
		pt.EscalationRate = float64(esc-l.lastEsc) / float64(d)
		pt.VONPer1K = float64(calls-l.lastCalls) * 1000 / float64(d)
	}
	l.lastDec, l.lastEsc, l.lastCalls = dec, esc, calls
	l.eff = append(l.eff, pt)
}

// Flow es el estado del bucle Chispa → VON → reentreno. Sharing lo rellena el llamador.
func (l *Learner) Flow() contracts.Flow {
	f := contracts.Flow{Escalated: l.escalated.Load()}
	if p, ok := l.cfg.Teacher.(*VONPool); ok {
		f.VON = p.Stats()
	}
	l.mu.Lock()
	f.Efficiency = append([]contracts.EfficiencyPoint(nil), l.eff...)
	l.mu.Unlock()
	return f
}
