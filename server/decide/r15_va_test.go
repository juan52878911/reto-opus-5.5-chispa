package decide

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// R15 hallazgo 1: las preguntas de una petición sobre el mismo texto largo usan las mismas ventanas de L1 (memoria por texto),
// sea cual sea su orden o cuántas haya; el presupuesto cuenta ventanas únicas.
func TestR15L1SegundaPreguntaNoSoloCabeza(t *testing.T) {
	l1 := l1Largo(t, &TextoLargo{Estrategia: "trozos", Agregacion: "max", VentanaL1: 4, MaxTrozos: 3})
	met := NuevasMetricas()
	l1.UsaMetricas(met)
	largo := strings.Repeat("pedido dinero pago ", 150)
	q := preguntasL1(largo)[0]
	ctx := conPresupuesto(context.Background())
	a, err := l1.Decidir(ctx, q)
	if err != nil {
		t.Fatal(err)
	}
	b, err := l1.Decidir(ctx, q)
	if err != nil {
		t.Fatal(err)
	}
	solo, err := l1.Decidir(conPresupuesto(context.Background()), q)
	if err != nil {
		t.Fatal(err)
	}
	if a.Answer != b.Answer || a.Conf != b.Conf || a.Conf != solo.Conf {
		t.Fatalf("la respuesta depende de la posición: 1ª %v, 2ª %v, suelta %v", a.Conf, b.Conf, solo.Conf)
	}
	// 3 ventanas en la petición compartida + 3 en la suelta; no 4 (3 + la cabeza) en la primera.
	if got := met.TrozosL1.Load(); got != 6 {
		t.Fatalf("ventanas cobradas %d, esperado 6", got)
	}
}

// R15 hallazgo 2: lo que gasta L1 no se descuenta a L2 (presupuesto por capa): tras L1 en la misma petición, L2 corre el ONNX
// en max_trozos ventanas, no solo en la cabeza.
func TestR15L1AgotaPresupuestoDeL2(t *testing.T) {
	const maxTrozos = 3
	l1 := l1Largo(t, &TextoLargo{Estrategia: "trozos", Agregacion: "max", VentanaL1: 4, MaxTrozos: maxTrozos})
	l2, ses, _ := l2TrozosFalso(t, maxTrozos)
	largo := strings.Repeat("pedido dinero pago ", 150)
	ctx := conPresupuesto(context.Background())
	for _, q := range preguntasL1(largo) {
		if _, err := l1.Decidir(ctx, q); err != nil {
			t.Fatal(err)
		}
	}
	if got := presupuestoDe(ctx).trozos[capaL1]; got != maxTrozos {
		t.Fatalf("L1 cobró %d ventanas, esperado %d", got, maxTrozos)
	}
	if _, err := l2.Decidir(ctx, preguntaQ(strings.Repeat("palabra ", 50))); err != nil {
		t.Fatal(err)
	}
	if ses.n != maxTrozos {
		t.Fatalf("L2 corrió el ONNX en %d ventanas tras L1, esperado %d", ses.n, maxTrozos)
	}
}

// score en L2: el orden de las opciones en la petición no cambia la respuesta.
func TestR15L2ScoreOrdenDeOpcionesNoCambiaRespuesta(t *testing.T) {
	es, _ := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("s", []string{"1", "2", "3"}, 1, 1, 0)})
	esq, _ := chispa3.DecodificarEsquemas(es)
	cal := chispa3.Calib{TauEscalate: 0.5, Tipos: map[string]chispa3.ParamsTipo{"score3": {T: 1, A: 2, B: 0, Theta: 0.5}, "score3#1": {A: 1}}}
	l := NuevoL2Con(sesionFalsa{[][]float32{{1, 0}}}, esq, cal, tokFalso{})
	dec := func(ids ...string) Respuesta {
		var ops []Opcion
		for _, id := range ids {
			ops = append(ops, Opcion{ID: id})
		}
		r, err := l.Decidir(context.Background(), Pregunta{Texto: "s", Kind: KindScore, Opciones: ops})
		if err != nil {
			t.Fatal(err)
		}
		return r
	}
	want := dec("1", "2", "3")
	if want.Conf == 0 {
		t.Fatalf("referencia sin opinión: %+v", want)
	}
	for _, ids := range [][]string{{"3", "2", "1"}, {"2", "3", "1"}, {"1", "3", "2"}} {
		got := dec(ids...)
		if got.Answer != want.Answer || math.Abs(got.Conf-want.Conf) > 1e-12 {
			t.Fatalf("orden %v: %+v ≠ %+v", ids, got, want)
		}
		for id, p := range want.Probs {
			if math.Abs(got.Probs[id]-p) > 1e-12 {
				t.Fatalf("orden %v: prob %s %v ≠ %v", ids, id, got.Probs[id], p)
			}
		}
	}
	if r := dec("1", "2", "4"); r.Conf != 0 {
		t.Fatalf("ids que no son 1..K no deben opinar: %+v", r)
	}
}

func opsIDs(ids ...string) []Opcion {
	var ops []Opcion
	for _, id := range ids {
		ops = append(ops, Opcion{ID: id})
	}
	return ops
}

func l2Score(t *testing.T, cal chispa3.Calib, escalas ...[]string) *L2 {
	t.Helper()
	var es []chispa3.EntradaEsquema
	for _, ids := range escalas {
		es = append(es, ent("s", ids, 1, 1, 0))
	}
	b, err := chispa3.CodificarEsquemas(2, es)
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(b)
	if err != nil {
		t.Fatal(err)
	}
	return NuevoL2Con(sesionFalsa{[][]float32{{1, 0}}}, esq, cal, tokFalso{})
}

func calibNiveles(K int) chispa3.Calib {
	t := map[string]chispa3.ParamsTipo{fmt.Sprintf("score%d", K): {T: 1, A: 2, B: 0, Theta: 0.5}}
	for j := 1; j < K-1; j++ {
		t[fmt.Sprintf("score%d#%d", K, j)] = chispa3.ParamsTipo{A: 0.4}
	}
	return chispa3.Calib{TauEscalate: 0.5, Tipos: t}
}

// (a) score con 12 niveles: cualquier permutación (incluido "10" < "2" lexicográfico) da lo mismo que 1..12.
func TestR15L2ScoreDocePermutado(t *testing.T) {
	var base []string
	for i := 1; i <= 12; i++ {
		base = append(base, fmt.Sprint(i))
	}
	perm := []string{"10", "2", "12", "1", "7", "3", "11", "5", "9", "4", "8", "6"}
	l := l2Score(t, calibNiveles(12), base)
	dec := func(ids []string) Respuesta {
		r, err := l.Decidir(context.Background(), Pregunta{Texto: "s", Kind: KindScore, Opciones: opsIDs(ids...)})
		if err != nil {
			t.Fatal(err)
		}
		return r
	}
	want, got := dec(base), dec(perm)
	if want.Conf == 0 || got.Answer != want.Answer || math.Abs(got.Conf-want.Conf) > 1e-12 || len(got.Probs) != 12 {
		t.Fatalf("12 niveles permutados: %+v ≠ %+v", got, want)
	}
}

// (b) L2 y score: con ids que no son exactamente 1..K no opina (ni gasta torres), en cualquier orden.
func TestR15L2ScoreIdsNoUnoAKNoOpina(t *testing.T) {
	validos := []string{"1", "2", "3"}
	invalidos := [][]string{{"bajo", "medio", "alto"}, {"alto", "medio", "bajo"}, {"0", "1", "2"}, {"1", "2", "4"}, {"01", "2", "3"}}
	l := l2Score(t, calibNiveles(3), append([][]string{validos}, invalidos...)...)
	r, err := l.Decidir(context.Background(), Pregunta{Texto: "s", Kind: KindScore, Opciones: opsIDs(validos...)})
	if err != nil || r.Conf == 0 {
		t.Fatalf("1..3 debía opinar: %+v %v", r, err)
	}
	for _, ids := range invalidos {
		r, err := l.Decidir(context.Background(), Pregunta{Texto: "s", Kind: KindScore, Opciones: opsIDs(ids...)})
		if err != nil || r.Conf != 0 || r.Answer != "" {
			t.Fatalf("%v: %+v %v, esperaba que no opinara", ids, r, err)
		}
	}
}

type casoScoreOrden struct {
	Caso     string   `json:"caso"`
	Opciones []string `json:"opciones"`
	Consulta string   `json:"consulta"`
	Error    bool     `json:"error"`
}

// (c) paridad con model/l2/modelo.py (testdata/gen_score_orden.py → score_orden.json): la torre de consulta es el nivel máximo
// sea cual sea el orden; con ids que no son 1..K Python rechaza y aquí la capa no opina.
func TestR15L2ScoreParidadPythonOrden(t *testing.T) {
	b, err := os.ReadFile("testdata/score_orden.json")
	if err != nil {
		t.Fatal(err)
	}
	var casos []casoScoreOrden
	if err := json.Unmarshal(b, &casos); err != nil || len(casos) == 0 {
		t.Fatal(err)
	}
	for _, c := range casos {
		ops := opsIDs(c.Opciones...)
		orden, ok := opcionesNiveles(ops)
		if c.Error {
			if ok {
				t.Fatalf("%s: Python rechaza y Go lo acepta como 1..K", c.Caso)
			}
			if got := OpcionesConsulta(Pregunta{Kind: KindScore, Opciones: ops}); got != nil {
				t.Fatalf("%s: sin 1..K no hay torre de consulta: %v", c.Caso, got)
			}
			continue
		}
		if !ok {
			t.Fatalf("%s: debía ser 1..K", c.Caso)
		}
		if got := OpcionesConsulta(Pregunta{Kind: KindScore, Opciones: ops})[0].ID; got != c.Consulta {
			t.Fatalf("%s: torre de consulta %q, Python %q", c.Caso, got, c.Consulta)
		}
		if orden[len(orden)-1].ID != c.Consulta || orden[0].ID != "1" {
			t.Fatalf("%s: orden de niveles %v", c.Caso, orden)
		}
	}
}
