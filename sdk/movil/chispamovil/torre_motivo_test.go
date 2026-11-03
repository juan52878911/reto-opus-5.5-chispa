package chispamovil

import (
	"encoding/binary"
	"encoding/json"
	"math"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func bytesF32(xs ...float32) []byte {
	var b []byte
	for _, x := range xs {
		b = binary.LittleEndian.AppendUint32(b, math.Float32bits(x))
	}
	return b
}

// Un test por motivo de rechazo de InstalarTorresL2: devuelve false y MotivoInstalarTorresL2 dice por qué.
func TestInstalarTorresL2Motivos(t *testing.T) {
	c := esqDosOpciones(t)
	q := preguntasTorre[0]
	var textos []string
	json.Unmarshal([]byte(c.TextosTorreL2(q)), &textos)
	n := len(textos)
	if n < 2 {
		t.Fatalf("hacen falta ≥2 textos: %d", n)
	}
	ok := torresBytes(textos)
	d := len(ok) / (4 * n)
	filas := func(d int) []byte { return bytesF32(make([]float32, n*d)...) }

	casos := []struct {
		nombre, q string
		b         []byte
		n         int
		quiere    string
		prep      func(*Chispa)
	}{
		{"n distinto", q, ok, n + 1, "no casa con las", nil},
		{"n cero", q, ok, 0, "no casa con las", nil},
		{"bytes no divisibles", q, append(append([]byte{}, ok...), 1, 2), n, "no se reparten", nil},
		{"d cero", q, nil, n, "d=0", nil},
		{"d excesiva", q, filas(maxDimTorr + 1), n, "supera el máximo", nil},
		{"NaN", q, bytesF32(append([]float32{float32(math.NaN())}, make([]float32, n*d-1)...)...), n, "no finito", nil},
		{"Inf (fp16 desbordado)", q, bytesF32(append(make([]float32, n*d-1), float32(math.Inf(1)))...), n, "desbordó", nil},
		{"pregunta ilegible", "no es json", ok, n, "pregunta ilegible", nil},
		{"sin L2", q, ok, n, "no trae L2", func(c *Chispa) { c.tieneL2 = false }},
		{"motor degradado", q, ok, n, "motor degradado", func(c *Chispa) { c.torreMotivo = "texto inconsistente" }},
	}
	for _, k := range casos {
		t.Run(k.nombre, func(t *testing.T) {
			c := esqDosOpciones(t)
			if k.prep != nil {
				k.prep(c)
			}
			if c.InstalarTorresL2(k.q, k.b, k.n) {
				t.Fatal("debía rechazar")
			}
			if m := c.MotivoInstalarTorresL2(); !strings.Contains(m, k.quiere) {
				t.Fatalf("motivo %q no contiene %q", m, k.quiere)
			}
			if m := c.InstalarTorresL2Motivo(k.q, k.b, k.n); !strings.Contains(m, k.quiere) {
				t.Fatalf("InstalarTorresL2Motivo %q no contiene %q", m, k.quiere)
			}
		})
	}
	// Aceptada: motivo vacío (borra el anterior).
	if c.InstalarTorresL2(q, ok, n+1) || c.MotivoInstalarTorresL2() == "" {
		t.Fatal("debía rechazar con motivo")
	}
	if !c.InstalarTorresL2(q, ok, n) || c.MotivoInstalarTorresL2() != "" {
		t.Fatalf("debía aceptar: %q", c.MotivoInstalarTorresL2())
	}
}

// d distinta del Dim de TORR.
func TestInstalarTorresL2DimDistintaDeTORR(t *testing.T) {
	c := esqDosOpciones(t)
	c.torre = &chispa3.Torre{Dim: 8}
	var textos []string
	json.Unmarshal([]byte(c.TextosTorreL2(preguntasTorre[0])), &textos)
	n := len(textos)
	if c.InstalarTorresL2(preguntasTorre[0], bytesF32(make([]float32, n*4)...), n) {
		t.Fatal("debía rechazar d=4 con Dim=8")
	}
	if m := c.MotivoInstalarTorresL2(); !strings.Contains(m, "d=4") || !strings.Contains(m, "Dim=8") {
		t.Fatalf("motivo: %q", m)
	}
}
