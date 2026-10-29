package chispamovil

import (
	"context"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"chispa/runtime/l1"
	"github.com/juan52878911/chispa/server/decide"
)

func calibMulti() chispa3.Calib {
	return chispa3.Calib{TauEscalate: 0.7, Tipos: map[string]chispa3.ParamsTipo{
		"choice": {T: 0.05, Theta: 0.5},
		"noul":   {T: 1, A: 12, B: -3, Theta: 0.5},
		"multi":  {T: 1, A: 12, B: -3, Theta: 0.5},
		// θ propio de una opción
		"multi#cortesia": {T: 1, A: 12, B: -3, Theta: 0.9},
	}}
}

func opsMulti() []decide.Opcion {
	return []decide.Opcion{{ID: "facturacion", Description: "factura cobro pago dinero reembolso"},
		{ID: "logistica", Description: "envio paquete retraso pedido"},
		{ID: "cortesia", Description: "hola gracias"}}
}

// Paridad servidor ↔ móvil en multi (L1): mismas probs por opción, mismas activas y misma confianza.
func TestMultiL1ParidadConServidor(t *testing.T) {
	l1b := l1Diminuto(palabrasTiny)
	c := ficheroV3(t, chispa3.Seccion{Tipo: chispa3.L1, Datos: l1b})
	c.calib = calibMulti()
	ruta := filepath.Join(t.TempDir(), "m.chispa-l1")
	if err := os.WriteFile(ruta, l1b, 0o600); err != nil {
		t.Fatal(err)
	}
	m, err := l1.Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer m.Cerrar()
	srv := decide.NuevoL1Modelo(m, calibMulti(), 4)
	ops := opsMulti()
	ojs, _ := json.Marshal(ops)
	for _, estado := range []string{"quiero un reembolso de la factura", "factura cobro pago dinero reembolso envio paquete retraso pedido",
		"hola gracias", "pago pedido retraso", "zzz qqq"} {
		p := decide.Pregunta{ID: "q", Texto: "¿Qué temas toca?", Kind: decide.KindMulti, Estado: estado, Opciones: ops}
		want, err := srv.Decidir(context.Background(), p)
		if err != nil {
			t.Fatal(err)
		}
		raw := c.Decidir(estado, `{"question":"¿Qué temas toca?","kind":"multi","options":`+string(ojs)+`}`)
		got := leer(t, raw)
		if !got.Ok || got.Opina != (want.Conf > 0) {
			t.Fatalf("%q: móvil %s, servidor %+v", estado, raw, want)
		}
		if want.Conf == 0 {
			continue
		}
		var js struct {
			Answers []string `json:"answers"`
		}
		json.Unmarshal([]byte(raw), &js)
		if js.Answers == nil || strings.Join(js.Answers, ",") != strings.Join(want.Answers, ",") || got.Answer != want.Answer ||
			math.Abs(got.Conf-want.Conf) > tolParidad {
			t.Fatalf("%q: móvil %s, servidor %+v", estado, raw, want)
		}
		for id, pr := range want.Probs {
			if math.Abs(got.Probs[id]-pr) > tolParidad {
				t.Fatalf("%q %s: móvil %v, servidor %v", estado, id, got.Probs[id], pr)
			}
		}
	}
}

// Paridad en L2: la misma cabeza de multi (CALIB «multi_l2» y «multi_l2#id») sobre torres de ceros, que dan s = softplus(0) en todas.
func TestMultiL2ParidadConServidor(t *testing.T) {
	cal := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{
		"multi_l2": {T: 1, A: 3, B: -2, Theta: 0.5}, "multi_l2#b": {T: 1, A: 3, B: -2, Theta: 0.6},
	}}
	ops := []opcion{{ID: "a"}, {ID: "b"}, {ID: "c"}}
	dops := []decide.Opcion{{ID: "a"}, {ID: "b"}, {ID: "c"}}
	c := &Chispa{calib: cal}
	r := c.multiL2(pregunta{Kind: "multi", Opciones: ops}, []float64{sCero, sCero, sCero})
	esq, _ := chispa3.DecodificarEsquemas(mustEsq())
	srv := decide.NuevoL2Con(sesFalsa{[][]float32{{0, 0, 0, 0}}}, esq, cal, tokFalso{}).ConTorres(torreCero{}, 64)
	want, err := srv.Decidir(context.Background(), decide.Pregunta{ID: "q", Estado: "x", Texto: "Temas", Kind: decide.KindMulti, Opciones: dops})
	if err != nil {
		t.Fatal(err)
	}
	if want.Conf == 0 || strings.Join(r.Answers, ",") != strings.Join(want.Answers, ",") || math.Abs(r.Conf-want.Conf) > 1e-9 {
		t.Fatalf("móvil %+v, servidor %+v", r, want)
	}
	for id, v := range want.Probs {
		if math.Abs(r.Probs[id]-v) > 1e-9 {
			t.Fatalf("probs[%s]: móvil %v ≠ servidor %v", id, r.Probs[id], v)
		}
	}
	// σ(3·ln2 − 2) = 0,52…: a y c pasan θ=0,5; b exige 0,6 y no pasa
	if strings.Join(r.Answers, ",") != "a,c" {
		t.Fatalf("activas %v", r.Answers)
	}
}

// Paridad por capa: CALIB con «multi», «multi_l2» y «multi_l2#id» (más «noul» para el último respaldo); L1 y L2 usan cada una la suya.
func TestMultiL2PrecedenciaParidadConServidor(t *testing.T) {
	cal := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{
		"noul":  {T: 1, A: 5, B: -1, Theta: 0.4},
		"multi": {T: 1, A: 3, B: -2, Theta: 0.5}, "multi#b": {T: 1, A: 3, B: -2, Theta: 0.6},
		"multi_l2": {T: 1, A: 7, B: -3, Theta: 0.45}, "multi_l2#b": {T: 1, A: 2, B: 0.5, Theta: 0.7},
	}}
	ops := []opcion{{ID: "a"}, {ID: "b"}, {ID: "c"}}
	dops := []decide.Opcion{{ID: "a"}, {ID: "b"}, {ID: "c"}}
	esq, _ := chispa3.DecodificarEsquemas(mustEsq())
	for nombre, cal := range map[string]chispa3.Calib{
		"completa":            cal,
		"sin multi_l2#id":     {Tipos: map[string]chispa3.ParamsTipo{"noul": cal.Tipos["noul"], "multi": cal.Tipos["multi"], "multi_l2": cal.Tipos["multi_l2"]}},
		"sin multi_l2 (noul)": {Tipos: map[string]chispa3.ParamsTipo{"noul": cal.Tipos["noul"], "multi": cal.Tipos["multi"]}},
	} {
		c := &Chispa{calib: cal}
		r := c.multiL2(pregunta{Kind: "multi", Opciones: ops}, []float64{sCero, sCero, sCero})
		srv := decide.NuevoL2Con(sesFalsa{[][]float32{{0, 0, 0, 0}}}, esq, cal, tokFalso{}).ConTorres(torreCero{}, 64)
		want, err := srv.Decidir(context.Background(), decide.Pregunta{ID: "q", Estado: "x", Texto: "Temas", Kind: decide.KindMulti, Opciones: dops})
		if err != nil {
			t.Fatal(err)
		}
		if want.Conf == 0 || strings.Join(r.Answers, ",") != strings.Join(want.Answers, ",") || math.Abs(r.Conf-want.Conf) > 1e-9 || len(r.Probs) != len(want.Probs) {
			t.Fatalf("%s: móvil %+v, servidor %+v", nombre, r, want)
		}
		for id, v := range want.Probs {
			if math.Abs(r.Probs[id]-v) > 1e-9 {
				t.Fatalf("%s probs[%s]: móvil %v ≠ servidor %v", nombre, id, r.Probs[id], v)
			}
		}
	}
}

func TestMultiContratoJSON(t *testing.T) {
	c := ficheroV3(t, chispa3.Seccion{Tipo: chispa3.L1, Datos: l1Diminuto(palabrasTiny)})
	c.calib = calibMulti()
	ojs, _ := json.Marshal(opsMulti())
	// answers solo en multi
	raw := c.Decidir("factura cobro", `{"question":"¿Temas?","kind":"multi","options":`+string(ojs)+`}`)
	if !strings.Contains(raw, `"answers":[`) {
		t.Fatalf("multi sin answers: %s", raw)
	}
	raw = c.Decidir("factura cobro", `{"question":"¿Área?","kind":"choice","options":[{"id":"a"},{"id":"b"}]}`)
	if strings.Contains(raw, `"answers"`) {
		t.Fatalf("choice con answers: %s", raw)
	}
	// validación igual que el servidor
	for nombre, q := range map[string]string{
		"una opción": `{"question":"q","kind":"multi","options":[{"id":"a"}]}`,
		"repetida":   `{"question":"q","kind":"multi","options":[{"id":"a"},{"id":"a"}]}`,
		"sin opcs":   `{"question":"q","kind":"multi"}`,
	} {
		if got := leer(t, c.Decidir("x", q)); got.Error == "" {
			t.Errorf("%s: debía fallar: %+v", nombre, got)
		}
	}
	// L0 no opina en multi
	got := leer(t, c.DecidirL0("factura", `{"question":"q","kind":"multi","options":[{"id":"a"},{"id":"b"}]}`))
	if !got.Ok || got.Opina || len(got.Probs) != 0 {
		t.Fatalf("L0 en multi: %+v", got)
	}
}
