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

func TestL2cSoporteLambdaInfinitoNoCambiaNada(t *testing.T) {
	ctx, l0 := context.Background(), conL0(map[string]float64{"a": 0.4, "b": 0.6})
	l, p, _ := montajeSoporteL2c(t, 3)
	want, err := l.DecidirCon(ctx, p, l0)
	if err != nil {
		t.Fatal(err)
	}
	inf := math.Inf(1)
	otra := p
	otra.Texto = "¿otra?"
	for n, c := range map[string]struct {
		s      *chispa3.Sopl1
		lambda *float64
	}{"sin lambda": {soplDe(t, p, 3), nil}, "lambda inf": {soplDe(t, p, 3), &inf}, "sin sección": {nil, floatPtr(1)}} {
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

func TestL2cSoporteMueveLaTorreHaciaLosEjemplos(t *testing.T) {
	l, p, sf := montajeSoporteL2c(t, 1)
	e, _ := l.conj.Buscar(ClaveConj(p))
	S := sf.S
	base := []float64{softplus(0), softplus(1)}
	// λ=1, k=1 ⇒ w=0,5: la torre de «a», (1,0), y su soporte, (0,1), dan (√2/2, √2/2); «b» (k=0) no cambia.
	l.ConSoporte(soplDe(t, p, 1), floatPtr(1))
	got := l.mezclarSims(p, e, S, base, nil)
	if math.Abs(got[0]-softplus(math.Sqrt2/2)) > 1e-3 || got[1] != base[1] {
		t.Fatalf("w=0,5: %v (base %v)", got, base)
	}
	if &got[0] == &base[0] || base[0] != softplus(0) {
		t.Fatal("no debe mutar los sims de entrada")
	}
	// Monótono en w: λ más pequeña, más cerca de los ejemplos (que coinciden con el mensaje).
	prev := got[0]
	for _, lambda := range []float64{0.25, 0.01} {
		l.ConSoporte(soplDe(t, p, 1), floatPtr(lambda))
		g := l.mezclarSims(p, e, S, base, nil)
		if g[0] <= prev {
			t.Fatalf("λ=%v: %v no sube desde %v", lambda, g[0], prev)
		}
		prev = g[0]
	}
	if math.Abs(prev-softplus(1)) > 0.02 {
		t.Fatalf("con w≈1 el MaxSim de «a» es el de su soporte: %v", prev)
	}
	// Y la decisión cambia: sin soporte la cabeza prefiere «b» (sims de la descripción); con w≈1, «a» le alcanza.
	l0 := conL0(map[string]float64{"a": 0.5, "b": 0.5})
	r0, _ := montarYDecidir(t, nil, l0)
	r1, _ := montarYDecidir(t, floatPtr(0.01), l0)
	if !(r1.Probs["a"] > r0.Probs["a"]) {
		t.Fatalf("P(a) debe subir con el soporte: %v → %v", r0.Probs["a"], r1.Probs["a"])
	}
}

func montarYDecidir(t *testing.T, lambda *float64, l0 Previas) (Respuesta, error) {
	t.Helper()
	l, p, _ := montajeSoporteL2c(t, 1)
	return l.ConSoporte(soplDe(t, p, 1), lambda).DecidirCon(context.Background(), p, l0)
}
