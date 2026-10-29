package torre

import (
	"context"
	"testing"
	"time"
)

type sesionConCtx struct {
	sesionFalsa
	visto bool
}

func (s *sesionConCtx) EmbeberCtx(ctx context.Context, ids, mascara []int64) ([]float32, error) {
	s.visto = true
	<-ctx.Done()
	return nil, ctx.Err()
}

// Hallazgo 8: TorreCtx entrega el ctx a la sesión (la de ORT espera su turno con select sobre él).
func TestTorreCtxLlegaALaSesion(t *testing.T) {
	s := &sesionConCtx{}
	c := Nuevo(s, &tokFalso{}, meta(2, 0))
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	if _, err := c.TorreCtx(ctx, "a b"); err != context.DeadlineExceeded || !s.visto {
		t.Fatalf("err=%v visto=%v", err, s.visto)
	}
}
