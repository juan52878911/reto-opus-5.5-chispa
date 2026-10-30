package main

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/juan52878911/chispa/contracts"
	"github.com/juan52878911/chispa/internal/detsrv"
	"github.com/juan52878911/chispa/internal/ledger"
	"github.com/juan52878911/chispa/internal/web"
)

// replica es una instancia viva de un detector lógico (dim, kind): un proceso
// local o una microVM.
type replica struct {
	id, dim, kind string
	client        *detsrv.Client
	up            atomic.Bool
	handle        any // lo que el lanzador necesite para pararla
	bootMS        float64
	mu            sync.Mutex
	last          contracts.Health
	baseCPU       float64 // gasto de vidas anteriores (matar no borra coste)
	baseDec       int64
	stopped       bool
}

// Launcher arranca y para réplicas. Hay dos: procesos locales y microVMs.
type Launcher interface {
	Name() string
	MemMiB() int
	VCPUs() int
	Start(ctx context.Context, r *replica) (baseURL string, err error)
	Stop(r *replica) error
}

// procLauncher: un proceso `arena detector` por réplica, GOMAXPROCS=1.
type procLauncher struct {
	exe, models string
	port        atomic.Int32
	mem         int
}

func (p *procLauncher) Name() string { return "process" }
func (p *procLauncher) MemMiB() int  { return p.mem }
func (p *procLauncher) VCPUs() int   { return 1 }

// procLog guarda las últimas líneas de salida de un proceso hijo para
// incluirlas en el error si no arranca.
type procLog struct {
	mu    sync.Mutex
	lines []string
}

func (l *procLog) add(s string) {
	l.mu.Lock()
	l.lines = append(l.lines, s)
	if len(l.lines) > 20 {
		l.lines = l.lines[len(l.lines)-20:]
	}
	l.mu.Unlock()
}

func (l *procLog) tail() string {
	l.mu.Lock()
	defer l.mu.Unlock()
	if len(l.lines) == 0 {
		return "(sin salida)"
	}
	return strings.Join(l.lines, " | ")
}

// procHandle: el proceso hijo, su grupo y su salida reciente.
type procHandle struct {
	cmd    *exec.Cmd
	log    *procLog
	done   chan struct{}
	mu     sync.Mutex // Kill y recogida (Wait4) van bajo el mismo cerrojo
	reaped bool       // el líder ya se recogió: su pgid puede ser de otro
}

// reap recoge al hijo bajo h.mu, sin bloquear mientras siga vivo, para que
// Stop no pueda matar un pgid reutilizado entre la recogida y su comprobación.
func (h *procHandle) reap() {
	pid := h.cmd.Process.Pid
	for {
		h.mu.Lock()
		var ws syscall.WaitStatus
		wp, err := syscall.Wait4(pid, &ws, syscall.WNOHANG, nil)
		if wp == pid || (err != nil && err != syscall.EINTR) {
			h.reaped = true
			h.mu.Unlock()
			return
		}
		h.mu.Unlock()
		time.Sleep(10 * time.Millisecond)
	}
}

// healthTimeout: plazo total de espera a /health tras el arranque.
const healthTimeout = 30 * time.Second

const startTimeout = 20 * time.Second

func (p *procLauncher) Start(ctx context.Context, r *replica) (string, error) {
	// El hijo escucha en 127.0.0.1:0 y anuncia el puerto real ("LISTEN addr"):
	// reservar un puerto y cerrarlo antes de lanzar dejaba una carrera con
	// otros trabajos del nodo.
	cmd := exec.Command(p.exe, "detector", "-id", r.id, "-dim", r.dim, "-kind", r.kind, "-models", p.models, "-addr", "127.0.0.1:0")
	cmd.Env = append(os.Environ(), "GOMAXPROCS=1")
	// Grupo propio y muerte con el padre: nada queda vivo si arena cae.
	cmd.SysProcAttr = sysProcAttr()
	out, err := cmd.StdoutPipe()
	if err != nil {
		return "", err
	}
	errp, err := cmd.StderrPipe()
	if err != nil {
		return "", err
	}
	if err := cmd.Start(); err != nil {
		return "", fmt.Errorf("%s: no arrancó el proceso: %w", r.id, err)
	}
	h := &procHandle{cmd: cmd, log: &procLog{}, done: make(chan struct{})}
	r.handle = h
	addrCh := make(chan string, 1)
	var rd sync.WaitGroup
	scan := func(rc io.Reader, announce bool) {
		defer rd.Done()
		drainLines(rc, func(t string) {
			if announce && strings.HasPrefix(t, "LISTEN ") {
				select {
				case addrCh <- strings.TrimPrefix(t, "LISTEN "):
				default:
				}
				return
			}
			h.log.add(t)
		})
	}
	rd.Add(2)
	go scan(out, true)
	go scan(errp, false)
	go func() { rd.Wait(); h.reap(); close(h.done) }()
	select {
	case addr := <-addrCh:
		return "http://" + addr, nil
	case <-h.done:
		return "", fmt.Errorf("%s: el detector salió antes de escuchar; último log: %s", r.id, h.log.tail())
	case <-time.After(startTimeout):
		p.Stop(r)
		return "", fmt.Errorf("%s: sin puerto tras %s; último log: %s", r.id, startTimeout, h.log.tail())
	case <-ctx.Done():
		p.Stop(r)
		return "", ctx.Err()
	}
}

func (p *procLauncher) Stop(r *replica) error {
	h, ok := r.handle.(*procHandle)
	if !ok || h.cmd.Process == nil {
		return nil
	}
	// Si el hijo ya fue recogido, su pid puede ser de otro grupo: no matar.
	// La comprobación y el Kill van bajo el cerrojo con el que se recoge.
	h.mu.Lock()
	if h.reaped {
		h.mu.Unlock()
		return nil
	}
	// Mata el grupo entero; ESRCH (ya muerto) no es un error.
	if err := syscall.Kill(-h.cmd.Process.Pid, syscall.SIGKILL); err != nil && err != syscall.ESRCH {
		err = h.cmd.Process.Kill()
		h.mu.Unlock()
		return err
	}
	h.mu.Unlock()
	select {
	case <-h.done:
	case <-time.After(2 * time.Second):
	}
	return nil
}

// drainLines entrega cada línea de rc a fn. Una línea de más de 1 MiB se
// trunca a 1 MiB (el resto se descarta) y se siguen entregando las siguientes.
func drainLines(rc io.Reader, fn func(string)) {
	const max = 1 << 20
	br := bufio.NewReaderSize(rc, 64<<10)
	var line []byte
	for {
		frag, isPrefix, err := br.ReadLine()
		if len(line) < max {
			room := max - len(line)
			if len(frag) > room {
				frag = frag[:room]
			}
			line = append(line, frag...)
		}
		if isPrefix && err == nil {
			continue
		}
		if err != nil {
			if len(line) > 0 {
				fn(string(line))
			}
			return
		}
		fn(string(line))
		line = line[:0]
	}
}

// fleet es el conjunto de réplicas, agrupadas por dimensión y tipo.
type fleet struct {
	l    Launcher
	led  *ledger.Ledger
	hub  *web.Hub
	mu   sync.Mutex
	reps map[string]*replica              // id → réplica
	byDK map[string]map[string][]*replica // dim → kind → réplicas
	seq  map[string]int
	rr   atomic.Uint64
	accs map[string]float64 // exactitud en test por detector lógico
}

func newFleet(l Launcher, led *ledger.Ledger, hub *web.Hub, accs map[string]float64) *fleet {
	return &fleet{l: l, led: led, hub: hub, reps: map[string]*replica{}, byDK: map[string]map[string][]*replica{},
		seq: map[string]int{}, accs: accs}
}

func (f *fleet) add(ctx context.Context, dim, kind string) (*replica, error) {
	f.mu.Lock()
	key := dim + "-" + kind
	f.seq[key]++
	r := &replica{id: fmt.Sprintf("%s-r%d", key, f.seq[key]), dim: dim, kind: kind}
	f.reps[r.id] = r
	if f.byDK[dim] == nil {
		f.byDK[dim] = map[string][]*replica{}
	}
	f.byDK[dim][kind] = append(f.byDK[dim][kind], r)
	f.mu.Unlock()
	f.led.Register(r.id, dim, kind, f.accs[key])
	return r, f.boot(ctx, r)
}

func (f *fleet) boot(ctx context.Context, r *replica) error {
	t0 := time.Now()
	base, err := f.l.Start(ctx, r)
	if err != nil {
		f.status(r, "down")
		return err
	}
	r.client = detsrv.NewClient(base)
	// Espera a /health: el tiempo hasta aquí es el arranque (o restore).
	var lastErr error
	deadline := time.Now().Add(healthTimeout)
	for time.Now().Before(deadline) && ctx.Err() == nil {
		c, cancel := context.WithTimeout(ctx, 300*time.Millisecond)
		h, err := r.client.Health(c)
		cancel()
		lastErr = err
		if err == nil {
			r.bootMS = float64(time.Since(t0).Microseconds()) / 1000
			r.mu.Lock()
			r.last, r.stopped = *h, false
			r.mu.Unlock()
			r.up.Store(true)
			f.status(r, "up")
			return nil
		}
		time.Sleep(50 * time.Millisecond)
	}
	f.l.Stop(r)
	f.status(r, "down")
	msg := fmt.Sprintf("%s no contestó /health en %s (%s): %v", r.id, healthTimeout, base, lastErr)
	if h, ok := r.handle.(*procHandle); ok {
		msg += "; último log: " + h.log.tail()
	}
	return errors.New(msg)
}

// remove retira la última réplica de (dim, kind), dejando al menos una.
func (f *fleet) remove(dim, kind string) bool {
	f.mu.Lock()
	rs := f.byDK[dim][kind]
	if len(rs) <= 1 {
		f.mu.Unlock()
		return false
	}
	r := rs[len(rs)-1]
	f.byDK[dim][kind] = rs[:len(rs)-1]
	delete(f.reps, r.id)
	f.mu.Unlock()
	r.up.Store(false)
	dropBatcher(r)
	f.l.Stop(r)
	f.led.Unregister(r.id)
	f.hub.Publish(contracts.EvVMStatus, contracts.VMStatus{DetectorID: r.id, Dimension: dim, Kind: kind, State: "removed"})
	return true
}

// removeID retira una réplica concreta (reemplazo tras hornear un dorado).
func (f *fleet) removeID(id string) {
	f.mu.Lock()
	r := f.reps[id]
	if r == nil {
		f.mu.Unlock()
		return
	}
	rs := f.byDK[r.dim][r.kind]
	for i, x := range rs {
		if x == r {
			f.byDK[r.dim][r.kind] = append(rs[:i:i], rs[i+1:]...)
			break
		}
	}
	delete(f.reps, id)
	f.mu.Unlock()
	r.up.Store(false)
	dropBatcher(r)
	f.l.Stop(r)
	f.led.Unregister(r.id)
	f.hub.Publish(contracts.EvVMStatus, contracts.VMStatus{DetectorID: r.id, Dimension: r.dim, Kind: r.kind, State: "removed"})
}

func (f *fleet) kill(id string) error {
	f.mu.Lock()
	r := f.reps[id]
	f.mu.Unlock()
	if r == nil {
		return fmt.Errorf("detector %q desconocido", id)
	}
	r.mu.Lock()
	if r.stopped {
		r.mu.Unlock()
		return nil
	}
	r.stopped = true
	r.baseCPU += r.last.CPUSeconds
	r.baseDec += r.last.Decisions
	r.last = contracts.Health{}
	r.mu.Unlock()
	r.up.Store(false)
	f.l.Stop(r)
	f.status(r, "down")
	return nil
}

func (f *fleet) revive(id string) error {
	f.mu.Lock()
	r := f.reps[id]
	f.mu.Unlock()
	if r == nil {
		return fmt.Errorf("detector %q desconocido", id)
	}
	if r.up.Load() {
		return nil
	}
	go f.boot(context.Background(), r)
	return nil
}

func (f *fleet) status(r *replica, state string) {
	r.mu.Lock()
	h := r.last
	h.CPUSeconds += r.baseCPU
	h.Decisions += r.baseDec
	r.mu.Unlock()
	f.led.SetHealth(r.id, state, h)
	f.hub.Publish(contracts.EvVMStatus, contracts.VMStatus{DetectorID: r.id, Dimension: r.dim, Kind: r.kind,
		Addr: f.l.Name(), State: state, Health: h})
}

func (f *fleet) all() []*replica {
	f.mu.Lock()
	defer f.mu.Unlock()
	out := make([]*replica, 0, len(f.reps))
	for _, r := range f.reps {
		out = append(out, r)
	}
	return out
}

func (f *fleet) live() int {
	n := 0
	for _, r := range f.all() {
		if r.up.Load() {
			n++
		}
	}
	return n
}

// pick elige, por cada tipo de la dimensión, una réplica viva (round-robin).
// Si un tipo no tiene ninguna viva devuelve nil en su hueco: ese voto falta.
func (f *fleet) pick(dim string, kinds []string) []*replica {
	f.mu.Lock()
	defer f.mu.Unlock()
	n := f.rr.Add(1)
	out := make([]*replica, len(kinds))
	for i, k := range kinds {
		rs := f.byDK[dim][k]
		for j := 0; j < len(rs); j++ {
			r := rs[(int(n)+j)%len(rs)]
			if r.up.Load() {
				out[i] = r
				break
			}
		}
	}
	return out
}

// poll consulta /health de cada réplica viva cada segundo.
func (f *fleet) poll(ctx context.Context) {
	for ctx.Err() == nil {
		var wg sync.WaitGroup
		for _, r := range f.all() {
			if !r.up.Load() || r.client == nil {
				continue
			}
			wg.Add(1)
			go func(r *replica) {
				defer wg.Done()
				c, cancel := context.WithTimeout(ctx, 800*time.Millisecond)
				h, err := r.client.Health(c)
				cancel()
				if err != nil {
					return
				}
				r.mu.Lock()
				r.last = *h
				r.mu.Unlock()
				f.status(r, "up")
			}(r)
		}
		wg.Wait()
		select {
		case <-ctx.Done():
		case <-time.After(time.Second):
		}
	}
}

// reload pide a las réplicas de dim que recarguen su modelo.
func (f *fleet) reload(dim string) error {
	var firstErr error
	for _, r := range f.all() {
		if r.dim != dim || !r.up.Load() {
			continue
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		if err := f.l.(interface {
			Reload(context.Context, *replica) error
		}).Reload(ctx, r); err != nil && firstErr == nil {
			firstErr = err
		}
		cancel()
	}
	return firstErr
}

func (p *procLauncher) Reload(ctx context.Context, r *replica) error { return r.client.Reload(ctx) }

func (f *fleet) stopAll() {
	for _, r := range f.all() {
		f.l.Stop(r)
	}
}
