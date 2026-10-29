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
		// R13: too_many_options antes que kind ausente o noul inválido
		{`{"question":"q","options":[{"id":"o0"},{"id":"o1"},{"id":"o2"},{"id":"o3"},{"id":"o4"},{"id":"o5"},{"id":"o6"},{"id":"o7"},{"id":"o8"},{"id":"o9"},{"id":"o10"},{"id":"o11"},{"id":"o12"},{"id":"o13"},{"id":"o14"},{"id":"o15"},{"id":"o16"},{"id":"o17"},{"id":"o18"},{"id":"o19"},{"id":"o20"},{"id":"o21"},{"id":"o22"},{"id":"o23"},{"id":"o24"},{"id":"o25"},{"id":"o26"},{"id":"o27"},{"id":"o28"},{"id":"o29"},{"id":"o30"},{"id":"o31"},{"id":"o32"},{"id":"o33"},{"id":"o34"},{"id":"o35"},{"id":"o36"},{"id":"o37"},{"id":"o38"},{"id":"o39"},{"id":"o40"},{"id":"o41"},{"id":"o42"},{"id":"o43"},{"id":"o44"},{"id":"o45"},{"id":"o46"},{"id":"o47"},{"id":"o48"},{"id":"o49"},{"id":"o50"},{"id":"o51"},{"id":"o52"},{"id":"o53"},{"id":"o54"},{"id":"o55"},{"id":"o56"},{"id":"o57"},{"id":"o58"},{"id":"o59"},{"id":"o60"},{"id":"o61"},{"id":"o62"},{"id":"o63"},{"id":"o64"},{"id":"o65"},{"id":"o66"},{"id":"o67"},{"id":"o68"},{"id":"o69"},{"id":"o70"},{"id":"o71"},{"id":"o72"},{"id":"o73"},{"id":"o74"},{"id":"o75"},{"id":"o76"},{"id":"o77"},{"id":"o78"},{"id":"o79"},{"id":"o80"},{"id":"o81"},{"id":"o82"},{"id":"o83"},{"id":"o84"},{"id":"o85"},{"id":"o86"},{"id":"o87"},{"id":"o88"},{"id":"o89"},{"id":"o90"},{"id":"o91"},{"id":"o92"},{"id":"o93"},{"id":"o94"},{"id":"o95"},{"id":"o96"},{"id":"o97"},{"id":"o98"},{"id":"o99"},{"id":"o100"},{"id":"o101"},{"id":"o102"},{"id":"o103"},{"id":"o104"},{"id":"o105"},{"id":"o106"},{"id":"o107"},{"id":"o108"},{"id":"o109"},{"id":"o110"},{"id":"o111"},{"id":"o112"},{"id":"o113"},{"id":"o114"},{"id":"o115"},{"id":"o116"},{"id":"o117"},{"id":"o118"},{"id":"o119"},{"id":"o120"},{"id":"o121"},{"id":"o122"},{"id":"o123"},{"id":"o124"},{"id":"o125"},{"id":"o126"},{"id":"o127"},{"id":"o128"},{"id":"o129"},{"id":"o130"},{"id":"o131"},{"id":"o132"},{"id":"o133"},{"id":"o134"},{"id":"o135"},{"id":"o136"},{"id":"o137"},{"id":"o138"},{"id":"o139"},{"id":"o140"},{"id":"o141"},{"id":"o142"},{"id":"o143"},{"id":"o144"},{"id":"o145"},{"id":"o146"},{"id":"o147"},{"id":"o148"},{"id":"o149"},{"id":"o150"},{"id":"o151"},{"id":"o152"},{"id":"o153"},{"id":"o154"},{"id":"o155"},{"id":"o156"},{"id":"o157"},{"id":"o158"},{"id":"o159"},{"id":"o160"},{"id":"o161"},{"id":"o162"},{"id":"o163"},{"id":"o164"},{"id":"o165"},{"id":"o166"},{"id":"o167"},{"id":"o168"},{"id":"o169"},{"id":"o170"},{"id":"o171"},{"id":"o172"},{"id":"o173"},{"id":"o174"},{"id":"o175"},{"id":"o176"},{"id":"o177"},{"id":"o178"},{"id":"o179"},{"id":"o180"},{"id":"o181"},{"id":"o182"},{"id":"o183"},{"id":"o184"},{"id":"o185"},{"id":"o186"},{"id":"o187"},{"id":"o188"},{"id":"o189"},{"id":"o190"},{"id":"o191"},{"id":"o192"},{"id":"o193"},{"id":"o194"},{"id":"o195"},{"id":"o196"},{"id":"o197"},{"id":"o198"},{"id":"o199"},{"id":"o200"},{"id":"o201"},{"id":"o202"},{"id":"o203"},{"id":"o204"},{"id":"o205"},{"id":"o206"},{"id":"o207"},{"id":"o208"},{"id":"o209"},{"id":"o210"},{"id":"o211"},{"id":"o212"},{"id":"o213"},{"id":"o214"},{"id":"o215"},{"id":"o216"},{"id":"o217"},{"id":"o218"},{"id":"o219"},{"id":"o220"},{"id":"o221"},{"id":"o222"},{"id":"o223"},{"id":"o224"},{"id":"o225"},{"id":"o226"},{"id":"o227"},{"id":"o228"},{"id":"o229"},{"id":"o230"},{"id":"o231"},{"id":"o232"},{"id":"o233"},{"id":"o234"},{"id":"o235"},{"id":"o236"},{"id":"o237"},{"id":"o238"},{"id":"o239"},{"id":"o240"},{"id":"o241"},{"id":"o242"},{"id":"o243"},{"id":"o244"},{"id":"o245"},{"id":"o246"},{"id":"o247"},{"id":"o248"},{"id":"o249"},{"id":"o250"},{"id":"o251"},{"id":"o252"},{"id":"o253"},{"id":"o254"},{"id":"o255"},{"id":"o256"}]}`, "too_many_options"},
		{`{"question":"q","kind":"noul","options":[{"id":"o0"},{"id":"o1"},{"id":"o2"},{"id":"o3"},{"id":"o4"},{"id":"o5"},{"id":"o6"},{"id":"o7"},{"id":"o8"},{"id":"o9"},{"id":"o10"},{"id":"o11"},{"id":"o12"},{"id":"o13"},{"id":"o14"},{"id":"o15"},{"id":"o16"},{"id":"o17"},{"id":"o18"},{"id":"o19"},{"id":"o20"},{"id":"o21"},{"id":"o22"},{"id":"o23"},{"id":"o24"},{"id":"o25"},{"id":"o26"},{"id":"o27"},{"id":"o28"},{"id":"o29"},{"id":"o30"},{"id":"o31"},{"id":"o32"},{"id":"o33"},{"id":"o34"},{"id":"o35"},{"id":"o36"},{"id":"o37"},{"id":"o38"},{"id":"o39"},{"id":"o40"},{"id":"o41"},{"id":"o42"},{"id":"o43"},{"id":"o44"},{"id":"o45"},{"id":"o46"},{"id":"o47"},{"id":"o48"},{"id":"o49"},{"id":"o50"},{"id":"o51"},{"id":"o52"},{"id":"o53"},{"id":"o54"},{"id":"o55"},{"id":"o56"},{"id":"o57"},{"id":"o58"},{"id":"o59"},{"id":"o60"},{"id":"o61"},{"id":"o62"},{"id":"o63"},{"id":"o64"},{"id":"o65"},{"id":"o66"},{"id":"o67"},{"id":"o68"},{"id":"o69"},{"id":"o70"},{"id":"o71"},{"id":"o72"},{"id":"o73"},{"id":"o74"},{"id":"o75"},{"id":"o76"},{"id":"o77"},{"id":"o78"},{"id":"o79"},{"id":"o80"},{"id":"o81"},{"id":"o82"},{"id":"o83"},{"id":"o84"},{"id":"o85"},{"id":"o86"},{"id":"o87"},{"id":"o88"},{"id":"o89"},{"id":"o90"},{"id":"o91"},{"id":"o92"},{"id":"o93"},{"id":"o94"},{"id":"o95"},{"id":"o96"},{"id":"o97"},{"id":"o98"},{"id":"o99"},{"id":"o100"},{"id":"o101"},{"id":"o102"},{"id":"o103"},{"id":"o104"},{"id":"o105"},{"id":"o106"},{"id":"o107"},{"id":"o108"},{"id":"o109"},{"id":"o110"},{"id":"o111"},{"id":"o112"},{"id":"o113"},{"id":"o114"},{"id":"o115"},{"id":"o116"},{"id":"o117"},{"id":"o118"},{"id":"o119"},{"id":"o120"},{"id":"o121"},{"id":"o122"},{"id":"o123"},{"id":"o124"},{"id":"o125"},{"id":"o126"},{"id":"o127"},{"id":"o128"},{"id":"o129"},{"id":"o130"},{"id":"o131"},{"id":"o132"},{"id":"o133"},{"id":"o134"},{"id":"o135"},{"id":"o136"},{"id":"o137"},{"id":"o138"},{"id":"o139"},{"id":"o140"},{"id":"o141"},{"id":"o142"},{"id":"o143"},{"id":"o144"},{"id":"o145"},{"id":"o146"},{"id":"o147"},{"id":"o148"},{"id":"o149"},{"id":"o150"},{"id":"o151"},{"id":"o152"},{"id":"o153"},{"id":"o154"},{"id":"o155"},{"id":"o156"},{"id":"o157"},{"id":"o158"},{"id":"o159"},{"id":"o160"},{"id":"o161"},{"id":"o162"},{"id":"o163"},{"id":"o164"},{"id":"o165"},{"id":"o166"},{"id":"o167"},{"id":"o168"},{"id":"o169"},{"id":"o170"},{"id":"o171"},{"id":"o172"},{"id":"o173"},{"id":"o174"},{"id":"o175"},{"id":"o176"},{"id":"o177"},{"id":"o178"},{"id":"o179"},{"id":"o180"},{"id":"o181"},{"id":"o182"},{"id":"o183"},{"id":"o184"},{"id":"o185"},{"id":"o186"},{"id":"o187"},{"id":"o188"},{"id":"o189"},{"id":"o190"},{"id":"o191"},{"id":"o192"},{"id":"o193"},{"id":"o194"},{"id":"o195"},{"id":"o196"},{"id":"o197"},{"id":"o198"},{"id":"o199"},{"id":"o200"},{"id":"o201"},{"id":"o202"},{"id":"o203"},{"id":"o204"},{"id":"o205"},{"id":"o206"},{"id":"o207"},{"id":"o208"},{"id":"o209"},{"id":"o210"},{"id":"o211"},{"id":"o212"},{"id":"o213"},{"id":"o214"},{"id":"o215"},{"id":"o216"},{"id":"o217"},{"id":"o218"},{"id":"o219"},{"id":"o220"},{"id":"o221"},{"id":"o222"},{"id":"o223"},{"id":"o224"},{"id":"o225"},{"id":"o226"},{"id":"o227"},{"id":"o228"},{"id":"o229"},{"id":"o230"},{"id":"o231"},{"id":"o232"},{"id":"o233"},{"id":"o234"},{"id":"o235"},{"id":"o236"},{"id":"o237"},{"id":"o238"},{"id":"o239"},{"id":"o240"},{"id":"o241"},{"id":"o242"},{"id":"o243"},{"id":"o244"},{"id":"o245"},{"id":"o246"},{"id":"o247"},{"id":"o248"},{"id":"o249"},{"id":"o250"},{"id":"o251"},{"id":"o252"},{"id":"o253"},{"id":"o254"},{"id":"o255"},{"id":"o256"}]}`, "too_many_options"},
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

// R13 H1: la secuencia de Kotlin/Swift (TorresL2 y, si da false, TextosTorreL2) cuenta 1 por petición, no 2.
func TestR13MultiCalibAusenteUnaVezPorPeticion(t *testing.T) {
	c := movilL2(t)
	c.calib.Tipos["multi_l2@deadbeef"] = chispa3.ParamsTipo{B: 1, Theta: 0.5}
	q := `{"question":"¿Temas R13?","kind":"multi","options":[{"id":"a"},{"id":"b"},{"id":"c"}]}`
	if c.TorresL2(q) {
		t.Fatal("TorresL2 debía ser false")
	}
	if tx := c.TextosTorreL2(q); tx != "[]" {
		t.Fatalf("TextosTorreL2 = %s", tx)
	}
	if n := c.MultiCalibAusente(); n != 1 {
		t.Fatalf("contador = %d, quería 1", n)
	}
}
