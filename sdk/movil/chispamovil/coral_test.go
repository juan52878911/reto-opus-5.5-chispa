package chispamovil

import (
	"context"
	"encoding/binary"
	"fmt"
	"math"
	"testing"

	"chispa/format/chispa3"

	"github.com/juan52878911/chispa/server/decide"
)

// sCero es la similitud con una torre de ceros: softplus(0).
const sCero = math.Ln2

// calibCoral da, con s=sCero, P(y>1)=0,4 y P(y>2)=0,6 (acumuladas no monótonas).
func calibCoral() chispa3.Calib {
	b0 := sCero - math.Log(0.4/0.6)
	b1 := sCero - math.Log(0.6/0.4)
	return chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{
		"score3": {A: 1, B: b0}, "score3#1": {A: b1 - b0},
	}}
}

func TestScoreL2MedianaCORALNoMonotonaParidad(t *testing.T) {
	ops := []opcion{{ID: "1"}, {ID: "2"}, {ID: "3"}}
	dops := []decide.Opcion{{ID: "1"}, {ID: "2"}, {ID: "3"}}
	c := &Chispa{calib: calibCoral()}
	r := c.score(pregunta{Kind: "score", Opciones: ops}, sCero)
	if r.Answer != "2" {
		t.Fatalf("mediana móvil: %q, quería 2", r.Answer)
	}
	// Servidor: L2 real con la misma calibración; con s=0 sale de una torre de ceros.
	esq, _ := chispa3.DecodificarEsquemas(mustEsq())
	srv := decide.NuevoL2Con(sesFalsa{[][]float32{{0, 0, 0, 0}}}, esq, calibCoral(), tokFalso{}).ConTorres(torreCero{}, 64)
	want, err := srv.Decidir(context.Background(), decide.Pregunta{ID: "q", Estado: "x", Texto: "Gravedad", Kind: decide.KindScore, Opciones: dops})
	if err != nil {
		t.Fatal(err)
	}
	if want.Answer != r.Answer {
		t.Fatalf("servidor %q ≠ móvil %q", want.Answer, r.Answer)
	}
	for id, v := range want.Probs {
		if math.Abs(r.Probs[id]-v) > 1e-9 {
			t.Fatalf("probs[%s]: móvil %v ≠ servidor %v", id, r.Probs[id], v)
		}
	}
}

// torreCero da torres de ceros: la similitud es 0 y la cabeza CORAL se evalúa en sCero.
type torreCero struct{}

func (torreCero) Torre(string) ([]float32, error) { return make([]float32, dTorre), nil }

func preguntaCoral(i int) string {
	return fmt.Sprintf(`{"question":"esq%d","kind":"choice","options":[{"id":"a"},{"id":"b"}]}`, i)
}

func instalar(c *Chispa, i int) bool {
	var b []byte
	for k := 0; k < 2*dTorre; k++ {
		b = binary.LittleEndian.AppendUint32(b, math.Float32bits(float32(k+1)))
	}
	return c.InstalarTorresL2(preguntaCoral(i), b, 2)
}

// Reinstalar un esquema que ya está no desaloja nada: solo cuentan las claves que faltan.
func TestInstalarTorresL2ReinstalarNoDesaloja(t *testing.T) {
	c := movilL2(t)
	for i := 0; i < maxDin/2; i++ {
		if !instalar(c, i) {
			t.Fatal("instalar")
		}
	}
	if len(c.dyn) != maxDin {
		t.Fatalf("dyn = %d, quería %d", len(c.dyn), maxDin)
	}
	for r := 0; r < 5; r++ {
		if !instalar(c, 0) || !instalar(c, maxDin/2-1) {
			t.Fatal("reinstalar")
		}
	}
	if len(c.dyn) != maxDin {
		t.Fatalf("reinstalar desalojó: dyn = %d", len(c.dyn))
	}
	for i := 0; i < maxDin/2; i++ {
		if !c.TorresL2(preguntaCoral(i)) {
			t.Fatalf("esquema %d desalojado sin necesidad", i)
		}
	}
}

// Las torres que otro hilo acaba de instalar (a la espera de su PuntuarL2) no se desalojan; las antiguas sí.
func TestInstalarTorresL2ProtegeRecienInstaladas(t *testing.T) {
	c := movilL2(t)
	for i := 0; i < maxDin/2; i++ {
		instalar(c, i)
	}
	// «otro hilo» instaló el último; una instalación nueva llena el LRU.
	instalar(c, 10_000)
	if !c.TorresL2(preguntaCoral(10_000)) {
		t.Fatal("la nueva debe estar")
	}
	reciente := maxDin/2 - 1
	if !c.TorresL2(preguntaCoral(reciente)) {
		t.Fatalf("la recién instalada (%d) se desalojó", reciente)
	}
	if c.TorresL2(preguntaCoral(0)) {
		t.Fatal("la más antigua debía desalojarse")
	}
	if len(c.dyn) > maxDin {
		t.Fatalf("dyn = %d > maxDin", len(c.dyn))
	}
}
