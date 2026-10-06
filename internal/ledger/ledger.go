// Package ledger registra cada ronda de ataque (en memoria y en JSONL) y
// calcula las métricas de §6.6.
package ledger

import (
	"bufio"
	"encoding/json"
	"os"
	"sort"
	"sync"
	"time"

	"github.com/juan52878911/chispa/contracts"
)

const latWindow = 4096 // latencias recientes por detector para p50/p95

type detAgg struct {
	m   contracts.DetectorMetrics
	lat []float64
	pos int
}

type swarmAgg struct{ attacks, fooled, escalated int64 }

type Ledger struct {
	mu        sync.Mutex
	start     time.Time
	f         *os.File
	w         *bufio.Writer
	attacks   int64
	dets      map[string]*detAgg
	order     []string
	swarms    map[string]*swarmAgg
	ops       map[string]*contracts.OperatorMetrics
	lastN     int64
	lastDec   int64
	lastT     time.Time
	rateA     float64
	rateD     float64
	decisions int64
}

func Open(path string) (*Ledger, error) {
	f, err := os.Create(path)
	if err != nil {
		return nil, err
	}
	now := time.Now()
	return &Ledger{start: now, lastT: now, f: f, w: bufio.NewWriterSize(f, 1<<16),
		dets: map[string]*detAgg{}, swarms: map[string]*swarmAgg{}, ops: map[string]*contracts.OperatorMetrics{}}, nil
}

// Register da de alta un detector para que aparezca aunque aún no vote.
func (l *Ledger) Register(id, dim, kind string, testAcc float64) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if _, ok := l.dets[id]; !ok {
		l.dets[id] = &detAgg{m: contracts.DetectorMetrics{DetectorID: id, Dimension: dim, Kind: kind, TestAccuracy: testAcc, State: "starting"}}
		l.order = append(l.order, id)
	}
}

// Unregister quita un detector (réplica retirada al reducir la escala).
func (l *Ledger) Unregister(id string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	delete(l.dets, id)
	for i, x := range l.order {
		if x == id {
			l.order = append(l.order[:i], l.order[i+1:]...)
			break
		}
	}
}

// Totals: ataques y decisiones acumulados, para medir escalones de la rampa.
func (l *Ledger) Totals() (attacks, decisions int64) {
	l.mu.Lock()
	defer l.mu.Unlock()
	return l.attacks, l.decisions
}

// P95 de todas las latencias recientes.
func (l *Ledger) P95() float64 {
	l.mu.Lock()
	defer l.mu.Unlock()
	var all []float64
	for _, d := range l.dets {
		all = append(all, d.lat...)
	}
	return pct(all, 0.95)
}

// SetHealth actualiza estado y gasto de un detector.
func (l *Ledger) SetHealth(id, state string, h contracts.Health) {
	l.mu.Lock()
	defer l.mu.Unlock()
	d := l.dets[id]
	if d == nil {
		return
	}
	d.m.State = state
	if state == "up" {
		// CPU y decisiones se acumulan entre reinicios del proceso.
		d.m.CPUSeconds, d.m.RSSBytes, d.m.Decisions = h.CPUSeconds, h.RSSBytes, h.Decisions
	}
}

func (l *Ledger) Record(r contracts.AttackRound) {
	b, _ := json.Marshal(r)
	l.mu.Lock()
	defer l.mu.Unlock()
	l.w.Write(b)
	l.w.WriteByte('\n')
	l.attacks++
	anyFooled := false
	for _, v := range r.Detectors {
		d := l.dets[v.DetectorID]
		if d == nil {
			continue
		}
		if v.Error != "" {
			d.m.Errors++
			continue
		}
		l.decisions++
		d.m.Attacks++
		if v.Fooled {
			d.m.Fooled++
			anyFooled = true
		}
		if v.Escalate {
			d.m.Escalations++
		}
		if len(d.lat) < latWindow {
			d.lat = append(d.lat, v.LatencyMS)
		} else {
			d.lat[d.pos] = v.LatencyMS
			d.pos = (d.pos + 1) % latWindow
		}
	}
	s := l.swarms[r.Swarm.Dimension]
	if s == nil {
		s = &swarmAgg{}
		l.swarms[r.Swarm.Dimension] = s
	}
	s.attacks++
	if r.Swarm.Fooled {
		s.fooled++
	}
	if r.Swarm.Escalated {
		s.escalated++
	}
	for _, op := range r.Attack.Operators {
		o := l.ops[op.Name]
		if o == nil {
			o = &contracts.OperatorMetrics{Name: op.Name}
			l.ops[op.Name] = o
		}
		o.Uses++
		if anyFooled {
			o.Fooled++
		}
	}
}

func pct(xs []float64, p float64) float64 {
	if len(xs) == 0 {
		return 0
	}
	s := append([]float64(nil), xs...)
	sort.Float64s(s)
	return s[int(p*float64(len(s)-1))]
}

func rate(a, b int64) float64 {
	if b == 0 {
		return 0
	}
	return float64(a) / float64(b)
}

// Metrics calcula la foto actual. vcpuUSD es el precio supuesto de vCPU-hora.
func (l *Ledger) Metrics(workers int, vcpuUSD float64) contracts.Metrics {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.w.Flush()
	now := time.Now()
	if dt := now.Sub(l.lastT).Seconds(); dt >= 0.5 {
		l.rateA = float64(l.attacks-l.lastN) / dt
		l.rateD = float64(l.decisions-l.lastDec) / dt
		l.lastN, l.lastDec, l.lastT = l.attacks, l.decisions, now
	}
	m := contracts.Metrics{UptimeS: now.Sub(l.start).Seconds(), Attacks: l.attacks,
		AttacksPerSec: l.rateA, DecisionsPerS: l.rateD, Workers: workers}
	best := map[string]contracts.DetectorMetrics{}
	sumASR, nASR := map[string]float64{}, map[string]int{}
	for _, id := range l.order {
		d := l.dets[id]
		dm := d.m
		dm.ASR = rate(dm.Fooled, dm.Attacks)
		dm.P50MS, dm.P95MS = pct(d.lat, 0.5), pct(d.lat, 0.95)
		if dm.Decisions > 0 {
			dm.USPerDecision = dm.CPUSeconds * 1e6 / float64(dm.Decisions)
		}
		m.Detectors = append(m.Detectors, dm)
		m.Cost.TotalCPUSeconds += dm.CPUSeconds
		m.Cost.TotalRSSBytes += dm.RSSBytes
		m.Cost.TotalDecisions += dm.Decisions
		if dm.Attacks > 0 {
			if b, ok := best[dm.Dimension]; !ok || dm.ASR < b.ASR {
				best[dm.Dimension] = dm
			}
			sumASR[dm.Dimension] += dm.ASR
			nASR[dm.Dimension]++
		}
	}
	for _, dim := range contracts.DimensionOrder {
		s := l.swarms[dim]
		if s == nil {
			s = &swarmAgg{}
		}
		sm := contracts.SwarmMetrics{Dimension: dim, Attacks: s.attacks, Fooled: s.fooled,
			ASR: rate(s.fooled, s.attacks), Escalated: s.escalated, EscalationRate: rate(s.escalated, s.attacks)}
		if b, ok := best[dim]; ok {
			sm.BestSingleASR, sm.BestSingleID = b.ASR, b.DetectorID
			sm.MeanSingleASR = sumASR[dim] / float64(nASR[dim])
		}
		m.Swarms = append(m.Swarms, sm)
	}
	for _, o := range l.ops {
		om := *o
		om.Rate = rate(om.Fooled, om.Uses)
		m.Operators = append(m.Operators, om)
	}
	sort.Slice(m.Operators, func(i, j int) bool { return m.Operators[i].Rate > m.Operators[j].Rate })
	c := &m.Cost
	c.VCPUHourUSD = vcpuUSD
	c.USDSoFar = c.TotalCPUSeconds / 3600 * vcpuUSD
	if c.TotalDecisions > 0 {
		c.CPUMicrosPerDecide = c.TotalCPUSeconds * 1e6 / float64(c.TotalDecisions)
		c.USDPerMillion = c.CPUMicrosPerDecide / 3600 * vcpuUSD // 1e6 dec × µs/1e6 = s
	}
	return m
}

func (l *Ledger) Close() error {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.w.Flush()
	return l.f.Close()
}
