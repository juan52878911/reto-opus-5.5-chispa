package decide

import (
	"context"
	"math"
	"testing"

	"chispa/format/chispa3"
)

// R10-8: la CALIB de multi se indexa por esquema y opción. Un esquema nuevo con una opción «si» no hereda el θ ni la a, b de otro.
func TestMultiCalibPorEsquema(t *testing.T) {
	entrenado := Pregunta{Texto: "¿temas?", Kind: KindMulti, Opciones: []Opcion{{ID: "si"}, {ID: "otro"}}}
	nuevo := Pregunta{Texto: "¿urgente?", Kind: KindMulti, Opciones: []Opcion{{ID: "si"}, {ID: "no"}}}
	e := ClaveCalibMulti(entrenado)
	if e == ClaveCalibMulti(nuevo) {
		t.Fatal("esquemas distintos, misma clave")
	}
	c := calibTiny()
	c.Tipos["multi"+e] = chispa3.ParamsTipo{T: 1, A: 9, B: -1, Theta: 0.4}
	c.Tipos["multi"+e+"#si"] = chispa3.ParamsTipo{T: 1, A: 9, B: -1, Theta: 0.9}
	if p := paramsMulti(c, "multi", e, "si"); p.Theta != 0.9 {
		t.Fatalf("esquema entrenado, θ por opción: %+v", p)
	}
	if p := paramsMulti(c, "multi", e, "otro"); p.Theta != 0.4 {
		t.Fatalf("esquema entrenado, a, b del esquema: %+v", p)
	}
	if p := paramsMulti(c, "multi", ClaveCalibMulti(nuevo), "si"); p != c.Tipos["noul"] {
		t.Fatalf("esquema nuevo debe caer a noul: %+v", p)
	}
	// ficheros antiguos (claves sin esquema) siguen valiendo
	v := calibTiny()
	v.Tipos["multi"] = chispa3.ParamsTipo{T: 1, A: 5, B: -1, Theta: 0.4}
	v.Tipos["multi#si"] = chispa3.ParamsTipo{T: 1, A: 5, B: -1, Theta: 0.9}
	if p := paramsMulti(v, "multi", ClaveCalibMulti(nuevo), "si"); p.Theta != 0.9 {
		t.Fatalf("CALIB antigua sigue aplicándose: %+v", p)
	}
	// y la respuesta de verdad: el esquema nuevo no usa el θ 0,999 del entrenado
	c.Tipos["multi"+e+"#si"] = chispa3.ParamsTipo{T: 1, A: 9, B: -1, Theta: 0.999}
	r := respuestaMulti(nuevo, []float64{1, 1}, c)
	n := c.Tipos["noul"]
	if pr := 1 / (1 + math.Exp(-(n.A + n.B))); r.Probs["si"] != pr {
		t.Fatalf("esquema nuevo no usa su CALIB: %v", r.Probs)
	}
}

// R10-5: sin CALIB multi_l2 del esquema, L2 no opina en multi (antes decidía con la de noul y marcaba casi todo activo).
func TestL2MultiSinCalibNoOpina(t *testing.T) {
	p := Pregunta{Texto: "¿temas?", Kind: KindMulti, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	c := calibTiny()
	if r := respuestaMultiL2(p, []float64{5, 5}, c); r.Conf != 0 || len(r.Probs) != 0 {
		t.Fatalf("debía no opinar: %+v", r)
	}
	e := ClaveCalibMulti(p)
	c.Tipos["multi_l2"+e] = chispa3.ParamsTipo{T: 1, A: 2, B: -3, Theta: 0.5}
	if r := respuestaMultiL2(p, []float64{5, 5}, c); r.Conf == 0 || len(r.Probs) != 2 {
		t.Fatalf("con multi_l2 del esquema debe opinar: %+v", r)
	}
	otro := Pregunta{Texto: "otra", Kind: KindMulti, Opciones: p.Opciones}
	if r := respuestaMultiL2(otro, []float64{5, 5}, c); r.Conf != 0 {
		t.Fatalf("otro esquema no hereda multi_l2: %+v", r)
	}
}

// Una multi escalada devuelve la mejor pista con probs por opción: L1 opina pero no llega a su τ y L2 no opina (sin multi_l2).
func TestMultiEscaladaDevuelveProbsDeLaMejorPista(t *testing.T) {
	cfg := ConfigPorDefecto()
	for i := range cfg.Capas {
		if cfg.Capas[i].Nombre == "L1" {
			cfg.Capas[i].Tau = 1
		}
	}
	casc, _ := cascadaTiny(t, calibMulti(), cfg)
	p := Pregunta{ID: "m", Kind: KindMulti, Texto: "¿Qué temas toca?", Estado: "quiero un reembolso de la factura", Opciones: opsMulti()}
	res := casc.Decidir(context.Background(), p)
	if !res.Escalate || res.Layer != CapaEscalar || len(res.Probs) != len(p.Opciones) {
		t.Fatalf("debía escalar con una p por opción: %+v", res)
	}
	for id, x := range res.Probs {
		if x < 0 || x > 1 {
			t.Fatalf("%s: p fuera de [0,1]: %v", id, x)
		}
	}
}
