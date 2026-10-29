package decide

import (
	"bytes"
	"context"
	"fmt"
	"log"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

type simSinPresupuesto struct{}

func (simSinPresupuesto) Similitudes(context.Context, Pregunta) ([][]float32, []float64, bool, error) {
	return nil, nil, false, errSinPresupuestoTorres
}

func multiDe(texto string, n int) Pregunta {
	p := preguntaConOpciones(n)
	p.Texto, p.Kind = texto, KindMulti
	return p
}

// R11-3: un multi sin multi_l2 no calcula torres, y el presupuesto de la petición queda para el choice siguiente.
func TestR11MultiSinMultiL2NoGastaTorres(t *testing.T) {
	enc := &codificadorContador{}
	l := l2Torres(t, enc, 1024).ConMaxTorresNuevas(4)
	met := NuevasMetricas()
	l.UsaMetricas(met)
	ctx := conPresupuesto(context.Background())
	r, err := l.Decidir(ctx, multiDe("¿temas?", 4))
	if err != nil || r.Conf != 0 || r.Incompleto || enc.n.Load() != 0 {
		t.Fatalf("multi: %+v %v torres=%d", r, err, enc.n.Load())
	}
	r, err = l.Decidir(ctx, preguntaConOpciones(4))
	if err != nil || r.Incompleto || r.Answer == "" {
		t.Fatalf("choice tras multi sin presupuesto: %+v %v", r, err)
	}
	if met.MultiL2SinCalib.Load() != 1 {
		t.Fatalf("métrica sin_calib=%d", met.MultiL2SinCalib.Load())
	}
}

// R11-8: en L2c, la falta de presupuesto es Incompleto sin error (no cuenta como error de capa).
func TestR11L2cSinPresupuestoIncompleto(t *testing.T) {
	exacto(t)
	fx, conj, p := leerFixtureConj(t)
	esq, _ := chispa3.DecodificarEsquemas(mustEsq(t))
	l2c := NuevoL2cCon(NuevoL2Con(sesionFalsa{fx.Casos[1].S}, esq, chispa3.Calib{}, tokFalso{}), simSinPresupuesto{}, conj)
	r, err := l2c.DecidirCon(context.Background(), p, Previas{"L0": {Probs: fx.Casos[1].L0}})
	if err != nil || !r.Incompleto {
		t.Fatalf("%+v err=%v", r, err)
	}
}

func capturaLog(t *testing.T) *bytes.Buffer {
	var b bytes.Buffer
	log.SetOutput(&b)
	t.Cleanup(func() { log.SetOutput(log.Default().Writer()) })
	return &b
}

// R11-10: el aviso «sin multi_l2» sale una vez por modelo (L2), no una por proceso, y hay métrica.
func TestR11AvisoSinMultiL2PorModelo(t *testing.T) {
	b := capturaLog(t)
	p := multiDe("¿temas?", 2)
	met := NuevasMetricas()
	for i := 0; i < 2; i++ { // dos modelos: recarga
		l := l2Torres(t, &codificadorContador{}, 16)
		l.UsaMetricas(met)
		l.Decidir(context.Background(), p)
		l.Decidir(context.Background(), p)
	}
	if n := strings.Count(b.String(), "multi_l2"); n != 2 {
		t.Fatalf("avisos=%d, quería 2 (uno por modelo):\n%s", n, b)
	}
	if met.MultiL2SinCalib.Load() != 4 {
		t.Fatalf("sin_calib=%d", met.MultiL2SinCalib.Load())
	}
}

// R11-4: CALIB con claves multi@ que no casan con la pregunta: métrica y aviso.
func TestR11MultiCalibAusenteMetricaYAviso(t *testing.T) {
	b := capturaLog(t)
	entrenado := multiDe("¿temas?", 2)
	c := calibTiny()
	c.Tipos["multi"+ClaveCalibMulti(entrenado)] = chispa3.ParamsTipo{T: 1, A: 9, B: -1, Theta: 0.4}
	met := NuevasMetricas()
	base := multiCalibAusenteL1.Load()
	respuestaMulti(entrenado, []float64{1, 1}, c)
	if multiCalibAusenteL1.Load() != base {
		t.Fatal("el esquema entrenado no debe contar")
	}
	cambiado := entrenado
	cambiado.Texto += " "
	respuestaMulti(cambiado, []float64{1, 1}, c)
	respuestaMulti(cambiado, []float64{1, 1}, c)
	if multiCalibAusenteL1.Load() != base+2 || strings.Count(b.String(), "multi@") != 1 {
		t.Fatalf("ausente=%d log=%q", met.MultiCalibAusente.Load(), b)
	}
	var w bytes.Buffer
	met.Escribe(&w)
	if !strings.Contains(w.String(), fmt.Sprintf("chispa_multi_calib_ausente_total %d", base+2)) || !strings.Contains(w.String(), "chispa_multi_l2_sin_calib_total") {
		t.Fatal("faltan métricas en /metrics")
	}
}

// R11-14: el índice se calcula una vez al cargar.
func TestR11IndiceCalibAlCargar(t *testing.T) {
	c := calibTiny()
	c.Tipos["multi_l2@abc"] = chispa3.ParamsTipo{T: 1}
	l := NuevoL2Con(sesionFalsa{}, nil, c, tokFalso{})
	if !l.multi.porEsquema || !l.multi.l2Esquema || l.multi.l1Esquema {
		t.Fatalf("%+v", &l.multi)
	}
}
