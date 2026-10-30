package decide

import (
	"testing"

	"chispa/format/chispa3"
)

func l2NoulFalso(t *testing.T, tk Tokenizador) *L2 {
	t.Helper()
	es, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("n", []string{"false", "true"}, 1, 2, 1)})
	if err != nil {
		t.Fatal(err)
	}
	esq, err := chispa3.DecodificarEsquemas(es)
	if err != nil {
		t.Fatal(err)
	}
	cal := chispa3.Calib{TauEscalate: 0.5, Tipos: map[string]chispa3.ParamsTipo{"noul": {T: 1, A: 1, B: -1, Theta: 0.5}}}
	return NuevoL2Con(sesionTexto{}, esq, cal, tk)
}
