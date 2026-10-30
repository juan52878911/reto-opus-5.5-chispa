package decide

import (
	"context"
	"math"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"chispa/runtime/tok"
)

// Distribución bimodal: la mediana depende de recorrer los niveles en orden numérico, no el declarado.
var (
	ordenesWA  = [][]string{{"1", "2", "3"}, {"3", "1", "2"}, {"2", "3", "1"}, {"3", "2", "1"}}
	probsBimWA = map[string]float64{"1": 0.45, "2": 0.1, "3": 0.45}
)

func opsWA(ids []string) []Opcion {
	out := make([]Opcion, len(ids))
	for i, id := range ids {
		out[i] = Opcion{ID: id}
	}
	return out
}

func TestWAOrdenNivel(t *testing.T) {
	if got := tok.OrdenNivel([]string{"10", "2", "1"}); strings.Join(got, ",") != "1,2,10" {
		t.Fatalf("numérico: %v", got)
	}
	in := []string{"alto", "bajo", "medio"}
	if got := tok.OrdenNivel(in); strings.Join(got, ",") != "alto,bajo,medio" {
		t.Fatalf("no numérico debe conservar el orden: %v", got)
	}
	if got := tok.OrdenNivel([]string{"3", "x", "1"}); strings.Join(got, ",") != "3,x,1" {
		t.Fatalf("mezcla debe conservar el orden: %v", got)
	}
}

func TestWAPermutacionL0Ordinal(t *testing.T) {
	for _, ids := range ordenesWA {
		r := ordinal(Pregunta{Kind: KindScore, Opciones: opsWA(ids)}, Respuesta{Answer: "1", Probs: probsBimWA, Conf: 0.45})
		if r.Answer != "2" {
			t.Fatalf("orden %v: %q, esperaba 2", ids, r.Answer)
		}
	}
}

func TestWAPermutacionL1RespuestaScore(t *testing.T) {
	var ref string
	for i, ids := range ordenesWA {
		r := respuestaScore(Pregunta{Kind: KindScore, Opciones: opsWA(ids)}, simsPorID(ids, map[string]float64{"1": .8, "2": .5, "3": .8}), 0.1)
		if i == 0 {
			ref = r.Answer
		}
		if r.Answer != ref || ref != "2" {
			t.Fatalf("orden %v: %q (ref %q, esperaba 2)", ids, r.Answer, ref)
		}
	}
}

func simsPorID(ids []string, m map[string]float64) []float64 {
	out := make([]float64, len(ids))
	for i, id := range ids {
		out[i] = m[id]
	}
	return out
}

func TestWAPermutacionAgregarProbs(t *testing.T) {
	for _, ids := range ordenesWA {
		_, ans, _, ok := tok.AgregarProbs("score", ids, []map[string]float64{probsBimWA, probsBimWA}, tok.AggMax, 0.5)
		if !ok || ans != "2" {
			t.Fatalf("orden %v: %q ok=%v", ids, ans, ok)
		}
	}
}

func TestWAPermutacionL3(t *testing.T) {
	f := &llmFalso{contenido: `{"probs":{"1":0.45,"2":0.1,"3":0.45}}`}
	l, _ := nuevoL3Test(t, f.arranca(t), nil)
	for _, ids := range ordenesWA {
		r, _ := l.Decidir(context.Background(), pregL3(KindScore, ids...))
		if r.Answer != "2" || math.Abs(r.Conf-0.1) > 1e-9 {
			t.Fatalf("orden %v: %+v", ids, r)
		}
	}
}

// L2 con texto largo (trozos): la agregación de ventanas recorre los niveles por id numérico.
func TestWAPermutacionL2Trozos(t *testing.T) {
	es, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("s", []string{"1", "2", "3"}, 1, 1, 0)})
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(es)
	if err != nil {
		t.Fatal(err)
	}
	// A=0: P(y>1)=σ(−b)=0,55 y P(y>2)=σ(−(b+inc))=0,45 → probs {1: .45, 2: .1, 3: .45}.
	b := -math.Log(0.55 / 0.45)
	cal := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"score3": {T: 1, A: 0, B: b, Theta: 0.5}, "score3#1": {A: -2 * b}}}
	l2 := NuevoL2Con(&sesionCuenta{}, esq, cal, tokTrozosFalso{}).ConTextoLargo(TextoLargo{Estrategia: "trozos", MaxTrozos: 3})
	for _, ids := range ordenesWA {
		p := Pregunta{Texto: "s", Kind: KindScore, Estado: "uno dos tres cuatro", Opciones: opsWA(ids)}
		r, err := l2.Decidir(conPresupuesto(context.Background()), p)
		if err != nil {
			t.Fatal(err)
		}
		if r.Answer != "2" {
			t.Fatalf("orden %v: %+v", ids, r)
		}
	}
}
