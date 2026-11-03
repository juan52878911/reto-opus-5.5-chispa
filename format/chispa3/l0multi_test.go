package chispa3

import (
	"bytes"
	"errors"
	"os"
	"strings"
	"testing"
)

// entradasGolden: dos L0 de kindling de testdata y un L0TF pequeño; etiquetas distintas entre sí.
func entradasGolden(t *testing.T) []EntradaL0 {
	t.Helper()
	urg, err := os.ReadFile("testdata/urgencia.chispa")
	if err != nil {
		t.Fatal(err)
	}
	inj, err := os.ReadFile("testdata/injection.chispa")
	if err != nil {
		t.Fatal(err)
	}
	tf, err := CodificarL0TF(datosL0TF(false))
	if err != nil {
		t.Fatal(err)
	}
	return []EntradaL0{
		{Nombre: "urgencia", Tipo: L0, Datos: urg},
		{Nombre: "tf", Tipo: L0TF, Datos: tf},
		{Nombre: "injection", Tipo: L0, Datos: inj},
	}
}

func metaMin(t *testing.T) Seccion {
	b, err := Meta{Version: 1}.Codificar()
	if err != nil {
		t.Fatal(err)
	}
	return Seccion{Tipo: META, Datos: b}
}

// El golden l0multi.chispa se regenera con CHISPA_REGEN_GOLDEN=1; sin ello se compara byte a byte.
func TestL0MultiGolden(t *testing.T) {
	secs, err := SeccionesL0(entradasGolden(t))
	if err != nil || len(secs) != 1 || secs[0].Tipo != L0MULTI {
		t.Fatalf("secciones: %v %v", secs, err)
	}
	fich := construir(t, append([]Seccion{metaMin(t)}, secs...))
	const ruta = "testdata/l0multi.chispa"
	if os.Getenv("CHISPA_REGEN_GOLDEN") == "1" {
		if err := os.WriteFile(ruta, fich, 0o644); err != nil {
			t.Fatal(err)
		}
	}
	want, err := os.ReadFile(ruta)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(fich, want) {
		t.Fatal("el golden l0multi.chispa cambió (CHISPA_REGEN_GOLDEN=1 para regenerarlo si es intencionado)")
	}
	f, err := AbrirCon(ruta, Limites{})
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	ms, err := f.L0Todos()
	if err != nil || len(ms) != 3 {
		t.Fatalf("L0Todos: %d %v", len(ms), err)
	}
	if ms[0].Tipo != L0 || ms[1].TF == nil || ms[2].Tipo != L0 {
		t.Fatalf("tipos: %v %v %v", ms[0].Tipo, ms[1].Tipo, ms[2].Tipo)
	}
	if ms[0].Nombre != "sección urgencia" || strings.Join(ms[2].Etiquetas(), ",") != "injection,safe" {
		t.Fatalf("nombres/etiquetas: %v %v", ms[0].Nombre, ms[2].Etiquetas())
	}
	if L0MULTI != 11 || L0MULTI.String() != "L0MULTI" {
		t.Fatal("L0MULTI debe ser el tipo 11")
	}
}

// Un solo L0 sigue escribiéndose como L0 o L0TF, y L0Todos lo lee igual que antes.
func TestL0MultiUnoSeEscribeComoSiempre(t *testing.T) {
	es := entradasGolden(t)
	for _, e := range es {
		secs, err := SeccionesL0([]EntradaL0{e})
		if err != nil || len(secs) != 1 || secs[0].Tipo != e.Tipo || !bytes.Equal(secs[0].Datos, e.Datos) {
			t.Fatalf("%s: %v %v", e.Nombre, secs, err)
		}
		f, err := Desde(construir(t, append([]Seccion{metaMin(t)}, secs...)), Limites{})
		if err != nil {
			t.Fatal(err)
		}
		ms, err := f.L0Todos()
		if err != nil || len(ms) != 1 || ms[0].Nombre != "sección "+e.Tipo.String() {
			t.Fatalf("%s: %v %v", e.Nombre, ms, err)
		}
		if _, err := f.L0Multi(); !errors.Is(err, ErrNoHay) {
			t.Fatalf("sin L0MULTI: %v", err)
		}
	}
	if secs, err := SeccionesL0(nil); err != nil || secs != nil {
		t.Fatal("sin modelos no hay secciones")
	}
}

func TestL0MultiEtiquetasRepetidas(t *testing.T) {
	es := entradasGolden(t)
	dup := EntradaL0{Nombre: "otra.chispa (L0)", Tipo: L0, Datos: es[0].Datos}
	_, err := SeccionesL0([]EntradaL0{es[0], es[1], dup})
	if err == nil || !strings.Contains(err.Error(), "urgencia") || !strings.Contains(err.Error(), "otra.chispa") {
		t.Fatalf("debe nombrar los dos orígenes: %v", err)
	}
	// el mismo conjunto en otro orden también cuenta
	if FirmaEtiquetas([]string{"b", "a"}) != FirmaEtiquetas([]string{"a", "b"}) {
		t.Fatal("la firma no depende del orden")
	}
	// y un fichero ya escrito con repetidas, que SeccionesL0 no habría escrito: lo ve quien carga (servidor/móvil)
	b, err := CodificarL0Multi([]EntradaL0{es[0], dup})
	if err != nil {
		t.Fatal(err)
	}
	f, err := Desde(construir(t, []Seccion{{Tipo: L0MULTI, Datos: b}}), Limites{})
	if err != nil {
		t.Fatal(err)
	}
	ms, err := f.L0Todos()
	if err != nil || FirmaEtiquetas(ms[0].Etiquetas()) != FirmaEtiquetas(ms[1].Etiquetas()) {
		t.Fatal("L0Todos devuelve ambos; la comprobación es del consumidor")
	}
}

func TestL0MultiEntradasDeFicheros(t *testing.T) {
	es := entradasGolden(t)
	multi, _ := CodificarL0Multi(es[:2])
	f, err := Desde(construir(t, []Seccion{{Tipo: L0, Datos: es[2].Datos}, {Tipo: L0MULTI, Datos: multi}}), Limites{})
	if err != nil {
		t.Fatal(err)
	}
	got, err := f.EntradasL0("x.chispa")
	if err != nil || len(got) != 3 {
		t.Fatalf("%d %v", len(got), err)
	}
	if got[0].Nombre != "x.chispa (L0)" || got[1].Nombre != "x.chispa (urgencia)" {
		t.Fatalf("nombres: %q %q", got[0].Nombre, got[1].Nombre)
	}
}

func TestL0MultiInvalida(t *testing.T) {
	es := entradasGolden(t)
	b, _ := CodificarL0Multi(es)
	malos := map[string][]byte{
		"vacía":    {},
		"versión":  append([]byte{2, 0, 0, 0}, b[4:]...),
		"cero":     append(append([]byte{}, b[:4]...), 0, 0, 0, 0),
		"truncada": b[:len(b)-1],
		"sobrante": append(append([]byte{}, b...), 0),
		"tipo":     func() []byte { x := append([]byte{}, b...); x[8] = byte(CALIB); return x }(),
		"n enorme": append(append([]byte{}, b[:4]...), 0xff, 0xff, 0xff, 0x7f),
	}
	for n, x := range malos {
		if _, err := DecodificarL0Multi(x); !errors.Is(err, ErrContenido) && !errors.Is(err, ErrTruncado) {
			t.Errorf("%s: %v", n, err)
		}
	}
	if _, err := CodificarL0Multi(nil); !errors.Is(err, ErrContenido) {
		t.Fatal("N=0")
	}
	if _, err := CodificarL0Multi([]EntradaL0{{Tipo: CALIB}}); !errors.Is(err, ErrContenido) {
		t.Fatal("tipo")
	}
	// datos de un modelo corruptos: el marco pasa, la decodificación no
	mal := []EntradaL0{{Nombre: "roto", Tipo: L0TF, Datos: []byte{1, 2, 3}}}
	if _, err := SeccionesL0(mal); err == nil {
		t.Fatal("L0TF roto")
	}
}
