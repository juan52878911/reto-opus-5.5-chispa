package chispamovil

import (
	"encoding/json"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// R11 #3: multi sin «multi_l2» del esquema no pide torres ni ONNX al host (L2 no opinaría), así que no gasta su presupuesto.
func TestR11MultiSinMultiL2NoPideTorres(t *testing.T) {
	c := movilL2(t)
	q := `{"question":"¿Temas R11?","kind":"multi","options":[{"id":"a"},{"id":"b"},{"id":"c"}]}`
	if c.TorresL2(q) {
		t.Fatal("TorresL2 debía ser false sin multi_l2")
	}
	if got := c.TextosTorreL2(q); got != "[]" {
		t.Fatalf("no debía pedir torres: %s", got)
	}
	if r := leer(t, c.PuntuarL2(q, ranuras(ranurasTorre...), 2)); !r.Ok || r.Opina {
		t.Fatalf("no debía opinar: %+v", r)
	}
	// con multi_l2 sí las pide
	c.calib.Tipos["multi_l2"] = chispa3.ParamsTipo{B: 1, Theta: 0.5}
	var textos []string
	json.Unmarshal([]byte(c.TextosTorreL2(q)), &textos)
	if len(textos) != 3 {
		t.Fatalf("con multi_l2 debía pedir 3 torres: %v", textos)
	}
}

// R11 #4: CALIB con claves multi@ y ninguna casa con la pregunta → métrica y aviso (una vez).
func TestR11CalibMultiAusenteAvisa(t *testing.T) {
	c := &Chispa{calib: chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"multi@00": {A: 1, Theta: 0.5}}}}
	p := pregunta{Texto: "q", Kind: "multi", Opciones: []opcion{{ID: "a"}, {ID: "b"}}}
	c.multi(p, []float64{0, 0})
	c.multi(p, []float64{0, 0})
	if n := c.MultiCalibAusente(); n != 2 {
		t.Fatalf("contador = %d, quería 2", n)
	}
	if av := c.Avisos(); strings.Count(av, "CALIB de multi") != 1 {
		t.Fatalf("aviso: %q", av)
	}
	// si casa, no cuenta
	c2 := &Chispa{calib: chispa3.Calib{Tipos: map[string]chispa3.ParamsTipo{"multi" + claveCalibMulti(p): {A: 1, Theta: 0.5}}}}
	c2.multi(p, []float64{0, 0})
	if c2.MultiCalibAusente() != 0 || c2.Avisos() != "" {
		t.Fatal("no debía avisar si la CALIB casa")
	}
}

// R11 #11 y #12: mismo orden de validación y mismo código que server/decide.validarPeticion, en el mensaje de todos los errores.
func TestR11CodigosYOrdenComoServidor(t *testing.T) {
	c := movilL2(t)
	casos := []struct{ q, codigo string }{
		{`{"question":"","kind":"choice","options":[{"id":"a"},{"id":"b"}]}`, "missing_question"},
		{`{"question":"q","options":[{"id":"a"},{"id":"b"}]}`, "missing_kind"},
		{`{"question":"q","kind":"x","options":[{"id":"a"},{"id":"b"}]}`, "invalid_kind"},
		{`{"question":"q","kind":"choice","options":[{"id":"a"}]}`, "too_few_options"},
		{`{"question":"q","kind":"noul","options":[{"id":"a"},{"id":"b"}]}`, "invalid_options"},
		{`{"question":"q","kind":"choice","options":[{"id":""},{"id":"b"}]}`, "missing_option_id"},
		{`{"question":"q","kind":"choice","options":[{"id":"a"},{"id":"a"}]}`, "duplicate_option_id"},
		{`{"question":"q","kind":"choice","options":[{"id":"` + strings.Repeat("x", maxIDByte+1) + `"},{"id":"b"}]}`, "field_too_long"},
		{`{"question":"` + strings.Repeat("x", maxTextoByte+1) + `","kind":"choice","options":[{"id":"a"},{"id":"b"}]}`, "field_too_long"},
		// orden: separador antes que duplicado; longitud de descripción antes que separador; pregunta antes que kind
		{`{"question":"q","kind":"choice","options":[{"id":"a\u001f"},{"id":"a\u001f"}]}`, "invalid_characters"},
		{`{"question":"q","kind":"choice","options":[{"id":"a","description":"\u001d` + strings.Repeat("x", maxTextoByte) + `"},{"id":"b"}]}`, "field_too_long"},
		{`{"question":"","kind":"x","options":[]}`, "missing_question"},
		{`{"question":"q\u001f","kind":"x"}`, "invalid_characters"},
		{`{"question":"q","kind":"x","options":[{"id":"a"}]}`, "invalid_kind"},
	}
	for _, k := range casos {
		for nombre, f := range map[string]func(string) string{
			"L1": func(s string) string { return c.Decidir("x", s) }, "L0": func(s string) string { return c.DecidirL0("x", s) },
			"L2": func(s string) string { return c.PuntuarL2(s, nil, 0) },
		} {
			if r := leer(t, f(k.q)); r.Ok || !strings.HasPrefix(r.Error, k.codigo+": ") {
				t.Errorf("%s %.60s: error %q, quería código %s", nombre, k.q, r.Error, k.codigo)
			}
		}
	}
}

// R12 H5: L2 con «multi_l2@<hash>» de otro texto no opina y cuenta como CALIB ausente (como el servidor), con aviso único.
func TestR12MultiL2SinCalibDelEsquemaCuentaAusente(t *testing.T) {
	c := movilL2(t)
	c.calib.Tipos["multi_l2@deadbeef"] = chispa3.ParamsTipo{B: 1, Theta: 0.5}
	q := `{"question":"¿Temas R12?","kind":"multi","options":[{"id":"a"},{"id":"b"},{"id":"c"}]}`
	if c.TorresL2(q) {
		t.Fatal("TorresL2 debía ser false")
	}
	if n := c.MultiCalibAusente(); n != 1 {
		t.Fatalf("contador = %d, quería 1", n)
	}
	if av := c.Avisos(); strings.Count(av, "CALIB de multi_l2") != 1 {
		t.Fatalf("aviso: %q", av)
	}
}
