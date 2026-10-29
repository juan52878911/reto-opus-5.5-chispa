package main

import (
	"bytes"
	"context"
	"encoding/json"
	"log"
	"os"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"github.com/juan52878911/chispa/server/decide"
)

// R10: el .chispa que exporta Python (CHISPA_MULTI, con CHISPA_MULTI_ESPERADO) trae CALIB «multi_l2» con las claves que arma el
// servidor (ClaveCalibMulti) y L2 opina en multi con ellas, sin el AVISO de respuestaMultiL2. Lo genera tests/test_multi_l2.py.
func TestMultiL2Opina(t *testing.T) {
	ruta, esp := os.Getenv("CHISPA_MULTI"), os.Getenv("CHISPA_MULTI_ESPERADO")
	if ruta == "" || esp == "" {
		t.Skip("sin CHISPA_MULTI")
	}
	var e struct {
		Pregunta string `json:"pregunta"`
		Opciones []struct {
			ID          string `json:"id"`
			Description string `json:"description"`
		} `json:"opciones"`
		Claves []string `json:"claves"`
	}
	b, err := os.ReadFile(esp)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(b, &e); err != nil {
		t.Fatal(err)
	}
	f, err := chispa3.Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	c, err := f.Calib()
	if err != nil {
		t.Fatal(err)
	}
	es, err := f.Esquemas()
	if err != nil {
		t.Fatal(err)
	}
	var ops []decide.Opcion
	for _, o := range e.Opciones {
		ops = append(ops, decide.Opcion{ID: o.ID, Description: o.Description})
	}
	p := decide.Pregunta{Texto: e.Pregunta, Kind: decide.KindMulti, Opciones: ops}

	// las claves de Python son exactamente las que arma el servidor, y no hay otras de multi_l2
	esq := decide.ClaveCalibMulti(p)
	if esq != esq[:1]+strings.ToLower(esq[1:]) {
		t.Errorf("el hex del servidor no va en minúsculas: %s", esq)
	}
	want := map[string]bool{"multi_l2" + esq: true}
	for _, o := range ops {
		want["multi_l2"+esq+"#"+o.ID] = true
	}
	got := map[string]bool{}
	for k := range c.Tipos {
		if strings.HasPrefix(k, "multi_l2") {
			got[k] = true
		}
	}
	for _, k := range e.Claves {
		if !want[k] {
			t.Errorf("Python escribió %q y el servidor no la arma", k)
		}
	}
	for k := range want {
		if !got[k] {
			t.Errorf("CALIB sin %q", k)
		}
	}
	if len(got) != len(want) {
		t.Errorf("claves multi_l2 en CALIB = %v, esperaba %v", got, want)
	}

	// L2 opina: Conf > 0 y una prob por opción, y no avisa de que falte la CALIB
	var buf bytes.Buffer
	log.SetOutput(&buf)
	defer log.SetOutput(os.Stderr)
	s := make([]float32, es.Dim())
	s[0] = 1
	l := decide.NuevoL2Con(sesionFalsa{[][]float32{s}}, es, c, tokFalso{})
	r, err := l.Decidir(context.Background(), p)
	if err != nil || r.Conf <= 0 || len(r.Probs) != len(ops) {
		t.Fatalf("L2 no opina en multi: %+v %v", r, err)
	}
	if strings.Contains(buf.String(), "AVISO") {
		t.Errorf("AVISO del servidor: %s", buf.String())
	}
	if r.EsquemaNuevo {
		t.Errorf("las torres de multi no salieron de ESQUEMAS")
	}
	// control: sin las claves de multi_l2, L2 no opina
	sin := chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{}, TauEscalate: c.TauEscalate}
	for k, v := range c.Tipos {
		if !strings.HasPrefix(k, "multi_l2") {
			sin.Tipos[k] = v
		}
	}
	if r, _ := decide.NuevoL2Con(sesionFalsa{[][]float32{s}}, es, sin, tokFalso{}).Decidir(context.Background(), p); r.Conf != 0 {
		t.Errorf("sin multi_l2 L2 opina: %+v", r)
	}
}
