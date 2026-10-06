package main

import (
	"context"
	"log"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/juan52878911/chispa/contracts"
	"github.com/juan52878911/chispa/internal/detectors"
)

var (
	bakeMu    sync.Mutex
	bakeGen   atomic.Int64
	bankSz    atomic.Int64
	bakeDirty atomic.Bool
)

// rebaker junta promociones: como mucho un horneado cada `every`. Antes cada
// promoción lanzaba el suyo (arrancar VM, copiar, guardar, reemplazar las 12
// réplicas) y con promociones cada pocos segundos la CPU de Lima se iba ahí.
func rebaker(ctx context.Context, every time.Duration, fl *fleet, vl *vmLauncher, models, image string, mem int) {
	if every <= 0 {
		return
	}
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			if bakeDirty.Swap(false) {
				rebake(ctx, fl, vl, models, image, mem)
			}
		}
	}
}

// rebake construye el dorado de la generación siguiente con todo el banco de
// modelos ya cargado y sustituye las réplicas una a una (primero arranca la
// nueva, luego retira la vieja: el enjambre nunca pierde votos).
func rebake(ctx context.Context, fl *fleet, vl *vmLauncher, models, image string, mem int) {
	bakeMu.Lock()
	defer bakeMu.Unlock()
	gen := int(bakeGen.Add(1))
	t0 := time.Now()
	snap, err := BuildGolden(ctx, GoldenOpts{Image: image, Mem: mem, Models: models, Generation: gen})
	if err != nil {
		log.Printf("rebake g%d: %v", gen, err)
		return
	}
	vl.SetSnapshot(snap)
	log.Printf("rebake: %s horneado en %s; reemplazando réplicas", snap, time.Since(t0).Round(time.Millisecond))
	for _, r := range fl.all() {
		if ctx.Err() != nil {
			return
		}
		if _, err := fl.add(ctx, r.dim, r.kind); err != nil {
			log.Printf("rebake: %v", err)
			continue
		}
		fl.removeID(r.id)
	}
}

// sharingState mide cada pocos segundos PSS/RSS de las microVMs (Linux).
type sharingState struct {
	mu   sync.Mutex
	det  VMMem
	von  VMMem
	nDet int
}

func (s *sharingState) loop(ctx context.Context) {
	for ctx.Err() == nil {
		m, _ := measureVMMemDetail(ctx)
		var det, von VMMem
		n := 0
		for name, v := range m {
			switch {
			case strings.HasPrefix(name, "arena-von"):
				von.Pss += v.Pss
				von.Rss += v.Rss
			case strings.HasPrefix(name, "arena-golden"):
			default:
				det.Pss += v.Pss
				det.Rss += v.Rss
				n++
			}
		}
		s.mu.Lock()
		s.det, s.von, s.nDet = det, von, n
		s.mu.Unlock()
		select {
		case <-ctx.Done():
		case <-time.After(3 * time.Second):
		}
	}
}

// fill: «ingenuo» = suma de RSS (cada VM contaría sus páginas compartidas
// enteras); «real» = suma de PSS (cada página compartida se reparte).
func (s *sharingState) fill(m *contracts.Metrics, snapshot string, models string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	sh := &m.Flow.Sharing
	sh.ChispaSnapshot = snapshot
	sh.ChispaGeneration = int(bakeGen.Load())
	if bankSz.Load() == 0 {
		if b, err := detectors.LoadBank(models); err == nil {
			bankSz.Store(b.Bytes())
		}
	}
	sh.ModelBankBytes = bankSz.Load()
	if s.nDet > 0 && s.det.Rss > 0 {
		sh.NaiveMemBytes = s.det.Rss
		sh.RealMemBytes = s.det.Pss
		sh.MemPerVMBytes = s.det.Pss / int64(s.nDet)
		sh.SavedPct = 100 * (1 - float64(s.det.Pss)/float64(s.det.Rss))
	}
	if s.von.Pss > 0 {
		m.Flow.VON.MemBytes = s.von.Pss
	}
}
