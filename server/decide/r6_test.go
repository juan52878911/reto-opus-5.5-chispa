package decide

import (
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func conCab(h http.Handler, cab string) int {
	r := httptest.NewRequest("POST", "/v1/decide", strings.NewReader(cuerpoNonce))
	r.Header.Set("Authorization", cab)
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, r)
	return rr.Code
}

// R6-7: el esquema Bearer no distingue mayúsculas y tolera espacios; sigue fallando cerrado.
func TestR6BearerSinMayusculas(t *testing.T) {
	_, h, _ := servidorConClaves(t, []ClaveAPI{{ID: "a", HashSHA256: HashClave("k"), RPS: 100}})
	for _, c := range []string{"bearer k", "BEARER k", "Bearer   k", "  Bearer k"} {
		if got := conCab(h, c); got != 200 {
			t.Errorf("%q: %d, quiero 200", c, got)
		}
	}
	for _, c := range []string{"Bearer", "Bearer ", "Basic k", "Bearerk", "Bearer mala", ""} {
		if got := conCab(h, c); got != 401 {
			t.Errorf("%q: %d, quiero 401", c, got)
		}
	}
}

// R6-4: los cubos sobreviven a la recarga (mismo id y hash); una clave nueva con el mismo id pero otro hash empieza llena.
func TestR6RecargaConservaCubos(t *testing.T) {
	ks := []ClaveAPI{{ID: "a", HashSHA256: HashClave("k"), RPS: 0.001, Rafaga: 2}}
	s, h, _ := servidorConClaves(t, ks)
	s.ConRecarga(func() (*Armado, error) {
		ar, err := (&armadorModelos{etiquetas: []string{"x"}, met: s.Met}).armar()
		ar.APIKeys = ks
		return ar, err
	}, "")
	for i, want := range []int{200, 200, 429} {
		if got := conClave(h, "k").Code; got != want {
			t.Fatalf("petición %d: %d, quiero %d", i, got, want)
		}
	}
	if err := s.Recargar(); err != nil {
		t.Fatal(err)
	}
	if got := conClave(h, "k").Code; got != 429 {
		t.Fatalf("tras recargar: %d, quiero 429 (cubo conservado)", got)
	}
	ks = []ClaveAPI{{ID: "a", HashSHA256: HashClave("otra"), RPS: 0.001, Rafaga: 2}}
	if err := s.Recargar(); err != nil {
		t.Fatal(err)
	}
	if got := conClave(h, "otra").Code; got != 200 {
		t.Fatalf("clave rotada: %d, quiero 200 (cubo nuevo)", got)
	}
}

// R6-3: una recarga sin claves no abre en silencio un servidor que las tenía, salvo api_keys_abierto.
func TestR6RecargaSinClavesSeRechaza(t *testing.T) {
	ks := []ClaveAPI{{ID: "a", HashSHA256: HashClave("k"), RPS: 100}}
	abierto := false
	s, h, _ := servidorConClaves(t, ks)
	s.ConRecarga(func() (*Armado, error) {
		ar, err := (&armadorModelos{etiquetas: []string{"x"}, met: s.Met}).armar()
		ar.APIKeysAbierto = abierto
		return ar, err
	}, "")
	if err := s.Recargar(); err == nil {
		t.Fatal("la recarga sin api_keys debía rechazarse")
	}
	if s.Generacion() != 1 || conClave(h, "").Code != 401 || conClave(h, "k").Code != 200 {
		t.Fatal("debía seguir el modelo viejo con sus claves")
	}
	abierto = true
	if err := s.Recargar(); err != nil || conClave(h, "").Code != 200 {
		t.Fatalf("con api_keys_abierto la recarga debe pasar y abrir: %v", err)
	}
}

// R6-12: ids de clave restringidos y etiquetas de /metrics escapadas.
func TestR6IdClaveSeguro(t *testing.T) {
	for _, id := range []string{"a\tb", "x\"y", "a b", "a\n", strings.Repeat("a", 65), "ñ"} {
		if validarClaves([]ClaveAPI{{ID: id, HashSHA256: HashClave("k"), RPS: 1}}) == nil {
			t.Errorf("id %q debía rechazarse", id)
		}
	}
	if err := validarClaves([]ClaveAPI{{ID: "cliente-1_a.B", HashSHA256: HashClave("k"), RPS: 1}}); err != nil {
		t.Error(err)
	}
	m := NuevasMetricas()
	m.Clave("a\tb\"c\\d\n", "ok")
	rr := httptest.NewRecorder()
	m.Escribe(rr)
	if !strings.Contains(rr.Body.String(), `clave="a`+"\t"+`b\"c\\d\n"`) {
		t.Errorf("etiqueta mal escapada:\n%s", rr.Body.String())
	}
}

// R6-2: λ de L1 frente a l1_lambda_calib.
func TestR6LambdaCalibSoporte(t *testing.T) {
	p := Pregunta{Kind: KindChoice, Texto: "¿Qué área?", Estado: "paquete retraso", Opciones: opsReembolso()}
	base := l1Con(t, nil, nil)
	sopl := soplL1(t, base, p, map[string]string{"facturacion": "paquete retraso"}, map[string]uint32{"facturacion": 4})
	armar := func(cal *float64, cfg Config) *Montaje {
		c := calibTiny()
		c.L1LambdaCalib = cal
		cfg.CacheEsquemas, cfg.CacheRespuestas = 16, 16
		mt, err := ArmarDesde(v3Tiny(t, c, chispa3.Seccion{Tipo: chispa3.SOPL1, Datos: sopl}), NuevoL0(8), &cfg, false, nil)
		if err != nil {
			t.Fatal(err)
		}
		return &mt
	}
	tiene := func(mt *Montaje, sub string) bool {
		for _, a := range mt.Avisos {
			if strings.Contains(a, sub) {
				return true
			}
		}
		return false
	}
	difiere := func(mt *Montaje) bool {
		return !reflect.DeepEqual(mt.L1.(*L1).opciones(p)["facturacion"], base.opciones(p)["facturacion"])
	}
	// con campo y mismo λ: soporte activo, sin aviso
	if mt := armar(floatPtr(4), Config{}); !difiere(mt) || len(mt.Avisos) != 0 {
		t.Errorf("mismo λ: soporte=%v avisos=%v", difiere(mt), mt.Avisos)
	}
	// con campo y λ distinto: soporte activo y aviso
	if mt := armar(floatPtr(4), Config{L1ShrinkageLambda: floatPtr(1)}); !difiere(mt) || !tiene(mt, "distinto") {
		t.Errorf("λ distinto: avisos=%v", mt.Avisos)
	}
	// sin campo: apagado (como antes) con aviso, salvo λ explícito
	if mt := armar(nil, Config{}); difiere(mt) || !tiene(mt, "sin encogimiento") {
		t.Errorf("viejo sin λ: soporte=%v avisos=%v", difiere(mt), mt.Avisos)
	}
	if mt := armar(nil, Config{L1ShrinkageLambda: floatPtr(4)}); !difiere(mt) || !tiene(mt, "sin encogimiento") {
		t.Errorf("viejo con λ explícito: soporte=%v avisos=%v", difiere(mt), mt.Avisos)
	}
}
