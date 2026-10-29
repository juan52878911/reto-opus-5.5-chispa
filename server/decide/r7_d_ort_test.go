//go:build ort

package decide

import (
	"context"
	"testing"
	"time"
)

// Hallazgo 8: con el turno de ORT ocupado, Embeber con ctx vencido vuelve con el error del ctx en vez de esperar el mutex.
func TestTurnoORTRespetaCtxL2(t *testing.T) {
	o := &sesionORT{sem: make(chan struct{}, 1)}
	o.sem <- struct{}{} // otro Run en curso
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	t0 := time.Now()
	if err := o.turno(ctx); err != context.DeadlineExceeded || time.Since(t0) > 2*time.Second {
		t.Fatalf("err=%v tras %v", err, time.Since(t0))
	}
	<-o.sem
	if err := o.turno(context.Background()); err != nil {
		t.Fatal(err)
	}
	<-o.sem
	cancelado, c2 := context.WithCancel(context.Background())
	c2()
	if err := o.turno(cancelado); err == nil || len(o.sem) != 0 {
		t.Fatalf("ctx cancelado debía fallar sin tomar el turno: %v", err)
	}
}
