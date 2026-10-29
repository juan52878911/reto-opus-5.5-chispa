package chispa3

import (
	"bytes"
	"encoding/binary"
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

// testdata/torre.chispa lo escribe el escritor Python (sdk/python/tests/test_torr.py): los bytes de TORR deben ser los de CodificarTORR.
func TestTORRFicheroEscritoPorPython(t *testing.T) {
	f, err := Abrir(filepath.Join("testdata", "torre.chispa"))
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	g, err := f.Torre()
	if err != nil || g.Dim != 256 || g.MaxLen != 128 || g.Prefijo != "passage: " || string(g.ONNX) != "ONNX-torre-falso" {
		t.Fatalf("%+v %v", g, err)
	}
	want, err := CodificarTORR(Torre{Dim: 256, MaxLen: 128, Prefijo: "passage: ", ONNX: []byte("ONNX-torre-falso")})
	if err != nil {
		t.Fatal(err)
	}
	raw, err := f.Bytes(TORR)
	if err != nil || !bytes.Equal(raw, want) {
		t.Fatalf("bytes distintos: %x vs %x (%v)", raw, want, err)
	}
}

func TestTorrMaxLenMinimo(t *testing.T) {
	for _, ml := range []int{-1, 0, 1, 2} {
		if _, err := CodificarTORR(Torre{Dim: 4, MaxLen: ml, Prefijo: "passage: ", ONNX: []byte("x")}); !errors.Is(err, ErrContenido) {
			t.Errorf("max_len %d: %v", ml, err)
		}
	}
	b, err := CodificarTORR(Torre{Dim: 4, MaxLen: 3, Prefijo: "passage: ", ONNX: []byte("x")})
	if err != nil {
		t.Fatal(err)
	}
	for _, ml := range []uint32{1, 2} {
		c := append([]byte(nil), b...)
		binary.LittleEndian.PutUint32(c[8:], ml)
		if _, err := DecodificarTORR(c); !errors.Is(err, ErrContenido) {
			t.Errorf("decodificar max_len %d: %v", ml, err)
		}
	}
}
