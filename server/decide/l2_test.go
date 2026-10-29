package decide

import (
	"context"
	"math"
	"strings"
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

// torreFalsa devuelve un vector que depende del texto y cuenta las llamadas.
type torreFalsa struct {
	n      int
	textos []string
}

func (t *torreFalsa) Torre(texto string) ([]float32, error) {
	t.n++
	t.textos = append(t.textos, texto)
	if strings.Contains(texto, "· quejas ·") {
		return []float32{1, 0}, nil
	}
	return []float32{0, 1}, nil
}

// Un esquema que ningún ESQUEMAS trae: la primera petición calcula las torres, la segunda sale de la caché.
func TestL2EsquemaNuevoTorreAlVuelo(t *testing.T) {
	es, _ := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("q", []string{"a"}, 1, 1, 0)})
	esq, err := chispa3.DecodificarEsquemas(es)
	if err != nil {
		t.Fatal(err)
	}
	// Una ranura que apunta al eje 0: gana la opción cuya torre es (1, 0).
	l := NuevoL2Con(sesionFalsa{[][]float32{{3, 0}}}, esq, chispa3.Calib{}, tokFalso{})
	p := Pregunta{Texto: "¿de qué trata?", Kind: KindChoice, Estado: "me cobraron dos veces",
		Opciones: []Opcion{{ID: "quejas", Description: "reclamos"}, {ID: "ventas", Description: "compras"}}}

	// Sin codificador de torres: sin opinión, como siempre.
	if r, err := l.Decidir(context.Background(), p); err != nil || r.Conf != 0 {
		t.Fatalf("sin torres: %+v %v", r, err)
	}

	tf := &torreFalsa{}
	l.ConTorres(tf, 16)
	r, err := l.Decidir(context.Background(), p)
	if err != nil || r.Answer != "quejas" || r.Conf <= 0.5 {
		t.Fatalf("1.ª petición: %+v %v", r, err)
	}
	if tf.n != 2 || l.Misses.Load() != 1 || l.Hits.Load() != 0 {
		t.Fatalf("1.ª: %d llamadas, %d fallos, %d aciertos", tf.n, l.Misses.Load(), l.Hits.Load())
	}
	if tf.textos[0] != "passage: ¿de qué trata? · quejas · reclamos" {
		t.Fatalf("texto de torre %q", tf.textos[0])
	}
	r2, _ := l.Decidir(context.Background(), p)
	if tf.n != 2 || l.Hits.Load() != 1 || r2.Answer != r.Answer || r2.Probs["quejas"] != r.Probs["quejas"] {
		t.Fatalf("2.ª: %d llamadas, %d aciertos, %+v", tf.n, l.Hits.Load(), r2)
	}
	// Mismas opciones en otro orden: misma clave, sigue en caché.
	p.Opciones[0], p.Opciones[1] = p.Opciones[1], p.Opciones[0]
	l.Decidir(context.Background(), p)
	if tf.n != 2 || l.Hits.Load() != 2 {
		t.Fatalf("orden distinto: %d llamadas, %d aciertos", tf.n, l.Hits.Load())
	}
	// Otra descripción = otro esquema: vuelve a calcular.
	p.Opciones[1].Description = "otra"
	l.Decidir(context.Background(), p)
	if l.Misses.Load() != 2 {
		t.Fatalf("fallos %d", l.Misses.Load())
	}

	// noul: una torre (la consulta «true»).
	tf.n = 0
	rn, err := l.Decidir(context.Background(), Pregunta{Texto: "¿es queja?", Kind: KindNoul,
		Opciones: []Opcion{{ID: "false"}, {ID: "true", Description: "quejas"}}})
	if err != nil || tf.n != 1 || rn.Answer == "" {
		t.Fatalf("noul: %+v %v (%d llamadas)", rn, err, tf.n)
	}
}
