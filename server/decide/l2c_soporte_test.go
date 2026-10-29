package decide

import (
	"context"
	"math"
	"reflect"
	"testing"

	"chispa/format/chispa3"
)

// montajeSoporteL2c: pregunta «¿q?» con opciones a y b; torres de ESQUEMAS a=(1,0), b=(0,1) y soporte de CONJ en el que
// los ejemplos de «a» apuntan a (0,1). El mensaje tiene una sola ranura, (0,1): por la descripción gana «b».
func montajeSoporteL2c(t *testing.T, kA uint32) (*L2c, Pregunta, *simFalsa) {
	t.Helper()
	p := Pregunta{ID: "q", Texto: "¿q?", Kind: KindChoice, Estado: "x", Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	esq, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{
		{Hash: chispa3.HashEsquema("¿q?", []string{"a"}), Escala: 1.0 / 127, Vec: []int8{127, 0}},
		{Hash: chispa3.HashEsquema("¿q?", []string{"b"}), Escala: 1.0 / 127, Vec: []int8{0, 127}},
	})
	if err != nil {
		t.Fatal(err)
	}
	e, _ := chispa3.DecodificarEsquemas(esq)
	cb, err := chispa3.CodificarConj([]chispa3.EntradaConj{{
		Hash: ClaveConj(p), Cabeza: chispa3.CabezaLR, K: 1, D: 2, T: 1, Beta: 1, Esc: [3]float32{1, 1, 1},
		W: []float32{1, 1, 1, 0, 0, 0}, Clases: []string{"a", "b"},
		Escala: []float32{1.0 / 127, 1.0 / 127}, Proto: []byte{0, 127, 0, 127},
	}})
	if err != nil {
		t.Fatal(err)
	}
	conj, err := chispa3.DecodificarConj(cb)
	if err != nil {
		t.Fatal(err)
	}
	S := [][]float32{{0, 1}}
	sf := &simFalsa{S: S, sims: []float64{softplus(0), softplus(1)}}
	base := NuevoL2Con(sesionFalsa{S}, e, chispa3.Calib{}, tokFalso{})
	return NuevoL2cCon(base, sf, conj), p, sf
}

func soplDe(t *testing.T, p Pregunta, kA uint32) *chispa3.Sopl1 {
	t.Helper()
	b, err := chispa3.CodificarSopl1(3, []chispa3.EntradaSopl1{{
		Hash: ClaveConj(p), Ids: []string{"a", "b"}, K: []uint32{kA, 0}, Escala: []float32{0, 0}, Media: make([]int8, 6),
	}})
	if err != nil {
		t.Fatal(err)
	}
	s, err := chispa3.DecodificarSopl1(b)
	if err != nil {
		t.Fatal(err)
	}
	return s
}

func TestL2cSoporteNilNoCambiaNada(t *testing.T) {
	ctx, l0 := context.Background(), conL0(map[string]float64{"a": 0.4, "b": 0.6})
	l, p, _ := montajeSoporteL2c(t, 3)
	want, err := l.DecidirCon(ctx, p, l0)
	if err != nil {
		t.Fatal(err)
	}
	otra := p
	otra.Texto = "¿otra?"
	for n, c := range map[string]struct {
		s      *chispa3.Sopl1
		lambda *float64
	}{"sin lambda": {soplDe(t, p, 3), nil}, "sin sección": {nil, floatPtr(1)}} {
		l2, _, _ := montajeSoporteL2c(t, 3)
		got, err := l2.ConSoporte(c.s, c.lambda).DecidirCon(ctx, p, l0)
		if err != nil || !reflect.DeepEqual(got, want) {
			t.Fatalf("%s: %+v ≠ %+v (%v)", n, got, want, err)
		}
	}
	// Pregunta ausente de la sección: ni siquiera se toca (los sims salen tal cual).
	l.ConSoporte(soplDe(t, otra, 3), floatPtr(0.01))
	if got, _ := l.DecidirCon(ctx, p, l0); !reflect.DeepEqual(got, want) {
		t.Fatalf("pregunta ausente: %+v ≠ %+v", got, want)
	}
}

// Shrinkage de G.8 sobre los prototipos (κ ≡ λ): la torre de «a», (1,0), y su ranura de CONJ, (0,1), dan con κ=1, n=1 (λ=0,5)
// P=(√½, √½) y simproto = (0,1)·P = 0,707107 (a mano); «b» (k=0) conserva el de CONJ, 1. sim_opción no se toca.
func TestL2cSoporteMezclaLosPrototipos(t *testing.T) {
	l, p, sf := montajeSoporteL2c(t, 1)
	l.ConSoporte(soplDe(t, p, 1), floatPtr(1))
	got := l.mezclarSimproto(p, sf.S, nil)
	if len(got) != 2 || math.Abs(got[0]-math.Sqrt2/2) > 1e-6 || math.Abs(got[1]-1) > 1e-6 {
		t.Fatalf("κ=1: %v, quería [0,707107 1]", got)
	}
	// κ=0,25 ⇒ λ=0,2 ⇒ Q=(0,2, 0,8), simproto = 0,8/√0,68 = 0,970143.
	l.ConSoporte(soplDe(t, p, 1), floatPtr(0.25))
	if g := l.mezclarSimproto(p, sf.S, nil); math.Abs(g[0]-0.970143) > 1e-6 {
		t.Fatalf("κ=0,25: %v, quería 0,970143", g[0])
	}
	// Monótono: con κ menor el prototipo vuelve a los ejemplos (que coinciden con el mensaje) y el simproto sube hacia 1.
	prev := got[0]
	for _, kappa := range []float64{0.25, 0.01} {
		l.ConSoporte(soplDe(t, p, 1), floatPtr(kappa))
		g := l.mezclarSimproto(p, sf.S, nil)
		if g[0] <= prev {
			t.Fatalf("κ=%v: %v no sube desde %v", kappa, g[0], prev)
		}
		prev = g[0]
	}
	// La decisión: κ≈0 equivale a no mezclar; κ=1 baja el simproto de «a» y con él P(a).
	l0 := conL0(map[string]float64{"a": 0.5, "b": 0.5})
	r0, _ := montarYDecidir(t, nil, l0)
	rCero, _ := montarYDecidir(t, floatPtr(0), l0)
	rUno, _ := montarYDecidir(t, floatPtr(1), l0)
	if math.Abs(rCero.Probs["a"]-r0.Probs["a"]) > 1e-6 {
		t.Fatalf("κ=0 debe dar lo mismo que sin mezcla: %v ≠ %v", rCero.Probs["a"], r0.Probs["a"])
	}
	if !(rUno.Probs["a"] < r0.Probs["a"]) {
		t.Fatalf("P(a) debe bajar cuando la descripción pesa: %v → %v", r0.Probs["a"], rUno.Probs["a"])
	}
}

func montarYDecidir(t *testing.T, lambda *float64, l0 Previas) (Respuesta, error) {
	t.Helper()
	l, p, _ := montajeSoporteL2c(t, 1)
	return l.ConSoporte(soplDe(t, p, 1), lambda).DecidirCon(context.Background(), p, l0)
}

// λ = +∞ ⇒ solo descripción (ya no «sin mezcla»): P = torre de «a», (1,0), y el simproto del mensaje (0,1) con ella es 0; «b» (k=0) conserva
// el de CONJ, 1. λ = 0 ⇒ solo ejemplos: los prototipos de CONJ tal cual, la decisión de «sin mezcla».
func TestL2cSoporteLambdaCeroEInfinito(t *testing.T) {
	inf := math.Inf(1)
	l, p, sf := montajeSoporteL2c(t, 3)
	l.ConSoporte(soplDe(t, p, 3), &inf)
	got := l.mezclarSimproto(p, sf.S, nil)
	if len(got) != 2 || math.Abs(got[0]) > 1e-6 || math.Abs(got[1]-1) > 1e-6 {
		t.Fatalf("κ=∞: %v, quería [0 1]", got)
	}
	l.ConSoporte(soplDe(t, p, 3), floatPtr(0))
	cero := l.mezclarSimproto(p, sf.S, nil)
	if len(cero) != 2 || math.Abs(cero[0]-1) > 1e-2 || math.Abs(cero[1]-1) > 1e-6 {
		t.Fatalf("κ=0: %v, quería [1 1] (los prototipos de CONJ)", cero)
	}
	l0 := conL0(map[string]float64{"a": 0.5, "b": 0.5})
	r0, _ := montarYDecidir(t, nil, l0)
	rInf, _ := montarYDecidir(t, &inf, l0)
	if !(rInf.Probs["a"] < r0.Probs["a"]) {
		t.Fatalf("solo descripción: P(a) debe bajar frente a no mezclar: %v → %v", r0.Probs["a"], rInf.Probs["a"])
	}
}
