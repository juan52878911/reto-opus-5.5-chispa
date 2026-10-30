package decide

import (
	"context"
	"fmt"
	"math"
	"math/rand"
	"strconv"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

const semillaCalib = 20261029

func opcionesN(k int) []Opcion {
	o := make([]Opcion, k)
	for i := range o {
		o[i] = Opcion{ID: strconv.Itoa(i + 1)}
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

func sumaProbs(p map[string]float64) (s float64) {
	for _, v := range p {
		s += v
	}
	return
}

func enUnidad(t *testing.T, ctx string, p map[string]float64) {
	t.Helper()
	for id, v := range p {
		if !(v >= 0 && v <= 1) || math.IsNaN(v) {
			t.Fatalf("%s: prob[%s]=%v fuera de [0,1]", ctx, id, v)
		}
	}
}

// Probabilidades de choice y score en L1 y L2 (suman 1), noul (suma 1 y en [0,1]) y multi (cada una en [0,1]), con CALIB y entradas aleatorias.
func TestCalibPropiedadProbabilidades(t *testing.T) {
	r := rand.New(rand.NewSource(semillaCalib))
	for it := 0; it < 2000; it++ {
		escala := []float64{0.01, 1, 50, 800}[r.Intn(4)] // incluye puntuaciones extremas: sin NaN ni desbordes
		k := 2 + r.Intn(6)
		ctx := fmt.Sprintf("it=%d k=%d escala=%g", it, k, escala)
		p := Pregunta{Kind: KindChoice, Opciones: opcionesN(k)}
		prm := paramsAlea(r)

		// choice y score de L1: softmax(sim/T)
		rc := respuestaSoftmax(p, simsAlea(r, k, escala), prm.T)
		if d := math.Abs(sumaProbs(rc.Probs) - 1); d > 1e-9 {
			t.Fatalf("%s: choice L1 suma %v", ctx, sumaProbs(rc.Probs))
		}
		enUnidad(t, ctx+" choice", rc.Probs)
		ps := p
		ps.Kind = KindScore
		rs := respuestaScore(ps, simsAlea(r, k, escala), prm.T)
		if d := math.Abs(sumaProbs(rs.Probs) - 1); d > 1e-9 {
			t.Fatalf("%s: score L1 suma %v", ctx, sumaProbs(rs.Probs))
		}
		enUnidad(t, ctx+" score L1", rs.Probs)

		// noul (L1 y L2 comparten respuestaNoul)
		rn := respuestaNoul(prm.A*simsAlea(r, 1, escala)[0]+prm.B, prm.Theta)
		if d := math.Abs(sumaProbs(rn.Probs) - 1); d > 1e-9 {
			t.Fatalf("%s: noul suma %v", ctx, sumaProbs(rn.Probs))
		}
		enUnidad(t, ctx+" noul", rn.Probs)
		if !(rn.Conf >= 0 && rn.Conf <= 1) {
			t.Fatalf("%s: conf noul %v", ctx, rn.Conf)
		}

		// score de L2 (CORAL): scoreK, scoreK#j con incrementos aleatorios, también no monótonos
		cal := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"score" + strconv.Itoa(k): prm}}
		for j := 1; j < k-1; j++ {
			cal.Tipos[fmt.Sprintf("score%d#%d", k, j)] = chispa3.ParamsTipo{A: (r.Float64() - 0.5) * 6}
		}
		l2 := NuevoL2Con(nil, nil, cal, nil)
		r2, err := l2.score(ps, simsAlea(r, 1, escala)[0])
		if err != nil || r2.Probs == nil {
			t.Fatalf("%s: score L2 sin respuesta (%v)", ctx, err)
		}
		if d := math.Abs(sumaProbs(r2.Probs) - 1); d > 1e-9 {
			t.Fatalf("%s: score L2 suma %v", ctx, sumaProbs(r2.Probs))
		}
		enUnidad(t, ctx+" score L2", r2.Probs)

		// multi: L1 («multi») y L2 («multi_l2»), cada opción en [0,1]
		pm := Pregunta{Kind: KindMulti, Opciones: opcionesN(k)}
		calM := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"noul": paramsAlea(r), "multi": paramsAlea(r), "multi_l2": paramsAlea(r)}}
		for _, o := range pm.Opciones {
			if r.Intn(2) == 0 {
				calM.Tipos["multi#"+o.ID] = paramsAlea(r)
				calM.Tipos["multi_l2#"+o.ID] = paramsAlea(r)
			}
		}
		for capa, resp := range map[string]Respuesta{
			"L1": respuestaMulti(pm, simsAlea(r, k, escala), calM),
			"L2": respuestaMultiL2(pm, simsAlea(r, k, escala), calM),
		} {
			if resp.Probs == nil {
				t.Fatalf("%s: multi %s sin respuesta", ctx, capa)
			}
			enUnidad(t, ctx+" multi "+capa, resp.Probs)
			if len(resp.Probs) != k {
				t.Fatalf("%s: multi %s con %d probs", ctx, capa, len(resp.Probs))
			}
		}
	}
}

// decisorCalibFijo devuelve siempre la misma respuesta.
type decisorCalibFijo struct {
	nombre string
	r      Respuesta
}

func (d decisorCalibFijo) Nombre() string { return d.nombre }
func (d decisorCalibFijo) Decidir(context.Context, Pregunta) (Respuesta, error) {
	return d.r, nil
}

// Subir τ nunca convierte una escalada en aceptada, ni hace que una capa más temprana acepte donde antes aceptaba otra posterior:
// con τ' ≥ τ (capa a capa), escalar con τ implica escalar con τ'; y la capa que acepta con τ' es la misma o posterior a la de τ.
func TestCalibPropiedadMonotoniaTau(t *testing.T) {
	r := rand.New(rand.NewSource(semillaCalib + 1))
	orden := map[string]int{"L1": 0, "L2": 1, CapaEscalar: 2}
	for it := 0; it < 3000; it++ {
		p := Pregunta{ID: "q", Kind: KindChoice, Texto: "x", Opciones: opcionesN(3)}
		l1 := Respuesta{Answer: "1", Conf: r.Float64(), Probs: map[string]float64{"1": 1}}
		l2 := Respuesta{Answer: "2", Conf: r.Float64(), Probs: map[string]float64{"2": 1}, EsquemaNuevo: r.Intn(2) == 0}
		if r.Intn(5) == 0 {
			l1 = Respuesta{} // no opina
		}
		t1, t2 := r.Float64(), r.Float64()
		d1, d2 := r.Float64()*(1-t1), r.Float64()*(1-t2)
		tn := r.Float64()
		dn := r.Float64() * (1 - tn)
		corre := func(a, b, nuevo float64) Resultado {
			n := nuevo
			c, err := NuevaCascadaConTauNuevo([]Capa{{"L1", a}, {"L2", b}}, []Decisor{decisorCalibFijo{"L1", l1}, decisorCalibFijo{"L2", l2}}, NuevasMetricas(), &n)
			if err != nil {
				t.Fatal(err)
			}
			return c.Decidir(context.Background(), p)
		}
		bajo, alto := corre(t1, t2, tn), corre(t1+d1, t2+d2, tn+dn)
		if bajo.Escalate && !alto.Escalate {
			t.Fatalf("it=%d: escalaba con τ=(%g,%g,%g) y acepta con τ=(%g,%g,%g): %+v → %+v", it, t1, t2, tn, t1+d1, t2+d2, tn+dn, bajo, alto)
		}
		if orden[alto.Layer] < orden[bajo.Layer] {
			t.Fatalf("it=%d: al subir τ decide una capa anterior (%s → %s)", it, bajo.Layer, alto.Layer)
		}
	}
}

// Los valores calibrados de cada tipo que sirve cada capa son los de CALIB, y los que faltan salen como default y suben el contador.
func TestCalibVistaOrigenYDefecto(t *testing.T) {
	cal := chispa3.Calib{
		Tipos:       map[string]chispa3.ParamsTipo{"choice": {T: 0.3, A: 1, B: 2, Theta: 0.4}, "noul": {T: 1, A: 5, B: -1, Theta: 0.7}},
		TiposL2:     map[string]chispa3.ParamsTipo{"choice": {T: 0.9}, "score4": {T: 1, A: 2, B: 1}},
		TauEscalate: 0.8,
	}
	v1 := VistaCalibCapa("L1", cal, OrigenFichero, true)
	v2 := VistaCalibCapa("L2", cal.ParaL2(), OrigenTiposL2, true)
	if len(v1.SinCalib) != 2 || v1.SinCalib[0] != "score" || v1.SinCalib[1] != "multi" {
		t.Fatalf("L1 sin CALIB = %v", v1.SinCalib)
	}
	if len(v2.SinCalib) != 2 || v2.SinCalib[0] != "noul" || v2.SinCalib[1] != "multi" {
		t.Fatalf("L2 sin CALIB = %v", v2.SinCalib)
	}
	var noulL2 *EntradaCalib
	for i, e := range v2.Entradas {
		if e.Tipo == "noul" {
			noulL2 = &v2.Entradas[i]
		}
	}
	if noulL2 == nil || noulL2.Origen != OrigenDefecto || noulL2.ParamsTipo != ParamsDefecto() {
		t.Fatalf("noul de L2 debería salir con los de por defecto: %+v", noulL2)
	}
	if v1.AvisoSinCalib() == "" || VistaCalibCapa("L1", chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{
		"choice": {T: 1}, "noul": {T: 1}, "score": {T: 1}, "multi": {T: 1}}}, OrigenFichero, true).AvisoSinCalib() != "" {
		t.Fatal("el aviso debe salir solo si falta algún tipo")
	}

	m := NuevasMetricas()
	l2 := NuevoL2Con(nil, nil, cal.ParaL2(), nil)
	l2.origenCalib = OrigenTiposL2
	l2.UsaMetricas(m)
	paramsDeCapa(m, "L2", l2.calib, "noul")
	paramsDeCapa(m, "L2", l2.calib, "noul")
	paramsDeCapa(m, "L2", l2.calib, "choice") // este sí está
	var sb strings.Builder
	m.Escribe(&sb)
	for _, quiero := range []string{
		`chispa_calib_defecto_total{capa="L2",tipo="noul"} 2`,
		`chispa_calib{capa="L2",tipo="choice",origen="tipos_l2",param="T"} 0.9`,
		`chispa_calib{capa="L2",tipo="noul",origen="default",param="a"} 4`,
		`chispa_calib_tau{capa="L2",clave="tau_escalate",origen="calib"} 0.8`,
		`chispa_calib_sin_tipo{capa="L2",tipo="multi"} 1`,
	} {
		if !strings.Contains(sb.String(), quiero) {
			t.Errorf("/metrics no trae %q:\n%s", quiero, sb.String())
		}
	}
	if strings.Contains(sb.String(), `chispa_calib_defecto_total{capa="L2",tipo="choice"}`) {
		t.Error("choice está en CALIB: no debe contar como defecto")
	}
}

// ArmarDesde avisa de los tipos sin CALIB de cada capa (AvisosCalib) y, al poner la cascada en servicio, /metrics trae la CALIB efectiva.
func TestCalibAvisoAlArmarYMetricas(t *testing.T) {
	casc, mt := cascadaTiny(t, calibTiny(), ConfigPorDefecto())
	if len(mt.AvisosCalib) == 0 {
		t.Fatal("calibTiny no trae todos los tipos: falta el aviso")
	}
	for _, a := range mt.AvisosCalib {
		if !strings.HasPrefix(a, "AVISO: CALIB de L") || !strings.Contains(a, "sin los tipos [") {
			t.Fatalf("aviso: %q", a)
		}
	}
	casc.PublicaCalib() // lo hace el servidor al poner la cascada en servicio
	var sb strings.Builder
	casc.met.Escribe(&sb)
	if !strings.Contains(sb.String(), `chispa_calib{capa="L1",tipo="choice",origen="fichero",param="T"}`) ||
		!strings.Contains(sb.String(), `chispa_calib_sin_tipo{capa="L1",tipo="multi"} 1`) {
		t.Fatalf("/metrics sin la CALIB de L1:\n%s", sb.String())
	}
}
