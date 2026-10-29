package decide

import (
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
