package decide

import (
	"context"
	"errors"
	"fmt"
	"sync/atomic"
	"testing"
	"time"
)

func ctxClave(k *claveViva) context.Context {
	return context.WithValue(context.Background(), ctxCobro{}, &cobroClave{k: k, ahora: time.Now})
}

// R22-1: un esperador de la clave B no hereda ErrPresupuestoTorres del líder de la clave A. Se monta el vuelo a mano: el líder
// de A (sin fichas) está en l.vuelo cuando B llega, y termina con su error de presupuesto.
func TestR22EsperadorHeredaPresupuestoDeOtraClave(t *testing.T) {
	l := l2Torres(t, &codificadorContador{}, 1024).ConMaxTorresNuevas(1)
	b := &claveViva{id: "b", torres: nuevoCuboTorres(1000)}
	c := &llamadaTorre{done: make(chan struct{})}
	l.muVuelo.Lock()
	l.vuelo["k"] = c
	l.muVuelo.Unlock()
	res := make(chan error, 1)
	go func() { _, _, err := l.torreUnica(ctxClave(b), "k", "x"); res <- err }()
	time.Sleep(20 * time.Millisecond) // B ya espera al líder de A
	l.muVuelo.Lock()
	delete(l.vuelo, "k")
	l.muVuelo.Unlock()
	c.err = ErrPresupuestoTorres
	close(c.done)
	if err := <-res; err != nil {
		t.Fatalf("B heredó el error del líder de A: %v", err)
	}
}

// codificadorTurno espera su turno de ORT respetando el ctx, como torre.Codificador: si el ctx vence antes, no calcula.
type codificadorTurno struct {
	turno  chan struct{}
	calcul atomic.Int64
}

func (c *codificadorTurno) Torre(string) ([]float32, error) {
	return c.TorreCtx(context.Background(), "")
}
func (c *codificadorTurno) TorreCtx(ctx context.Context, _ string) ([]float32, error) {
	select {
	case <-c.turno:
	case <-ctx.Done():
		return nil, ctx.Err()
	}
	c.calcul.Add(1)
	return []float32{1, 0}, nil
}

// R22-3: el líder que vence esperando turno devuelve la ficha; el esperador vivo calcula.
func TestR22FichaPerdidaEnEsperaDeTurno(t *testing.T) {
	enc := &codificadorTurno{turno: make(chan struct{}, 1)}
	l := l2Torres(t, enc, 1024).ConMaxTorresNuevas(1).ConTorresPorSegundo(0.001 + 1) // ráfaga 1
	ctxL, cancelL := context.WithCancel(context.Background())
	lider := make(chan error, 1)
	go func() { _, _, err := l.torreUnica(ctxL, "k", "x"); lider <- err }()
	for { // esperar a que el líder esté en vuelo
		l.muVuelo.Lock()
		_, ok := l.vuelo["k"]
		l.muVuelo.Unlock()
		if ok {
			break
		}
		time.Sleep(time.Millisecond)
	}
	esp := make(chan error, 1)
	go func() { _, _, err := l.torreUnica(context.Background(), "k", "x"); esp <- err }()
	time.Sleep(20 * time.Millisecond)
	cancelL()
	if err := <-lider; !errors.Is(err, context.Canceled) {
		t.Fatalf("líder: %v", err)
	}
	enc.turno <- struct{}{}
	if err := <-esp; err != nil {
		t.Fatalf("esperador vivo: %v (cálculos de ORT: %d)", err, enc.calcul.Load())
	}
}

// R22-2: con cache_torres mínima y max_torres_nuevas pequeño, todas las preguntas de max_opciones progresan.
func TestR22CacheMinimaNoProgresa(t *testing.T) {
	cfg := ConfigPorDefecto()
	cfg.Limites.MaxOpciones = 64
	l := l2Torres(t, &codificadorHash{}, cfg.cacheTorresMinima()).ConMaxTorresNuevas(2)
	sin := 0
	for q := 0; q < 20; q++ {
		p := preguntaConOpciones(64)
		p.Texto = fmt.Sprintf("pregunta %d", q)
		ok := false
		for i := 0; i < 200 && !ok; i++ {
			r, err := l.Decidir(context.Background(), p)
			ok = err == nil && !r.SinPresupuestoTorres
		}
		if !ok {
			sin++
		}
	}
	if sin != 0 {
		t.Fatalf("%d de 20 preguntas no progresan", sin)
	}
}

type codificadorHash struct{}

func (codificadorHash) Torre(string) ([]float32, error) { return []float32{1, 0}, nil }
