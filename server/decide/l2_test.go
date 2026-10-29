package decide

import (
	"context"
	"math"
	"testing"

	"chispa/format/chispa3"
)

type sesionFalsa struct{ S [][]float32 }

func (s sesionFalsa) Ranuras([]int64) ([][]float32, error) { return s.S, nil }

type tokFalso struct{}

func (tokFalso) IDs(string) []int64 { return []int64{0, 5, 2} }

func ent(pregunta string, opciones []string, escala float32, v ...int8) chispa3.EntradaEsquema {
	return chispa3.EntradaEsquema{Hash: chispa3.HashEsquema(pregunta, opciones), Escala: escala, Vec: v}
}

// MaxSim = max_k softplus(h·s_k) con h = int8·escala; se compara con el cálculo a mano.
func TestL2MaxSim(t *testing.T) {
	es, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{
		ent("q", []string{"a"}, 0.5, 10, 0),
		ent("q", []string{"b"}, 0.5, 0, 10),
		ent("n", []string{"false", "true"}, 1, 2, 0),
		ent("s", []string{"1", "2", "3"}, 1, 1, 0),
	})
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(es)
	if err != nil {
		t.Fatal(err)
	}
	cal := chispa3.Calib{TauEscalate: 0.5, Tipos: map[string]chispa3.ParamsTipo{
		"choice": {T: 1, Theta: 0.5}, "noul": {T: 1, A: 1, B: -1, Theta: 0.5},
		"score3": {T: 1, A: 2, B: 0, Theta: 0.5}, "score3#2": {A: 1},
	}}
	// Ranuras: s_1 = (1, 0), s_2 = (0, 0.2): la torre «a» ve 5 y 0; la «b», 0 y 1.
	l := NuevoL2Con(sesionFalsa{[][]float32{{1, 0}, {0, 0.2}}}, esq, cal, tokFalso{})
	ctx := context.Background()

	r, err := l.Decidir(ctx, Pregunta{Texto: "q", Kind: KindChoice, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}})
	if err != nil {
		t.Fatal(err)
	}
	sa, sb := softplus(5), softplus(1) // a: max(sp(5), sp(0)); b: max(sp(0), sp(1))
	wa := math.Exp(sa) / (math.Exp(sa) + math.Exp(sb))
	if r.Answer != "a" || math.Abs(r.Probs["a"]-wa) > 1e-9 {
		t.Fatalf("choice: %+v, esperaba p(a)=%v", r, wa)
	}

	r, _ = l.Decidir(ctx, Pregunta{Texto: "n", Kind: KindNoul, Opciones: []Opcion{{ID: "true"}, {ID: "false"}}})
	pt := 1 / (1 + math.Exp(-(softplus(2) - 1))) // s = max(sp(2·1), sp(2·0,2→0,4))
	if r.Answer != "true" || math.Abs(r.Probs["true"]-pt) > 1e-9 {
		t.Fatalf("noul: %+v, esperaba %v", r, pt)
	}

	r, _ = l.Decidir(ctx, Pregunta{Texto: "s", Kind: KindScore, Opciones: []Opcion{{ID: "1"}, {ID: "2"}, {ID: "3"}}})
	s := softplus(1)
	g1, g2 := 1/(1+math.Exp(-(2*s-0))), 1/(1+math.Exp(-(2*s-1))) // b_1 = 0, b_2 = b_1 + 1
	var suma float64
	for _, p := range r.Probs {
		suma += p
	}
	if math.Abs(r.Probs["1"]-(1-g1)) > 1e-9 || math.Abs(r.Probs["2"]-(g1-g2)) > 1e-9 || math.Abs(r.Probs["3"]-g2) > 1e-9 || math.Abs(suma-1) > 1e-9 {
		t.Fatalf("score: %+v", r)
	}

	// Esquema ausente de ESQUEMAS: sin opinión, y sin llamar al ONNX.
	r, err = l.Decidir(ctx, Pregunta{Texto: "otra", Kind: KindChoice, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}})
	if err != nil || r.Conf != 0 {
		t.Fatalf("%+v %v", r, err)
	}
}

type sesionCuenta struct{ n int }

func (s *sesionCuenta) Ranuras([]int64) ([][]float32, error) { s.n++; return [][]float32{{1, 0}}, nil }

// Esquema nuevo (sin torre en ESQUEMAS): L2 no opina ni llama al ONNX y la cascada lo decide con L1 en zero-shot.
func TestEsquemaNuevoLoDecideL1(t *testing.T) {
	es, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("otro", []string{"a"}, 1, 1, 0)})
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(es)
	if err != nil {
		t.Fatal(err)
	}
	ses := &sesionCuenta{}
	l2 := NuevoL2Con(ses, esq, calibTiny(), tokFalso{})
	f := v3Tiny(t, calibTiny())
	mt, err := ArmarDesde(f, NuevoL0(8), &Config{CacheEsquemas: 16, CacheRespuestas: 16}, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	casc, err := NuevaCascada([]Capa{{"L1", 0.5}, {"L2", 0.5}}, []Decisor{mt.L1, l2}, NuevasMetricas())
	if err != nil {
		t.Fatal(err)
	}
	p := Pregunta{ID: "n", Kind: KindChoice, Texto: "¿Qué área nunca vista?", Estado: "factura", Opciones: opsReembolso()}
	r := casc.Decidir(context.Background(), p)
	if r.Layer != "L1" || r.Answer != "facturacion" || ses.n != 0 {
		t.Fatalf("%+v, llamadas al ONNX: %d", r, ses.n)
	}
	if rr, err := l2.Decidir(context.Background(), p); err != nil || rr.Conf != 0 {
		t.Fatalf("L2 sin torre debe callar: %+v %v", rr, err)
	}
}
