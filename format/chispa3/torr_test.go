package chispa3

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func torrDePrueba() Torre {
	return Torre{Dim: 256, MaxLen: 128, Prefijo: "passage: ", ONNX: []byte("ONNX-torre-falso")}
}

func TestTORRIdaYVuelta(t *testing.T) {
	b, err := CodificarTORR(torrDePrueba())
	if err != nil {
		t.Fatal(err)
	}
	got, err := DecodificarTORR(b)
	if err != nil || got.Dim != 256 || got.MaxLen != 128 || got.Prefijo != "passage: " || !bytes.Equal(got.ONNX, []byte("ONNX-torre-falso")) {
		t.Fatalf("%+v %v", got, err)
	}
	// Dentro de un fichero, con todas las demás secciones.
	s := append(seccionesDePrueba(t), Seccion{TORR, b})
	ruta := filepath.Join(t.TempDir(), "x.chispa")
	if err := os.WriteFile(ruta, construir(t, s), 0o644); err != nil {
		t.Fatal(err)
	}
	f, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if !f.Tiene(TORR) {
		t.Fatal("sin TORR")
	}
	if g, err := f.Torre(); err != nil || g.Prefijo != "passage: " || len(g.ONNX) != 16 {
		t.Fatalf("%+v %v", g, err)
	}
	if TORR.String() != "TORR" {
		t.Fatal(TORR.String())
	}
}

// Los .chispa sin la sección se leen igual y Torre() dice que no hay.
func TestTORRAusenteEnTestdata(t *testing.T) {
	for _, n := range []string{"urgencia", "injection"} {
		f, err := Abrir("testdata/" + n + ".chispa")
		if err != nil {
			t.Fatal(n, err)
		}
		if f.Tiene(TORR) {
			t.Errorf("%s: no debería traer TORR", n)
		}
		if _, err := f.Torre(); !errors.Is(err, ErrNoHay) {
			t.Errorf("%s: %v", n, err)
		}
		f.Close()
	}
}

func TestTORRInvalida(t *testing.T) {
	ok, _ := CodificarTORR(torrDePrueba())
	malas := map[string][]byte{
		"vacía":     nil,
		"corta":     ok[:10],
		"versión":   append([]byte{9}, ok[1:]...),
		"sin onnx":  ok[:torrCab+9],
		"prefijo>n": append(append([]byte(nil), ok[:12]...), 200, 0, 0, 0, 'x', 'y'),
	}
	for n, b := range malas {
		if _, err := DecodificarTORR(b); !errors.Is(err, ErrContenido) {
			t.Errorf("%s: %v", n, err)
		}
	}
	for _, t0 := range []Torre{{0, 128, "p", []byte{1}}, {256, 0, "p", []byte{1}}, {256, 128, "\xff", []byte{1}}, {256, 128, "p", nil}} {
		if _, err := CodificarTORR(t0); !errors.Is(err, ErrContenido) {
			t.Errorf("%+v: %v", t0, err)
		}
	}
}
