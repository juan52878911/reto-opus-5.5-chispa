package decide

import (
	"context"
	"net/http/httptest"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func cascadaDe(t *testing.T, met *Metricas, ds ...Decisor) *Cascada {
	t.Helper()
	cfg := make([]Capa, len(ds))
	for i, d := range ds {
		cfg[i] = Capa{Nombre: d.Nombre(), Tau: 0.9}
	}
	c, err := NuevaCascada(cfg, ds, met)
	if err != nil {
		t.Fatal(err)
	}
	return c
}

// L2 sin torre (el .chispa no trae TORR) ante un esquema que ESQUEMAS no tiene: ninguna capa opina y la respuesta lo dice.
func TestEscalateReasonSinOpinionPorFaltaDeTorre(t *testing.T) {
	esq, _ := chispa3.DecodificarEsquemas(mustEsq(t))
	l2 := NuevoL2Con(sesionFalsa{[][]float32{{3, 0}}}, esq, chispa3.Calib{}, tokFalso{})
	met := NuevasMetricas()
	c := cascadaDe(t, met, l2)
	p := Pregunta{ID: "x", Texto: "esquema nuevo", Kind: KindChoice, Estado: "hola",
		Opciones: []Opcion{{ID: "a", Description: "r"}, {ID: "b", Description: "c"}}}
	r := c.Decidir(context.Background(), p)
	if !r.Escalate || r.EscalateReason != MotivoSinOpinion || len(r.Probs) != 0 {
		t.Fatalf("%+v", r)
	}
	m := metricasTexto(met)
	for _, want := range []string{`chispa_capa_no_opina_total{capa="L2",causa="sin_torre"} 1`, "chispa_sin_opinion_total 1"} {
		if !strings.Contains(m, want) {
			t.Fatalf("falta %q en:\n%s", want, m)
		}
	}
	if !l2.Activa() || l2.TorreAlVuelo() {
		t.Fatal("Activa/TorreAlVuelo")
	}
}

func TestEscalateReasonBajaConfianzaYScoreIds(t *testing.T) {
	met := NuevasMetricas()
	baja := &falso{n: "L1", r: Respuesta{Answer: "a", Probs: map[string]float64{"a": 0.5, "b": 0.5}, Conf: 0.5}}
	p := Pregunta{ID: "x", Kind: KindChoice, Estado: "h", Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	if r := cascadaDe(t, met, baja).Decidir(context.Background(), p); !r.Escalate || r.EscalateReason != MotivoBajaConfianza || len(r.Probs) == 0 {
		t.Fatalf("%+v", r)
	}
	nada := &falso{n: "L1"}
	ps := Pregunta{ID: "s", Kind: KindScore, Estado: "h", Opciones: []Opcion{{ID: "x"}, {ID: "y"}}}
	if r := cascadaDe(t, met, nada).Decidir(context.Background(), ps); r.EscalateReason != MotivoScoreIdsNoValidos {
		t.Fatalf("%+v", r)
	}
	// Una capa que falla no es «sin opinión»: lleva el motivo «incompleta», no «sin_opinión».
	rota := &falso{n: "L1", err: context.DeadlineExceeded}
	if r := cascadaDe(t, met, rota).Decidir(context.Background(), p); r.EscalateReason != MotivoIncompleta {
		t.Fatalf("%+v", r)
	}
	// Una decisión normal no lleva motivo.
	ok := &falso{n: "L1", r: Respuesta{Answer: "a", Probs: map[string]float64{"a": 1}, Conf: 1}}
	if r := cascadaDe(t, met, ok).Decidir(context.Background(), p); r.Escalate || r.EscalateReason != "" {
		t.Fatalf("%+v", r)
	}
}

func TestHealthzDiceLasCapas(t *testing.T) {
	c := cascadaDe(t, NuevasMetricas(), NuevoL0(4), &falso{n: "L1", r: Respuesta{}})
	cp := c.Capacidades()
	if cp.Capas["L0"] || !cp.Capas["L1"] || cp.TorreAlVuelo {
		t.Fatalf("%+v", cp)
	}
	srv := NuevoServidor(c, NuevasMetricas(), 8)
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, httptest.NewRequest("GET", "/healthz", nil))
	if b := rec.Body.String(); !strings.Contains(b, `"status":"ok"`) || !strings.Contains(b, `"torre_al_vuelo":false`) || !strings.Contains(b, `"L1":true`) {
		t.Fatal(b)
	}
}
