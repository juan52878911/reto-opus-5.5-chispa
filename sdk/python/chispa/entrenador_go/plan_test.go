package main

import (
	"strings"
	"testing"

	"chispa/format/chispa3"
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

// META conserva texto_torre (antes se rehacía sin él y el servidor servía el texto v1 sin avisar).
func TestMetaConservaTextoTorre(t *testing.T) {
	base := Meta{Version: 1, Tareas: []string{"q"}, Licencias: map[string]string{}}
	for texto, want := range map[string]string{"": "v1", "v1": "v1", "v2_sin_id": "v2_sin_id"} {
		m := base
		m.TextoTorre = texto
		b, err := codificarMeta(m)
		if err != nil {
			t.Fatalf("%q: %v", texto, err)
		}
		d, err := chispa3.DecodificarMetaTexto(b)
		if err != nil || d.VersionTextoTorre() != want {
			t.Errorf("%q: versión %q, %v (quería %q)", texto, d.VersionTextoTorre(), err, want)
		}
	}
	m := base
	m.TextoTorre = "v9"
	if _, err := codificarMeta(m); err == nil {
		t.Error("v9 debía fallar")
	}
}

// ZH: el error de tope dice el tamaño por sección, el tope y qué subir.
func TestErrTopeDiceSeccionesYComoSubirlo(t *testing.T) {
	secs := []chispa3.Seccion{{Tipo: chispa3.L1, Datos: make([]byte, 700)}, {Tipo: chispa3.CALIB, Datos: make([]byte, 30)}}
	err := errTope(secs, 900, 500)
	for _, q := range []string{"900 bytes", "tope de 500 bytes", "L1 700", "CALIB 30", "--l1", "--max-fichero", `"max_fichero"`} {
		if !strings.Contains(err.Error(), q) {
			t.Errorf("falta %q en: %v", q, err)
		}
	}
}
