package decide

import (
	"context"
	"math"
	"strings"
	"testing"
)

// La misma petición da Probs idénticos bit a bit: ninguna suma ni normalización recorre un map.
func TestTextoLargoDeterminismoBitABit(t *testing.T) {
	largo := strings.Join([]string{"factura cobro pago dinero", "hola gracias hola gracias", "paquete retraso envio pedido"}, " ")
	qs := append(preguntasL1(largo), Pregunta{Kind: KindMulti, Texto: "¿Qué áreas?", Opciones: opsReembolso(), Estado: largo})
	for _, agg := range []string{"max", "media"} {
		l := l1Largo(t, &TextoLargo{Estrategia: "trozos", Agregacion: agg, VentanaL1: 4})
		for _, q := range qs {
			ref, err := l.Decidir(context.Background(), q)
			if err != nil {
				t.Fatal(err)
			}
			for i := 0; i < 50; i++ {
				got, err := l.Decidir(context.Background(), q)
				if err != nil {
					t.Fatal(err)
				}
				if got.Answer != ref.Answer || len(got.Probs) != len(ref.Probs) {
					t.Fatalf("%s %s: %+v ≠ %+v", agg, q.Kind, got, ref)
				}
				for id, v := range ref.Probs {
					if math.Float64bits(got.Probs[id]) != math.Float64bits(v) {
						t.Fatalf("%s %s rep %d: probs[%s] %v ≠ %v", agg, q.Kind, i, id, got.Probs[id], v)
					}
				}
			}
		}
	}
}
