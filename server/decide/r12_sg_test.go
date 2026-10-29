package decide

import (
	"context"
	"testing"

	"chispa/format/chispa3"
)

// R12-H7: las respuestas de L2 base que L2c da de respaldo (sin probabilidades de L0, sin entrada en CONJ…) se cortan con
// tau_escalate_l2 y no con tau_l2c, el τ de la cabeza conjunta. Las de la cabeza siguen con tau_l2c.
func TestL2cRespaldoUsaTauEscalateL2(t *testing.T) {
	exacto(t)
	fx, conj, p := leerFixtureConj(t)
	c := fx.Casos[1]
	esq, _ := chispa3.DecodificarEsquemas(mustEsq(t))
	tauCabeza, tauL2 := 0.2, 0.999
	calib := chispa3.Calib{TauEscalate: 0.5, TauEscalateL2: &tauL2, TauL2c: &tauCabeza, Tipos: map[string]chispa3.ParamsTipo{"choice": {T: 1}}}.ParaL2()
	armar := func() *Cascada {
		l2c := NuevoL2cCon(NuevoL2Con(sesionFalsa{c.S}, esq, calib, tokFalso{}), &simFalsa{S: c.S, sims: c.Sims}, conj)
		casc, err := NuevaCascada([]Capa{{Nombre: "L0", Tau: 0.9}, {Nombre: "L2", Tau: tauCabeza}}, []Decisor{decisorFijo{"L0", Respuesta{Answer: "x", Probs: c.L0, Conf: 0.1}}, l2c}, NuevasMetricas())
		if err != nil {
			t.Fatal(err)
		}
		return casc
	}
	if r := armar().Decidir(context.Background(), p); r.Layer != "L2" || r.Escalate {
		t.Fatalf("la cabeza conjunta debe decidir con tau_l2c: %+v", r)
	}
	// Sin entrada en CONJ para la pregunta: respaldo de L2 base (p(a) ≈ 0,976: pasa tau_l2c=0,2 y no tau_escalate_l2=0,999).
	es2, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("q", []string{"a"}, 0.5, 10, 0), ent("q", []string{"b"}, 0.5, 0, 10)})
	if err != nil {
		t.Fatal(err)
	}
	esq2, _ := chispa3.DecodificarEsquemas(es2)
	q := Pregunta{Texto: "q", Kind: KindChoice, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	cascada := func(tau float64) *Cascada {
		l2c := NuevoL2cCon(NuevoL2Con(sesionFalsa{[][]float32{{1, 0}, {0, 0.2}}}, esq2, calib, tokFalso{}), &simFalsa{S: c.S, sims: c.Sims}, conj)
		casc, err := NuevaCascada([]Capa{{Nombre: "L0", Tau: 0.9}, {Nombre: "L2", Tau: tau}}, []Decisor{decisorFijo{"L0", Respuesta{Conf: 0.1}}, l2c}, NuevasMetricas())
		if err != nil {
			t.Fatal(err)
		}
		return casc
	}
	if r := cascada(tauCabeza).Decidir(context.Background(), q); r.Layer != CapaEscalar || !r.Escalate || r.Answer != "a" {
		t.Fatalf("el respaldo de L2 base debía cortarse con tau_escalate_l2=%v (no con tau_l2c=%v): %+v", tauL2, tauCabeza, r)
	}
	// un τ de L2 fijado a mano en la config (distinto de tau_l2c) manda también sobre el respaldo
	if r := cascada(0.3).Decidir(context.Background(), q); r.Layer != "L2" || r.Escalate {
		t.Fatalf("τ explícito de la config: %+v", r)
	}
}
