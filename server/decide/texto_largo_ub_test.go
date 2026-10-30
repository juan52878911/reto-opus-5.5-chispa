package decide

import (
	"context"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// tokTrozosFalso trocea el texto en palabras: una ventana por palabra, tantas como tenga (el texto largo).
type tokTrozosFalso struct{}

func (tokTrozosFalso) IDs(string) []int64 { return []int64{0, 5, 2} }
func (tokTrozosFalso) Trozos(texto string, tl TextoLargo) ([][]int64, bool) {
	ws := strings.Fields(texto)
	out := make([][]int64, 0, len(ws))
	for range ws {
		out = append(out, []int64{0, 5, 2})
	}
	if tl.Estrategia != "trozos" {
		return out[:1], len(ws) > 1
	}
	return out[:min(len(out), tl.Trozos())], len(ws) > 1
}

func l2TrozosFalso(t *testing.T, maxTrozos int) (*L2, *sesionCuenta, *Metricas) {
	t.Helper()
	es, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{
		ent("q", []string{"a"}, 0.5, 10, 0),
		ent("q", []string{"b"}, 0.5, 0, 10),
	})
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(es)
	if err != nil {
		t.Fatal(err)
	}
	cal := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 1, Theta: 0.5}}}
	ses := &sesionCuenta{}
	l2 := NuevoL2Con(ses, esq, cal, tokTrozosFalso{}).ConTextoLargo(TextoLargo{Estrategia: "trozos", MaxTrozos: maxTrozos})
	met := NuevasMetricas()
	l2.UsaMetricas(met)
	return l2, ses, met
}

func preguntaQ(estado string) Pregunta {
	return Pregunta{Texto: "q", Kind: KindChoice, Estado: estado, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
}

// Una petición con muchas preguntas sobre el mismo texto largo corre el ONNX una vez por ventana (no por pregunta) y cuenta el
// texto una sola vez en /metrics.
func TestTextoLargoL2UnaPasadaPorPeticion(t *testing.T) {
	largo := strings.Repeat("palabra ", 50)
	l2, ses, met := l2TrozosFalso(t, 3)
	ctx := conPresupuesto(context.Background())
	for i := 0; i < 20; i++ {
		if _, err := l2.Decidir(ctx, preguntaQ(largo)); err != nil {
			t.Fatal(err)
		}
	}
	if ses.n != 3 || met.TextoLargoL2.Load() != 1 || met.TrozosL2.Load() != 3 {
		t.Fatalf("20 preguntas: %d pasadas de ONNX, métricas %d/%d (esperado 3, 1/3)", ses.n, met.TextoLargoL2.Load(), met.TrozosL2.Load())
	}
	// otra petición vuelve a tener presupuesto
	if _, err := l2.Decidir(conPresupuesto(context.Background()), preguntaQ(largo)); err != nil {
		t.Fatal(err)
	}
	if ses.n != 6 || met.TextoLargoL2.Load() != 2 {
		t.Fatalf("segunda petición: %d pasadas, %d textos", ses.n, met.TextoLargoL2.Load())
	}
}

// max_trozos es de la petición: un segundo texto largo, con el presupuesto ya gastado, solo decide su cabeza.
func TestTextoLargoL2PresupuestoCompartidoEntreTextos(t *testing.T) {
	l2, ses, met := l2TrozosFalso(t, 3)
	ctx := conPresupuesto(context.Background())
	l2.Decidir(ctx, preguntaQ(strings.Repeat("a ", 50)))
	l2.Decidir(ctx, preguntaQ(strings.Repeat("b ", 50)))
	if ses.n != 4 || met.TrozosL2.Load() != 4 || met.TextoLargoL2.Load() != 2 {
		t.Fatalf("%d pasadas, métricas %d/%d (esperado 3 + la cabeza del segundo)", ses.n, met.TextoLargoL2.Load(), met.TrozosL2.Load())
	}
}

// L1: un texto largo con 10 preguntas suma 1 texto, y sus ventanas se cobran del mismo presupuesto que L2.
func TestTextoLargoL1UnaVezPorPeticion(t *testing.T) {
	l1 := l1Largo(t, &TextoLargo{Estrategia: "trozos", Agregacion: "max", VentanaL1: 4, MaxTrozos: 3})
	met := NuevasMetricas()
	l1.UsaMetricas(met)
	largo := strings.Repeat("pedido dinero pago ", 150)
	ctx := conPresupuesto(context.Background())
	for i := 0; i < 10; i++ {
		for _, q := range preguntasL1(largo) {
			if _, err := l1.Decidir(ctx, q); err != nil {
				t.Fatal(err)
			}
		}
	}
	if met.TextoLargoL1.Load() != 1 || met.TrozosL1.Load() != 3 {
		t.Fatalf("L1: textos %d, ventanas %d (esperado 1 y 3)", met.TextoLargoL1.Load(), met.TrozosL1.Load())
	}
	if got := presupuestoDe(ctx).cupoTrozos(3); got != 1 {
		t.Fatalf("el presupuesto no se compartió: cupo %d", got)
	}
}
