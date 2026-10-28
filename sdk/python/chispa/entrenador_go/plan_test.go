package main

import (
	"testing"

	"github.com/juan52878911/kindling/pkg/chispa"
)

func TestBucketsParaL0(t *testing.T) {
	const lector = 64 << 20 // MaxWeightBytes de kindling
	for _, c := range []struct {
		clases int
		mb     float64
		quiero int
	}{
		{2, 48, 1 << 18},     // binario: una salida
		{20, 48, 1 << 18},    // 10,5 MB
		{151, 48, 1 << 17},   // clinc150: a 2^18 serían 79 MB y el lector la rechaza
		{151, 1000, 1 << 18}, // sin tope práctico no pasa del de por defecto
		{151, 0.001, chispa.MinBuckets},
	} {
		b := bucketsParaL0(c.clases, c.mb)
		if b != c.quiero {
			t.Errorf("%d clases, %g MB: %d buckets, quería %d", c.clases, c.mb, b, c.quiero)
		}
		if c.mb <= 48 && b > chispa.MinBuckets && b*c.clases*2 > lector {
			t.Errorf("%d clases: la tabla (%d bytes) no cabe en el lector", c.clases, b*c.clases*2)
		}
	}
}
