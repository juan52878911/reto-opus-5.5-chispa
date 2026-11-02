package main

import (
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"chispa/format/chispa3"
)

const metaJ = `{"version":1,"tareas":["t1"],"licencias":{"x":"MIT"},"dorado":""}`
const calibJ = `{"tipos":{"choice":{"T":0.05,"a":0,"b":0,"theta":0.5},"noul":{"T":1,"a":4,"b":-2,"theta":0.4}},"tau_escalate":0.6}`

func esquemasJ(t *testing.T) []byte {
	v := []int8{127, -127, 0, 5}
	raw := make([]byte, len(v))
	for i, x := range v {
		raw[i] = byte(x)
	}
	b, err := json.Marshal(esquemasJSON{Dim: 4, Entradas: []entradaJSON{
		{Pregunta: "¿qué?", Kind: "choice", Opciones: []opcionJSON{{"a", "da"}}, Escala: 0.01, Vec: base64.StdEncoding.EncodeToString(raw)},
		{Pregunta: "¿qué?", Kind: "choice", Opciones: []opcionJSON{{"b", "db"}}, Escala: 0.02, Vec: base64.StdEncoding.EncodeToString(raw)},
	}})
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func TestIdaYVuelta(t *testing.T) {
	ruta := filepath.Join(t.TempDir(), "x.chispa")
	l2 := []byte("ONNX-falso")
	if err := empaquetar([]byte(metaJ), l2, esquemasJ(t), []byte(calibJ), ruta); err != nil {
		t.Fatal(err)
	}
	f, err := chispa3.Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if err := f.Verificar(); err != nil {
		t.Fatal(err)
	}
	if got, _ := f.L2(); string(got) != string(l2) {
		t.Fatalf("L2 = %q", got)
	}
	c, err := f.Calib()
	if err != nil || c.TauEscalate != 0.6 || c.Tipos["noul"].B != -2 {
		t.Fatalf("calib %+v %v", c, err)
	}
	e, err := f.Esquemas()
	if err != nil || e.Len() != 2 || e.Dim() != 4 || e.Version() != 2 {
		t.Fatalf("esquemas %v", err)
	}
	vec, esc, ok := e.BuscarEsquema("¿qué?", "choice", []chispa3.OpcionClave{{ID: "b", Descripcion: "db"}})
	if !ok || esc != 0.02 || int8(vec[0]) != 127 || int8(vec[1]) != -127 {
		t.Fatalf("buscar: %v %v %v", vec, esc, ok)
	}
	if _, _, ok := e.BuscarEsquema("¿qué?", "choice", []chispa3.OpcionClave{{ID: "b", Descripcion: "otra"}}); ok {
		t.Fatal("no debería estar")
	}
}

func TestRechazaEntradasInvalidas(t *testing.T) {
	d := t.TempDir()
	malos := map[string][4][]byte{
		"calib T=0": {[]byte(metaJ), []byte("x"), esquemasJ(t), []byte(`{"tipos":{"c":{"T":0,"a":0,"b":0,"theta":0}},"tau_escalate":0.5}`)},
		"tau>1":     {[]byte(metaJ), []byte("x"), esquemasJ(t), []byte(`{"tipos":{},"tau_escalate":1.5}`)},
		"l2 vacío":  {[]byte(metaJ), nil, esquemasJ(t), []byte(calibJ)},
		"vec corto": {[]byte(metaJ), []byte("x"), []byte(`{"dim":4,"entradas":[{"pregunta":"p","opciones":["a"],"escala":1,"vec":"AAA="}]}`), []byte(calibJ)},
		"hash dup":  {[]byte(metaJ), []byte("x"), []byte(`{"dim":1,"entradas":[{"pregunta":"p","opciones":["a"],"escala":1,"vec":"AA=="},{"pregunta":"p","opciones":["a"],"escala":1,"vec":"AA=="}]}`), []byte(calibJ)},
		"meta mal":  {[]byte(`{"version":0}`), []byte("x"), esquemasJ(t), []byte(calibJ)},
	}
	for n, m := range malos {
		if err := empaquetar(m[0], m[1], m[2], m[3], filepath.Join(d, "m.chispa")); err == nil {
			t.Errorf("%s: debería fallar", n)
		}
	}
	if _, err := os.Stat(filepath.Join(d, "m.chispa")); err == nil {
		t.Error("no debe quedar fichero")
	}
}

// Un fichero hecho por exportar.py (CHISPA_FICHERO) con su descripción (CHISPA_ESPERADO): se abre con chispa3,
// cada torre cuantizada está donde toca y vale lo mismo.
func TestFicheroDePython(t *testing.T) {
	ruta, esp := os.Getenv("CHISPA_FICHERO"), os.Getenv("CHISPA_ESPERADO")
	if ruta == "" || esp == "" {
		t.Skip("sin CHISPA_FICHERO")
	}
	var e struct {
		Tau     float64       `json:"tau"`
		Dim     int           `json:"dim"`
		L2Bytes int           `json:"l2_bytes"`
		Tipos   []string      `json:"tipos"`
		Torres  []entradaJSON `json:"torres"`
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
	if err := f.Verificar(); err != nil {
		t.Fatal(err)
	}
	for _, tp := range []chispa3.Tipo{chispa3.META, chispa3.L2, chispa3.ESQUEMAS, chispa3.CALIB} {
		if !f.Tiene(tp) {
			t.Errorf("falta %v", tp)
		}
	}
	if l2, _ := f.L2(); len(l2) != e.L2Bytes {
		t.Errorf("L2 mide %d y debería medir %d", len(l2), e.L2Bytes)
	}
	c, err := f.Calib()
	if err != nil || c.TauEscalate != e.Tau {
		t.Fatalf("calib %+v %v", c, err)
	}
	for _, tp := range e.Tipos {
		if _, ok := c.Tipos[tp]; !ok {
			t.Errorf("CALIB sin %s", tp)
		}
	}
	es, err := f.Esquemas()
	if err != nil || es.Dim() != e.Dim || es.Len() != len(e.Torres) {
		t.Fatalf("esquemas: %v", err)
	}
	for _, tr := range e.Torres {
		raw, _ := base64.StdEncoding.DecodeString(tr.Vec)
		vec, esc, ok := es.Buscar2(tr.clave())
		if !ok || esc != tr.Escala || string(vec) != string(raw) {
			t.Fatalf("torre %q %v distinta o ausente", tr.Pregunta, tr.Opciones)
		}
	}
}

// El fixture de Python (CHISPA_FICHERO, CHISPA_FIXTURE_JSON) es ESQUEMAS v2 y cada clave esperada se encuentra con BuscarEsquema.
func TestFixtureEsquemasV2(t *testing.T) {
	ruta, esp := os.Getenv("CHISPA_FICHERO"), os.Getenv("CHISPA_FIXTURE_JSON")
	if ruta == "" || esp == "" {
		t.Skip("sin CHISPA_FICHERO")
	}
	b, err := os.ReadFile(esp)
	if err != nil {
		t.Fatal(err)
	}
	var e struct {
		Claves []entradaJSON `json:"claves"`
	}
	if err := json.Unmarshal(b, &e); err != nil {
		t.Fatal(err)
	}
	f, err := chispa3.Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if err := f.Verificar(); err != nil {
		t.Fatal(err)
	}
	es, err := f.Esquemas()
	if err != nil || es.Version() != 2 || es.Len() != len(e.Claves) {
		t.Fatalf("esquemas: %v", err)
	}
	for _, c := range e.Claves {
		ops := make([]chispa3.OpcionClave, len(c.Opciones))
		for i, o := range c.Opciones {
			ops[i] = chispa3.OpcionClave{ID: o.ID, Descripcion: o.Description}
		}
		if _, _, ok := es.BuscarEsquema(c.Pregunta, c.Kind, ops); !ok {
			t.Errorf("falta %q %s %v", c.Pregunta, c.Kind, c.Opciones)
		}
	}
}

func TestTextoTorreEnMeta(t *testing.T) {
	leer := func(meta string) (map[string]any, error) {
		ruta := filepath.Join(t.TempDir(), "x.chispa")
		if err := empaquetar([]byte(meta), []byte("ONNX-falso"), esquemasJ(t), []byte(calibJ), ruta); err != nil {
			return nil, err
		}
		f, err := chispa3.Abrir(ruta)
		if err != nil {
			t.Fatal(err)
		}
		defer f.Close()
		b, err := f.Bytes(chispa3.META)
		if err != nil {
			t.Fatal(err)
		}
		var m map[string]any
		if err := json.Unmarshal(b, &m); err != nil {
			t.Fatal(err)
		}
		return m, nil
	}
	m, err := leer(`{"version":1,"tareas":["t1"],"licencias":{"x":"MIT"},"dorado":"","texto_torre":"v2_sin_id"}`)
	if err != nil || m["texto_torre"] != "v2_sin_id" || m["version"] != float64(1) || m["dorado"] != "" {
		t.Fatalf("v2: %v %v", m, err)
	}
	if m, err = leer(metaJ); err != nil || m["texto_torre"] != nil {
		t.Fatalf("sin campo: %v %v", m, err)
	}
	if _, err = leer(`{"version":1,"tareas":["t1"],"licencias":{},"dorado":"","texto_torre":"v3"}`); err == nil {
		t.Fatal("v3 no debería valer")
	}
	if _, err = leer(`{"version":1,"tareas":["t1"],"licencias":{},"dorado":"","otro":1}`); err == nil {
		t.Fatal("campos desconocidos siguen rechazados")
	}
}
