package chispamovil

import (
	"context"
	"math"
	"os"
	"strconv"
	"testing"

	"chispa/format/chispa3"

	"github.com/juan52878911/chispa/server/decide"
)

// Paridad servidor ↔ móvil con el CALIB escrito con la convención del exportador (a_calib_chispa: «scoreK#j», j = 1..K−2).
func TestScoreCoralFixtureExportadorParidadServidor(t *testing.T) {
	raw, err := os.ReadFile("../../../server/decide/testdata/calib_coral.json")
	if err != nil {
		t.Fatal(err)
	}
	cal, err := chispa3.DecodificarCalib(raw)
	if err != nil {
		t.Fatal(err)
	}
	esq, _ := chispa3.DecodificarEsquemas(mustEsq())
	srv := decide.NuevoL2Con(sesFalsa{[][]float32{{0, 0, 0, 0}}}, esq, cal, tokFalso{}).ConTorres(torreCero{}, 64)
	c := &Chispa{calib: cal}
	for _, K := range []int{3, 5} {
		var ops []opcion
		var dops []decide.Opcion
		for i := 1; i <= K; i++ {
			ops = append(ops, opcion{ID: strconv.Itoa(i)})
			dops = append(dops, decide.Opcion{ID: strconv.Itoa(i)})
		}
		got := c.score(pregunta{Kind: "score", Opciones: ops}, sCero)
		if !got.Ok {
			t.Fatalf("K=%d: el móvil no opinó con las claves del exportador", K)
		}
		want, err := srv.Decidir(context.Background(), decide.Pregunta{ID: "q", Estado: "x", Texto: "Gravedad", Kind: decide.KindScore, Opciones: dops})
		if err != nil || want.Conf == 0 {
			t.Fatalf("K=%d: el servidor no opinó: %+v %v", K, want, err)
		}
		if want.Answer != got.Answer {
			t.Fatalf("K=%d: servidor %q ≠ móvil %q", K, want.Answer, got.Answer)
		}
		for id, v := range want.Probs {
			if math.Abs(got.Probs[id]-v) > 1e-9 {
				t.Fatalf("K=%d probs[%s]: móvil %v ≠ servidor %v", K, id, got.Probs[id], v)
			}
		}
	}
}
