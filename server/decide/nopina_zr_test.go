package decide

import (
	"context"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func opsScore(k int) []Opcion {
	o := make([]Opcion, k)
	for i := range o {
		o[i] = Opcion{ID: string(rune('1' + i))}
	}
	return o
}

// ZR-3: capas sin modelo (Stub, L0 vacío) cuentan «sin_modelo», no «sin_opinion» ni «esquema_no_entrenado».
func TestZRCapasSinModeloCuentanSinModelo(t *testing.T) {
	met := NuevasMetricas()
	c := cascadaDe(t, met, NuevoL0(8), NuevoL1(), NuevoL3())
	p := Pregunta{ID: "x", Texto: "hola", Kind: KindChoice, Estado: "e", Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	r := c.Decidir(context.Background(), p)
	if !r.Escalate || r.EscalateReason != MotivoSinOpinion {
		t.Fatalf("%+v", r)
	}
	m := metricasTexto(met)
	for _, capa := range []string{"L0", "L1", "L3"} {
		if !strings.Contains(m, `chispa_capa_no_opina_total{capa="`+capa+`",causa="sin_modelo"} 1`) {
			t.Fatalf("falta sin_modelo de %s en:\n%s", capa, m)
		}
	}
	if strings.Contains(m, `causa="sin_opinion"} 1`) || strings.Contains(m, `causa="esquema_no_entrenado"} 1`) {
		t.Fatalf("causa equivocada:\n%s", m)
	}
}

// ZR-4: score 1..K sin cabeza «scoreK» (o sin algún «#j») en CALIB: tipo_no_soportado.
// (con torre al vuelo: sin ella, un esquema nuevo cuenta sin_torre, que es la causa de fondo)
func TestZRScoreSinCabezaTipoNoSoportado(t *testing.T) {
	esq, _ := chispa3.DecodificarEsquemas(mustEsq(t))
	calib := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"score3": {T: 1, A: 1}, "score3#1": {A: 1}}}
	l2 := NuevoL2Con(sesionFalsa{[][]float32{{3, 0}}}, esq, calib, tokFalso{}).ConTorres(codTorreDorada{}, 16)
	score := func(k int) Pregunta { return Pregunta{ID: "s", Kind: KindScore, Estado: "e", Opciones: opsScore(k)} }
	if got := l2.CausaNoOpina(score(7)); got != CausaTipoNoSoportado {
		t.Fatalf("score7 sin cabeza: %s", got)
	}
	if got := l2.CausaNoOpina(score(4)); got != CausaTipoNoSoportado { // score4 no existe
		t.Fatalf("score4: %s", got)
	}
	if !l2.scoreCalibrado(3) {
		t.Fatal("score3 completo debe estar calibrado")
	}
	delete(calib.Tipos, "score3#1")
	if got := l2.CausaNoOpina(score(3)); got != CausaTipoNoSoportado {
		t.Fatalf("score3 sin #1: %s", got)
	}
}

// ZR-2: capa fallida o sin presupuesto y nadie más opina: motivo «incompleta», no «sin_opinion».
func TestZREscaladaIncompletaTieneMotivoPropio(t *testing.T) {
	met := NuevasMetricas()
	p := Pregunta{ID: "x", Kind: KindChoice, Estado: "e", Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	r := cascadaDe(t, met, &falso{n: "L1"}, &falso{n: "L3", err: context.DeadlineExceeded}).Decidir(context.Background(), p)
	if !r.Escalate || r.EscalateReason != MotivoIncompleta || len(r.Probs) != 0 {
		t.Fatalf("%+v", r)
	}
	if strings.Contains(metricasTexto(met), "chispa_sin_opinion_total 1") {
		t.Fatal("no es «nadie opinó»")
	}
}
