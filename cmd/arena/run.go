package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math"
	"math/rand/v2"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/juan52878911/chispa/contracts"
	"github.com/juan52878911/chispa/internal/attacks"
	"github.com/juan52878911/chispa/internal/dataset"
	"github.com/juan52878911/chispa/internal/detectors"
	"github.com/juan52878911/chispa/internal/learn"
	"github.com/juan52878911/chispa/internal/ledger"
	"github.com/juan52878911/chispa/internal/swarm"
	"github.com/juan52878911/chispa/internal/web"
)

func clampP(p float64) float64 { return math.Min(math.Max(p, 1e-4), 1-1e-4) }

// swarmScore es el Scorer de la búsqueda guiada: p de la etiqueta verdadera
// según la media de log-odds del enjambre, con una llamada por lote y detector.
func swarmScore(procs []*replica, trueLabel string) attacks.Scorer {
	return func(ctx context.Context, texts []string) ([]float64, error) {
		items := make([]contracts.DecideItem, len(texts))
		for i, t := range texts {
			items[i] = contracts.DecideItem{ID: fmt.Sprint(i), Text: t}
		}
		sum := make([]float64, len(texts))
		var mu sync.Mutex
		var wg sync.WaitGroup
		n := 0
		for _, p := range procs {
			if p == nil || !p.up.Load() {
				continue
			}
			wg.Add(1)
			go func(p *replica) {
				defer wg.Done()
				res, err := batcherFor(p).decide(ctx, items)
				if err != nil {
					return
				}
				mu.Lock()
				defer mu.Unlock()
				n++
				for i, r := range res {
					q := clampP(r.Probs[trueLabel])
					sum[i] += math.Log(q / (1 - q))
				}
			}(p)
		}
		wg.Wait()
		if n == 0 {
			return nil, fmt.Errorf("ningún detector vivo")
		}
		out := make([]float64, len(texts))
		for i := range sum {
			out[i] = 1 / (1 + math.Exp(-sum[i]/float64(n)))
		}
		return out, nil
	}
}

func hexID(r *rand.Rand) string { return fmt.Sprintf("%016x%016x", r.Uint64(), r.Uint64()) }

func run(args []string) error {
	fs := flag.NewFlagSet("run", flag.ExitOnError)
	dataDir := fs.String("data", "data", "data dir")
	models := fs.String("models", "models", "models dir")
	addr := fs.String("addr", "127.0.0.1:8088", "panel addr")
	basePort := fs.Int("base-port", 9100, "first detector port")
	vms := fs.Int("vms", 12, "initial replicas (min one per logical detector)")
	maxVMs := fs.Int("max-vms", 0, "cap on replicas (0 = half of host RAM / -vm-mem)")
	vmMem := fs.Int("vm-mem", 128, "MiB budgeted per replica")
	hold := fs.Duration("step", 6*time.Second, "ramp: time held at each step")
	autoRamp := fs.Bool("ramp", false, "start the ramp right away")
	vcpuUSD := fs.Float64("vcpu-usd", 0.04, "ASSUMED price of one vCPU-hour, USD")
	searchFrac := fs.Float64("search-frac", 0.4, "fraction of attacks using guided search")
	budget := fs.Int("budget", 6, "guided search iterations per seed")
	width := fs.Int("width", 8, "guided search candidates per iteration")
	batch := fs.Int("batch", 64, "learning: fooled attacks per batch")
	backend := fs.String("backend", "process", "process | microvm (needs kling and the golden snapshot)")
	snapshot := fs.String("snapshot", "arena-det", "microvm: golden snapshot of the detector")
	bankMode := fs.Bool("bank", true, "microvm: weights baked in the golden snapshot, shared copy-on-write")
	rebakeEvery := fs.Duration("rebake-every", 60*time.Second, "microvm: at most one golden rebake per interval (0 = never)")
	goldenImage := fs.String("golden-image", "arena-base", "microvm: image used to rebuild the golden after a promotion")
	budgetFrac := fs.Float64("budget-frac", 0.5, "fraction of host RAM/CPU the arena may use")
	cpuStop := fs.Float64("cpu-stop", 50, "ramp stops when the host CPU %% passes this")
	vonSnap := fs.String("von-snapshot", "", "microvm: restore this VON snapshot as teacher (e.g. von-qwen15-q4)")
	vonReplicas := fs.Int("von-replicas", 1, "VON replicas restored from the same snapshot (shared weights)")
	vonSlots := fs.Int("von-slots", 1, "concurrent requests per VON replica")
	perNode := fs.Int("per-node", 12, "microvm+bank: logical detectors served by each microVM node (0 = one VM per detector)")
	vmCPU := fs.Int("vm-cpu-pct", 100, "microvm: CPU ceiling per detector VM, % of one core (kindling default is 50)")
	perVM := fs.Int("workers-per-vm", 16, "attack workers per live replica (fills the micro-batches)")
	vonCPU := fs.Int("von-cpu-pct", 0, "CPU ceiling per VON replica, % of one core (0 = none)")
	fs.IntVar(&batchMax, "batch-max", 64, "micro-batch: max items per /decide_batch")
	fs.IntVar(&batchInflight, "batch-inflight", 2, "micro-batch: batches in flight per replica")
	fs.DurationVar(&batchWait, "batch-wait", 2*time.Millisecond, "micro-batch: max wait to fill a batch")
	vonURL := fs.String("von-url", "", "VON teacher: OpenAI-compatible base URL (empty = seed oracle)")
	vonModel := fs.String("von-model", "von-qwen15", "VON teacher model name")
	vonToken := fs.String("von-token", "", "VON bearer token")
	maxAttacks := fs.Int64("max-attacks", 0, "stop after N attacks (0 = forever)")
	smoke := fs.Bool("smoke", false, "run -max-attacks attacks, verify, exit")
	fs.Parse(args)
	if *smoke && *maxAttacks == 0 {
		*maxAttacks = 50
	}

	// Semillas de ataque: parte del test (nunca vista al entrenar); la otra
	// parte es el conjunto limpio del bucle de aprendizaje.
	seeds := map[string][]contracts.Example{}
	accs := map[string]float64{}
	for _, dim := range contracts.DimensionOrder {
		ex, err := detectors.ReadSplit(*dataDir, dim, "test")
		if err != nil {
			return fmt.Errorf("faltan datos (make dataset train): %w", err)
		}
		seeds[dim], _ = detectors.SplitTest(ex)
		for _, k := range detectors.Kinds {
			accs[detectors.ID(dim, k)] = detectors.ReadInfo(*models, detectors.ID(dim, k)).TestAccuracy
		}
	}
	attacks.BenignPool = dataset.BenignPool()

	exe, err := os.Executable()
	if err != nil {
		return err
	}
	led, err := ledger.Open(filepath.Join(*dataDir, "ledger.jsonl"))
	if err != nil {
		return err
	}
	defer led.Close()
	hub := web.NewHub()
	var pl Launcher
	switch *backend {
	case "process":
		p := &procLauncher{exe: exe, models: *models, mem: *vmMem}
		p.port.Store(int32(*basePort - 1))
		pl = p
	case "microvm":
		vl := &vmLauncher{snapshot: *snapshot, models: *models, mem: *vmMem, bank: *bankMode, cpuPct: *vmCPU}
		if *bankMode && *perNode > 0 {
			vl.perNode = *perNode
		}
		pl = vl
	default:
		return fmt.Errorf("backend desconocido %q", *backend)
	}
	fl := newFleet(pl, led, hub, accs)
	defer fl.stopAll()
	sc := newScaler(fl, led, hub, *maxVMs, *hold, *budgetFrac, *cpuStop)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	var pool *learn.VONPool
	if *vonSnap != "" {
		urls, stopVON, err := startVONPool(ctx, *vonSnap, *vonReplicas, *vonCPU)
		if err != nil {
			return fmt.Errorf("VON: %w", err)
		}
		defer stopVON()
		pool = learn.NewVONPool(urls, *vonSnap)
		pool.Snapshot = *vonSnap
		pool.SetSlots(*vonSlots)
		go func() {
			if err := pool.Prime(ctx); err != nil {
				log.Printf("VON prime: %v", err)
			}
		}()
	} else if *vonURL != "" {
		pool = learn.NewVONPool(strings.Split(*vonURL, ","), *vonModel)
		pool.Token = *vonToken
		pool.SetSlots(*vonSlots)
	}
	if _, err := sc.setTarget(ctx, *vms); err != nil {
		return err
	}
	go fl.poll(ctx)
	shs := &sharingState{}
	if *backend == "microvm" {
		go shs.loop(ctx)
	}

	var teacher learn.Teacher
	if pool != nil {
		teacher = pool
	}
	promote := fl.reload
	if vl, ok := pl.(*vmLauncher); ok && vl.bank {
		promote = func(dim string) error {
			// 1) efecto inmediato: empuja los bytes (copia privada por VM);
			// 2) en segundo plano: hornea la generación nueva en el dorado y
			//    reemplaza las réplicas para recuperar los pesos compartidos.
			err := fl.reload(dim)
			bakeDirty.Store(true)
			return err
		}
	}
	if vl, ok := pl.(*vmLauncher); ok && vl.bank {
		go rebaker(ctx, *rebakeEvery, fl, vl, *models, *goldenImage, *vmMem)
	}
	ln := learn.New(learn.Config{DataDir: *dataDir, ModelsDir: *models, BatchSize: *batch, Teacher: teacher,
		Promote: promote, Publish: func(b contracts.LearnBatch) { hub.Publish(contracts.EvLearnBatch, b) }})
	go ln.Watch(ctx)

	var desiredWorkers atomic.Int64
	workersFor := func() int { return min(max(*perVM*fl.live(), 2*runtime.NumCPU()), 2048) }
	metrics := func() contracts.Metrics {
		m := led.Metrics(int(desiredWorkers.Load()), *vcpuUSD)
		m.Scale = sc.snapshot()
		m.Learning = ln.Snapshot()
		m.Flow = ln.Flow()
		if pool != nil {
			m.Flow.VON.Replicas = len(pool.URLs())
		}
		if vl, ok := pl.(*vmLauncher); ok {
			shs.fill(&m, vl.snap(), *models)
		} else {
			fillSharing(&m, sc)
		}
		return m
	}
	extra := func(mux *http.ServeMux) {
		mux.HandleFunc("POST /api/scale", func(w http.ResponseWriter, r *http.Request) {
			var body struct {
				TargetVMs int `json:"target_vms"`
			}
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				http.Error(w, err.Error(), 400)
				return
			}
			go sc.setTarget(ctx, body.TargetVMs)
			w.WriteHeader(202)
		})
		mux.HandleFunc("POST /api/scale/ramp", func(w http.ResponseWriter, r *http.Request) {
			go sc.ramp(ctx)
			w.WriteHeader(202)
		})
		mux.HandleFunc("POST /api/learn/run", func(w http.ResponseWriter, r *http.Request) {
			if err := ln.RunNow(); err != nil {
				http.Error(w, err.Error(), 409)
				return
			}
			w.WriteHeader(202)
		})
		mux.HandleFunc("POST /api/learn/toggle", func(w http.ResponseWriter, r *http.Request) {
			json.NewEncoder(w).Encode(map[string]bool{"enabled": ln.Toggle()})
		})
	}
	srv := &http.Server{Addr: *addr, Handler: web.Handler(hub, metrics, fl.kill, fl.revive, extra)}
	go func() {
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatal(err)
		}
	}()
	defer srv.Close()
	go func() {
		t := time.NewTicker(time.Second)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				sc.sample()
				hub.Publish(contracts.EvMetrics, metrics())
			}
		}
	}()
	log.Printf("arena: %d réplicas (%s), máx %d, panel en http://%s, maestro: %s", fl.live(), pl.Name(), sc.snapshot().MaxVMs, *addr, ln.Snapshot().Teacher)
	if *autoRamp {
		go sc.ramp(ctx)
	}

	sseOK := make(chan bool, 1)
	if *smoke {
		go sseProbe(ctx, "http://"+*addr+"/events", sseOK)
	}

	// Pool de workers que crece y mengua con las réplicas vivas.
	var count atomic.Int64
	var wg sync.WaitGroup
	var spawned atomic.Int64
	actx, acancel := context.WithCancel(ctx)
	defer acancel()
	worker := func(w int64) {
		defer wg.Done()
		defer spawned.Add(-1)
		r := rand.New(rand.NewPCG(uint64(w)+1, uint64(time.Now().UnixNano())))
		for actx.Err() == nil {
			if w >= desiredWorkers.Load() {
				return
			}
			if *maxAttacks > 0 && count.Add(1) > *maxAttacks {
				return
			}
			round, err := attackOnce(actx, r, fl, seeds, *searchFrac, *budget, *width)
			if err != nil {
				if actx.Err() == nil {
					time.Sleep(50 * time.Millisecond)
				}
				continue
			}
			led.Record(round)
			ln.Offer(round)
			hub.Publish(contracts.EvSwarmResult, round)
		}
	}
	var nextID atomic.Int64
	adjust := func() {
		desiredWorkers.Store(int64(workersFor()))
		for spawned.Load() < desiredWorkers.Load() {
			spawned.Add(1)
			wg.Add(1)
			go worker(nextID.Add(1) - 1)
		}
		// Los ids por encima del deseado salen solos; se reutilizan los bajos.
		if nextID.Load() > desiredWorkers.Load() && spawned.Load() <= desiredWorkers.Load() {
			nextID.Store(spawned.Load())
		}
	}
	adjust()
	if !*smoke {
		go func() {
			for ctx.Err() == nil {
				time.Sleep(500 * time.Millisecond)
				adjust()
			}
		}()
		<-ctx.Done()
		return nil
	}
	wg.Wait()
	m := metrics()
	var swarmN, detN int64
	for _, s := range m.Swarms {
		swarmN += s.Attacks
	}
	for _, d := range m.Detectors {
		detN += d.Attacks
	}
	got := false
	select {
	case got = <-sseOK:
	case <-time.After(3 * time.Second):
	}
	fmt.Printf("smoke: attacks=%d swarm_results=%d detector_results=%d sse_metrics=%v replicas=%d\n", m.Attacks, swarmN, detN, got, m.Scale.LiveVMs)
	if m.Attacks < *maxAttacks || swarmN < *maxAttacks || detN < *maxAttacks || !got {
		return fmt.Errorf("smoke FAILED")
	}
	fmt.Println("smoke OK")
	return nil
}

func sseProbe(ctx context.Context, url string, ok chan<- bool) {
	time.Sleep(200 * time.Millisecond)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		ok <- false
		return
	}
	defer res.Body.Close()
	sc := bufio.NewScanner(res.Body)
	sc.Buffer(make([]byte, 1<<20), 1<<22)
	for sc.Scan() {
		if strings.Contains(sc.Text(), `"type":"metrics"`) {
			ok <- true
			return
		}
	}
	ok <- false
}

func attackOnce(ctx context.Context, r *rand.Rand, fl *fleet, seeds map[string][]contracts.Example,
	searchFrac float64, budget, width int) (contracts.AttackRound, error) {
	dim := contracts.DimensionOrder[r.IntN(len(contracts.DimensionOrder))]
	seed := seeds[dim][r.IntN(len(seeds[dim]))]
	procs := fl.pick(dim, detectors.Kinds)
	a := contracts.Attack{AttackID: hexID(r), SeedID: seed.ID, Dimension: dim, TrueLabel: seed.Label,
		OriginalText: seed.Text, CreatedAt: time.Now().UTC()}
	if r.Float64() < searchFrac {
		a.Generator = "search"
		text, ops, it, _, err := attacks.Search(ctx, r, seed.Text, attacks.BenignPool, budget, width, swarmScore(procs, seed.Label))
		if err != nil {
			return contracts.AttackRound{}, err
		}
		a.AttackedText, a.Operators, a.Iteration = text, ops, it
	} else {
		a.Generator = "mutation"
		a.AttackedText, a.Operators = attacks.Mutate(r, seed.Text, 1+r.IntN(3))
	}
	item := []contracts.DecideItem{{ID: a.AttackID, Text: a.AttackedText}}
	votes := make([]contracts.DetectorResult, len(procs))
	var wg sync.WaitGroup
	for i, p := range procs {
		wg.Add(1)
		go func(i int, p *replica) {
			defer wg.Done()
			if p == nil {
				votes[i] = contracts.DetectorResult{AttackID: a.AttackID, DetectorID: detectors.ID(dim, detectors.Kinds[i]), Error: "down"}
				return
			}
			v := contracts.DetectorResult{AttackID: a.AttackID, DetectorID: p.id}
			if !p.up.Load() {
				v.Error = "down"
				votes[i] = v
				return
			}
			res, err := batcherFor(p).decide(ctx, item)
			if err != nil {
				v.Error = err.Error()
				votes[i] = v
				return
			}
			d := res[0]
			v.PredictedLabel, v.Probs, v.Escalate, v.LatencyMS = d.Label, d.Probs, d.Escalate, d.LatencyMS
			// Misma regla que el enjambre: engaña si contesta mal sin escalar.
			v.Fooled = !d.Escalate && d.Label != seed.Label
			votes[i] = v
		}(i, p)
	}
	wg.Wait()
	return contracts.AttackRound{Attack: a, Detectors: votes, Swarm: swarm.Verdict(a.AttackID, dim, seed.Label, votes)}, nil
}
