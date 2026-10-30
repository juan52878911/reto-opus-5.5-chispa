package chispamovil

import (
	"encoding/json"
	"fmt"
	"math"
	"math/rand"
	"strconv"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

const semillaCalib = 20261029

func opcionesN(k int) []opcion {
	o := make([]opcion, k)
	for i := range o {
		o[i] = opcion{ID: strconv.Itoa(i + 1)}
	}
	return o
}

func paramsAlea(r *rand.Rand) chispa3.ParamsTipo {
	return chispa3.ParamsTipo{T: 0.01 + r.Float64()*2, A: (r.Float64() - 0.2) * 30, B: (r.Float64() - 0.5) * 20, Theta: r.Float64()}
}

func simsAlea(r *rand.Rand, k int, escala float64) []float64 {
	s := make([]float64, k)
	for i := range s {
		s[i] = (r.Float64()*2 - 1) * escala
	}
	return s
}

func compruebaProbs(t *testing.T, ctx string, r respuesta, sumaUno bool) {
	t.Helper()
	var s float64
	for id, v := range r.Probs {
		if !(v >= 0 && v <= 1) {
			t.Fatalf("%s: prob[%s]=%v fuera de [0,1]", ctx, id, v)
		}
		s += v
	}
	if sumaUno && math.Abs(s-1) > 1e-9 {
		t.Fatalf("%s: las probs suman %v", ctx, s)
	}
	if !(r.Conf >= 0 && r.Conf <= 1) {
		t.Fatalf("%s: conf %v", ctx, r.Conf)
	}
}

// choice y score suman 1; noul también y sus dos probs están en [0,1]; multi: cada opción en [0,1]. Capa L1 y L2, con entradas aleatorias.
func TestCalibPropiedadProbabilidades(t *testing.T) {
	r := rand.New(rand.NewSource(semillaCalib))
	for it := 0; it < 2000; it++ {
		escala := []float64{0.01, 1, 50, 800}[r.Intn(4)]
		k := 2 + r.Intn(6)
		ctx := fmt.Sprintf("it=%d k=%d escala=%g", it, k, escala)
		p := pregunta{Kind: "choice", Opciones: opcionesN(k)}
		prm := paramsAlea(r)

		compruebaProbs(t, ctx+" choice", softmax(p, simsAlea(r, k, escala), prm.T), true)
		compruebaProbs(t, ctx+" score L1", puntuarNiveles(pregunta{Kind: "score", Opciones: p.Opciones}, simsAlea(r, k, escala), prm.T), true)
		compruebaProbs(t, ctx+" noul", noul(prm.A*simsAlea(r, 1, escala)[0]+prm.B, prm.Theta), true)

		cal := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"score" + strconv.Itoa(k): prm}}
		for j := 1; j < k-1; j++ {
			cal.Tipos[fmt.Sprintf("score%d#%d", k, j)] = chispa3.ParamsTipo{A: (r.Float64() - 0.5) * 6}
		}
		c := &Chispa{calib: cal}
		rs := c.score(pregunta{Kind: "score", Opciones: p.Opciones}, simsAlea(r, 1, escala)[0])
		if len(rs.Probs) != k {
			t.Fatalf("%s: score L2 sin respuesta", ctx)
		}
		compruebaProbs(t, ctx+" score L2", rs, true)

		pm := pregunta{Kind: "multi", Opciones: p.Opciones}
		calM := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"noul": paramsAlea(r), "multi": paramsAlea(r), "multi_l2": paramsAlea(r)}}
		for _, o := range pm.Opciones {
			if r.Intn(2) == 0 {
				calM.Tipos["multi#"+o.ID] = paramsAlea(r)
				calM.Tipos["multi_l2#"+o.ID] = paramsAlea(r)
			}
		}
		cm := &Chispa{calib: calM}
		for capa, resp := range map[string]respuesta{"L1": cm.multi(pm, simsAlea(r, k, escala)), "L2": cm.multiL2(pm, simsAlea(r, k, escala))} {
			if len(resp.Probs) != k {
				t.Fatalf("%s: multi %s con %d probs", ctx, capa, len(resp.Probs))
			}
			compruebaProbs(t, ctx+" multi "+capa, resp, false)
		}
	}
}

// Subir τ nunca convierte una escalada en aceptada: la regla de la app (opina y conf ≥ τ) sobre las respuestas reales del SDK.
func TestCalibPropiedadMonotoniaTau(t *testing.T) {
	r := rand.New(rand.NewSource(semillaCalib + 1))
	acepta := func(x respuesta, tau float64) bool { return x.Opina && x.Conf > 0 && x.Conf >= tau }
	for it := 0; it < 2000; it++ {
		k := 2 + r.Intn(5)
		p := pregunta{Kind: "choice", Opciones: opcionesN(k)}
		prm := paramsAlea(r)
		rs := []respuesta{softmax(p, simsAlea(r, k, 3), prm.T), noul(prm.A*r.Float64()+prm.B, prm.Theta)}
		t1 := r.Float64()
		t2 := t1 + r.Float64()*(1-t1)
		for _, x := range rs {
			if !acepta(x, t1) && acepta(x, t2) {
				t.Fatalf("it=%d: escalaba con τ=%g y acepta con τ=%g (conf %g)", it, t1, t2, x.Conf)
			}
		}
	}
}

func TestCalibVistaAvisoYDefecto(t *testing.T) {
	c := &Chispa{tieneL2: true, calib: chispa3.Calib{
		Tipos:       map[string]chispa3.ParamsTipo{"choice": {T: 0.3, A: 1, B: 2, Theta: 0.4}, "noul": {T: 1, A: 5, B: -1, Theta: 0.7}},
		TiposL2:     map[string]chispa3.ParamsTipo{"choice": {T: 0.9}},
		TauEscalate: 0.8,
	}}
	c.avisarCalib()
	av := c.Avisos()
	if !strings.Contains(av, "CALIB de L1 sin los tipos [score multi]") || !strings.Contains(av, "CALIB de L2 sin los tipos [noul score multi]") {
		t.Fatalf("avisos: %q", av)
	}
	var vs []vistaCalib
	if err := json.Unmarshal([]byte(c.CalibJSON()), &vs); err != nil || len(vs) != 2 {
		t.Fatalf("CalibJSON: %v %s", err, c.CalibJSON())
	}
	for _, e := range vs[1].Entradas {
		if e.Tipo == "noul" && (e.Origen != origenDefecto || e.A != 4) {
			t.Fatalf("noul de L2: %+v", e)
		}
		if e.Tipo == "choice" && (e.Origen != origenTiposL2 || e.T != 0.9) {
			t.Fatalf("choice de L2: %+v", e)
		}
	}
	c.paramsL2("noul")
	c.paramsL2("noul")
	c.paramsL2("choice")
	c.params("noul")
	if got := c.CalibDefectoJSON(); got != `[{"capa":"L2","tipo":"noul","n":2}]` {
		t.Fatalf("CalibDefectoJSON = %s", got)
	}
}
