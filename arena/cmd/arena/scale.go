package main

import (
	"context"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/juan52878911/chispa/contracts"
	"github.com/juan52878911/chispa/internal/detectors"
	"github.com/juan52878911/chispa/internal/detsrv"
	"github.com/juan52878911/chispa/internal/ledger"
	"github.com/juan52878911/chispa/internal/web"
)

// scaler lleva el número de réplicas y la rampa «más VMs → cuánto más poder».
type scaler struct {
	f                   *fleet
	led                 *ledger.Ledger
	hub                 *web.Hub
	mu                  sync.Mutex
	st                  contracts.Scale
	lastCPU             float64
	lastT               time.Time
	cpuPct              float64
	stepHold            time.Duration
	cpuStop             float64
	lastBusy, lastTotal float64
	busy                sync.Mutex
}

func newScaler(f *fleet, led *ledger.Ledger, hub *web.Hub, maxVMs int, hold time.Duration, frac, cpuStop float64) *scaler {
	mem := hostMem()
	cpus := runtime.NumCPU()
	s := &scaler{f: f, led: led, hub: hub, lastT: time.Now(), stepHold: hold, cpuStop: cpuStop}
	s.st = contracts.Scale{Backend: f.l.Name(), HostMemBytes: mem, HostCPUs: cpus,
		BudgetMemBytes: int64(float64(mem) * frac), BudgetCPUs: max(1, int(float64(cpus)*frac)), VMMemMiB: f.l.MemMiB(), VMVCPUs: f.l.VCPUs()}
	byMem := int(s.st.BudgetMemBytes / int64(f.l.MemMiB()<<20))
	s.st.MaxVMs = byMem
	if vl, ok := f.l.(*vmLauncher); ok && vl.perNode > 0 {
		// Sin sobresuscribir: una vCPU por nodo y un núcleo libre para el motor.
		s.st.MaxVMs = min(byMem, max(1, cpus-1))
		s.st.VMVCPUs = vl.VCPUs()
	}
	if maxVMs > 0 && maxVMs < byMem {
		s.st.MaxVMs = maxVMs
	}
	return s
}

// nodeInfo: en modo nodo, cuántas réplicas lógicas lleva cada microVM.
func (s *scaler) perNode() int {
	if vl, ok := s.f.l.(*vmLauncher); ok && vl.perNode > 0 {
		return vl.perNode
	}
	return 1
}

// liveVMs: microVMs (o procesos) reales, no detectores lógicos.
func (s *scaler) liveVMs() int {
	if vl, ok := s.f.l.(*vmLauncher); ok && vl.perNode > 0 {
		return vl.NodeCount()
	}
	return s.f.live()
}

// sample mide el CPU como % del host: en Linux el del host entero (/proc/stat,
// incluye las microVMs); en macOS el de la arena (motor + réplicas).
func (s *scaler) sample() {
	if runtime.GOOS == "linux" {
		busy, total := procStat()
		s.mu.Lock()
		if s.lastTotal > 0 && total > s.lastTotal {
			s.cpuPct = 100 * (busy - s.lastBusy) / (total - s.lastTotal)
		}
		s.lastBusy, s.lastTotal = busy, total
		s.mu.Unlock()
		return
	}
	cpu, _ := detsrv.Usage()
	for _, r := range s.f.all() {
		r.mu.Lock()
		cpu += r.last.CPUSeconds + r.baseCPU
		r.mu.Unlock()
	}
	now := time.Now()
	s.mu.Lock()
	defer s.mu.Unlock()
	if dt := now.Sub(s.lastT).Seconds(); dt > 0.5 {
		if s.lastCPU > 0 {
			s.cpuPct = 100 * (cpu - s.lastCPU) / (dt * float64(s.st.HostCPUs))
		}
		s.lastCPU, s.lastT = cpu, now
	}
}

func (s *scaler) snapshot() contracts.Scale {
	s.mu.Lock()
	defer s.mu.Unlock()
	st := s.st
	st.LiveVMs = s.liveVMs()
	st.History = append([]contracts.ScalePoint(nil), s.st.History...)
	return st
}

func (s *scaler) vmMem() int64 {
	if runtime.GOOS == "linux" {
		t, avail := meminfo()
		return t - avail // memoria usada de verdad (CoW de los snapshots incluido)
	}
	if s.f.l.Name() == "process" {
		var t int64
		for _, r := range s.f.all() {
			r.mu.Lock()
			t += r.last.RSSBytes
			r.mu.Unlock()
		}
		return t
	}
	return int64(s.f.live()) * int64(s.f.l.MemMiB()) << 20
}

// setTarget reparte n réplicas entre los detectores lógicos (mínimo 1 cada uno)
// y arranca o para las que sobren. Devuelve el arranque medio en ms.
func (s *scaler) setTarget(ctx context.Context, n int) (float64, error) {
	s.busy.Lock()
	defer s.busy.Unlock()
	var logical [][2]string
	for _, d := range contracts.DimensionOrder {
		for _, k := range detectors.Kinds {
			logical = append(logical, [2]string{d, k})
		}
	}
	n = max(n, len(logical))
	s.mu.Lock()
	n = min(n, max(s.st.MaxVMs*s.perNode(), len(logical)))
	s.st.TargetVMs = n
	s.mu.Unlock()
	var wg sync.WaitGroup
	var mu sync.Mutex
	var boots []float64
	var firstErr error
	for i, lk := range logical {
		want := n / len(logical)
		if i < n%len(logical) {
			want++
		}
		s.f.mu.Lock()
		have := len(s.f.byDK[lk[0]][lk[1]])
		s.f.mu.Unlock()
		for ; have > want; have-- {
			s.f.remove(lk[0], lk[1])
		}
		for ; have < want; have++ {
			wg.Add(1)
			go func(d, k string) {
				defer wg.Done()
				r, err := s.f.add(ctx, d, k)
				mu.Lock()
				defer mu.Unlock()
				if err != nil && firstErr == nil {
					firstErr = err
				}
				if err == nil {
					boots = append(boots, r.bootMS)
				}
			}(lk[0], lk[1])
		}
	}
	wg.Wait()
	mean := 0.0
	for _, b := range boots {
		mean += b
	}
	if len(boots) > 0 {
		mean /= float64(len(boots))
	}
	return mean, firstErr
}

// ramp sube de escalón en escalón (una réplica más de cada detector lógico)
// hasta el máximo del presupuesto o hasta pasar la mitad del CPU del host.
func (s *scaler) ramp(ctx context.Context) {
	s.mu.Lock()
	if s.st.Ramping {
		s.mu.Unlock()
		return
	}
	s.st.Ramping, s.st.History, s.st.Note = true, nil, ""
	step := len(contracts.DimensionOrder) * len(detectors.Kinds)
	s.mu.Unlock()
	defer func() { s.mu.Lock(); s.st.Ramping = false; s.mu.Unlock() }()
	note := ""
	for n := step; ; n += step {
		if ctx.Err() != nil {
			return
		}
		s.mu.Lock()
		maxVMs := s.st.MaxVMs
		s.mu.Unlock()
		if n > maxVMs*s.perNode() {
			note = fmt.Sprintf("tope: %d microVMs (memoria y núcleos del presupuesto)", maxVMs)
			break
		}
		boot, err := s.setTarget(ctx, n)
		if err != nil {
			note = "fallo al arrancar: " + err.Error()
			break
		}
		// Deja estabilizar y mide la segunda mitad del escalón.
		time.Sleep(s.stepHold / 2)
		a0, d0 := s.led.Totals()
		t0 := time.Now()
		time.Sleep(s.stepHold / 2)
		a1, d1 := s.led.Totals()
		dt := time.Since(t0).Seconds()
		s.sample()
		s.mu.Lock()
		p := contracts.ScalePoint{TS: time.Now().UTC(), VMs: s.liveVMs(), AttacksPerSec: float64(a1-a0) / dt,
			DecisionsPerS: float64(d1-d0) / dt, P95MS: s.led.P95(), HostCPUPct: s.cpuPct, VMMemBytes: s.vmMem(), BootMS: boot}
		s.st.History = append(s.st.History, p)
		cpu := s.cpuPct
		s.mu.Unlock()
		s.hub.Publish(contracts.EvScaleStep, p)
		if runtime.GOOS == "linux" {
			if t, avail := meminfo(); t > 0 && float64(avail)/float64(t) < 0.12 {
				note = fmt.Sprintf("tope de memoria real: queda %.0f%% libre", 100*float64(avail)/float64(t))
				break
			}
		}
		if cpu >= s.cpuStop {
			note = fmt.Sprintf("tope de CPU: %.0f%% del host (límite %.0f%%)", cpu, s.cpuStop)
			break
		}
	}
	s.mu.Lock()
	s.st.Note = note
	s.mu.Unlock()
}

func meminfo() (total, avail int64) {
	b, err := os.ReadFile("/proc/meminfo")
	if err != nil {
		return 0, 0
	}
	for _, l := range strings.Split(string(b), "\n") {
		f := strings.Fields(l)
		if len(f) < 2 {
			continue
		}
		v, _ := strconv.ParseInt(f[1], 10, 64)
		switch f[0] {
		case "MemTotal:":
			total = v << 10
		case "MemAvailable:":
			avail = v << 10
		}
	}
	return
}

func procStat() (busy, total float64) {
	b, err := os.ReadFile("/proc/stat")
	if err != nil {
		return 0, 0
	}
	line := strings.SplitN(string(b), "\n", 2)[0]
	f := strings.Fields(line)
	for i, x := range f[1:] {
		v, _ := strconv.ParseFloat(x, 64)
		total += v
		if i != 3 && i != 4 { // idle, iowait
			busy += v
		}
	}
	return
}
