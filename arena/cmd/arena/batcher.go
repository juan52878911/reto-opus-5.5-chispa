package main

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/juan52878911/chispa/contracts"
	"github.com/juan52878911/chispa/internal/detsrv"
)

// batcher junta las peticiones de muchos workers hacia una réplica y las manda
// en un solo POST /decide_batch. Con microVMs cada viaje cuesta caro (red
// virtual + VM anidada): repartirlo entre decenas de decisiones es lo que
// convierte microsegundos de Chispa en throughput real.
type batcher struct {
	r      *replica
	node   *detsrv.Client // modo nodo: un lote por microVM con varios detectores
	in     chan batchReq
	max    int
	linger time.Duration
	slots  chan struct{} // lotes en vuelo por réplica: pocos, y los demás se llenan esperando
}

type batchReq struct {
	item      contracts.DecideItem
	dim, kind string
	out       chan batchRes
}

type batchRes struct {
	res contracts.DecideResult
	err error
}

func newBatcher(r *replica, max int, linger time.Duration) *batcher {
	b := &batcher{r: r, in: make(chan batchReq, 4*max), max: max, linger: linger, slots: make(chan struct{}, batchInflight)}
	go b.loop()
	return b
}

func (b *batcher) loop() {
	for first := range b.in {
		b.slots <- struct{}{} // espera turno: mientras, la cola sigue llenándose
		reqs := []batchReq{first}
		t := time.NewTimer(b.linger)
	collect:
		for len(reqs) < b.max {
			select {
			case q, ok := <-b.in:
				if !ok {
					break collect
				}
				reqs = append(reqs, q)
			case <-t.C:
				break collect
			}
		}
		t.Stop()
		go func() {
			b.flush(reqs)
			<-b.slots
		}()
	}
}

func (b *batcher) flush(reqs []batchReq) {
	items := make([]contracts.DecideItem, len(reqs))
	for i, q := range reqs {
		items[i] = q.item
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if b.node != nil {
		multi := make([]detsrv.MultiItem, len(reqs))
		for i, q := range reqs {
			multi[i] = detsrv.MultiItem{ID: q.item.ID, Text: q.item.Text, Dim: q.dim, Kind: q.kind}
		}
		res, err := b.node.DecideMulti(ctx, multi)
		for i, q := range reqs {
			if err != nil {
				q.out <- batchRes{err: err}
				continue
			}
			q.out <- batchRes{res: res[i]}
		}
		return
	}
	c := b.r.client
	if c == nil {
		for _, q := range reqs {
			q.out <- batchRes{err: fmt.Errorf("réplica sin cliente")}
		}
		return
	}
	res, err := c.DecideBatch(ctx, items)
	for i, q := range reqs {
		if err != nil {
			q.out <- batchRes{err: err}
			continue
		}
		q.out <- batchRes{res: res.Results[i]}
	}
}

// decide manda un texto por el micro-lote de la réplica.
func (b *batcher) decide(ctx context.Context, items []contracts.DecideItem) (_ []contracts.DecideResult, err error) {
	return b.decideFor(ctx, "", "", items)
}

func (b *batcher) decideFor(ctx context.Context, dim, kind string, items []contracts.DecideItem) (_ []contracts.DecideResult, err error) {
	// La réplica puede retirarse (y cerrarse su canal) mientras se encola.
	defer func() {
		if recover() != nil {
			err = fmt.Errorf("réplica retirada")
		}
	}()
	outs := make([]chan batchRes, len(items))
	for i, it := range items {
		outs[i] = make(chan batchRes, 1)
		select {
		case b.in <- batchReq{item: it, dim: dim, kind: kind, out: outs[i]}:
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
	res := make([]contracts.DecideResult, len(items))
	for i, o := range outs {
		select {
		case r := <-o:
			if r.err != nil {
				return nil, r.err
			}
			res[i] = r.res
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
	return res, nil
}

// replicaDecide: el voto de una réplica pasa por su micro-lote; en modo nodo,
// por el de su microVM (compartido por los 12 detectores que sirve).
func replicaDecide(ctx context.Context, r *replica, items []contracts.DecideItem) ([]contracts.DecideResult, error) {
	if n, ok := r.handle.(*vmNode); ok {
		return nodeBatcher(n).decideFor(ctx, r.dim, r.kind, items)
	}
	return batcherFor(r).decide(ctx, items)
}

var nodeBatchers = map[*vmNode]*batcher{}

func nodeBatcher(n *vmNode) *batcher {
	batchersMu.Lock()
	defer batchersMu.Unlock()
	b := nodeBatchers[n]
	if b == nil {
		// Un nodo junta el tráfico de 12 detectores: lotes más grandes.
		b = &batcher{node: detsrv.NewClient(n.base), in: make(chan batchReq, 16*batchMax), max: 4 * batchMax,
			linger: batchWait, slots: make(chan struct{}, batchInflight)}
		go b.loop()
		nodeBatchers[n] = b
	}
	return b
}

var (
	batchersMu sync.Mutex
	batchers   = map[*replica]*batcher{}
	batchMax   = 64
	batchWait  = 2 * time.Millisecond
	// DECISIÓN — 2 lotes en vuelo por réplica. Con decenas de conexiones
	// simultáneas la VM anidada colapsa (medido: /health a 5 s); con 2, cada
	// viaje se llena hasta batchMax y la latencia queda acotada.
	batchInflight = 2
)

func batcherFor(r *replica) *batcher {
	batchersMu.Lock()
	defer batchersMu.Unlock()
	b := batchers[r]
	if b == nil {
		b = newBatcher(r, batchMax, batchWait)
		batchers[r] = b
	}
	return b
}

func dropBatcher(r *replica) {
	batchersMu.Lock()
	defer batchersMu.Unlock()
	if b := batchers[r]; b != nil {
		close(b.in)
		delete(batchers, r)
	}
}
