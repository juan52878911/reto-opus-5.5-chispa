package decide

import (
	"context"
	"sync/atomic"
	"testing"
	"time"
)

// Codificador y sesión que esperan su turno de ORT respetando el ctx: apuntan el ctx que reciben.
type codificadorCtx struct {
	codificadorContador
	vistoCtx atomic.Bool
}

func (c *codificadorCtx) TorreCtx(ctx context.Context, texto string) ([]float32, error) {
	c.vistoCtx.Store(true)
	select {
	case <-ctx.Done(): // la cola de ORT, aquí un turno que nunca llega
		return nil, ctx.Err()
	case <-time.After(10 * time.Second):
		return []float32{1, 0}, nil
	}
}

// Hallazgo 8: L2 pasa el ctx de la petición a la torre; vencido el plazo no sigue esperando el turno de ORT.
func TestL2PasaCtxALaTorre(t *testing.T) {
	enc := &codificadorCtx{}
	l := l2Torres(t, enc, 1024)
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	t0 := time.Now()
	_, err := l.Decidir(ctx, preguntaConOpciones(3))
	if err == nil || !enc.vistoCtx.Load() || time.Since(t0) > 2*time.Second {
		t.Fatalf("err=%v visto=%v tras %v", err, enc.vistoCtx.Load(), time.Since(t0))
	}
}

type sesionCtx struct {
	sesionFalsa
	ctxOK atomic.Bool
}

func (s *sesionCtx) RanurasCtx(ctx context.Context, ids []int64) ([][]float32, error) {
	<-ctx.Done()
	s.ctxOK.Store(true)
	return nil, ctx.Err()
}

func TestL2PasaCtxALasRanuras(t *testing.T) {
	ses := &sesionCtx{}
	l := l2Torres(t, &codificadorContador{}, 1024)
	l.ses = ses
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	if _, err := l.Decidir(ctx, preguntaConOpciones(1)); err == nil || !ses.ctxOK.Load() {
		t.Fatalf("err=%v", err)
	}
}

// Hallazgo 8: presupuesto global de torres por segundo; agotado, L2 no opina y no ejecuta el codificador.
func TestL2PresupuestoTorresPorSegundo(t *testing.T) {
	enc := &codificadorContador{}
	l, m := l2Met(t, enc)
	l.ConMaxTorresNuevas(30).ConTorresPorSegundo(5) // ráfaga max(5, 30, 1) = 30: una pregunta de 20 cabe, la segunda no
	if r, err := l.Decidir(context.Background(), preguntaConOpciones(20)); err != nil || r.Conf == 0 {
		t.Fatalf("la ráfaga debía cubrir una pregunta completa: %+v %v", r, err)
	}
	p2 := preguntaConOpciones(20)
	p2.Texto = "¿otra?"
	r, err := l.Decidir(context.Background(), p2)
	if err != nil || r.Conf != 0 {
		t.Fatalf("debía no opinar: %+v %v", r, err)
	}
	if n := enc.n.Load(); n > 30 {
		t.Fatalf("calculó %d torres con ráfaga 30", n)
	}
	if m.PresupuestoAgotado.Load() == 0 {
		t.Fatal("PresupuestoAgotado sin contar")
	}
}
