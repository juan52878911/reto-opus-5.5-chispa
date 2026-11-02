package chispa3

import (
	"bytes"
	"encoding/binary"
	"errors"
	"os"
	"path/filepath"
	"strings"
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
	for _, t0 := range []Torre{{Dim: 0, MaxLen: 128, Prefijo: "p", ONNX: []byte{1}}, {Dim: 256, MaxLen: 0, Prefijo: "p", ONNX: []byte{1}}, {Dim: 256, MaxLen: 128, Prefijo: "\xff", ONNX: []byte{1}}, {Dim: 256, MaxLen: 128, Prefijo: "p"}, {Dim: 256, MaxLen: 128, Prefijo: "p", TextoTorre: "v9", ONNX: []byte{1}}} {
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

func torrV2DePrueba() Torre {
	t := torrDePrueba()
	t.TextoTorre = TextoTorreV2SinID
	return t
}

// TORR v2 lleva la versión del texto; v1 (o vacío) se escribe como TORR v1 y se lee como texto v1.
func TestTORRV2IdaYVuelta(t *testing.T) {
	b2, err := CodificarTORR(torrV2DePrueba())
	if err != nil {
		t.Fatal(err)
	}
	if v := binary.LittleEndian.Uint32(b2); v != 2 {
		t.Fatalf("versión escrita %d", v)
	}
	g, err := DecodificarTORR(b2)
	if err != nil || g.TextoTorre != TextoTorreV2SinID || g.Dim != 256 || g.MaxLen != 128 || g.Prefijo != "passage: " || string(g.ONNX) != "ONNX-torre-falso" {
		t.Fatalf("%+v %v", g, err)
	}
	for _, ver := range []string{"", TextoTorreV1} {
		x := torrDePrueba()
		x.TextoTorre = ver
		b1, err := CodificarTORR(x)
		if err != nil || binary.LittleEndian.Uint32(b1) != 1 {
			t.Fatalf("%q: %v", ver, err)
		}
		if g, err := DecodificarTORR(b1); err != nil || g.TextoTorre != TextoTorreV1 {
			t.Fatalf("%q: %+v %v", ver, g, err)
		}
	}
}

func TestTORRV2Invalida(t *testing.T) {
	ok, _ := CodificarTORR(torrV2DePrueba())
	le := binary.LittleEndian
	desconocida := append([]byte(nil), ok...)
	le.PutUint32(desconocida, 3)
	texto := append([]byte(nil), ok...)
	le.PutUint32(texto[16:], 7)
	malas := map[string][]byte{
		"versión 3":       desconocida,
		"texto 7":         texto,
		"cabecera corta":  ok[:18],
		"sin onnx":        ok[:torrCab2+9],
		"prefijo > resto": append(append([]byte(nil), ok[:12]...), 200, 0, 0, 0, 2, 0, 0, 0, 'x'),
	}
	for n, b := range malas {
		if _, err := DecodificarTORR(b); !errors.Is(err, ErrContenido) {
			t.Errorf("%s: %v", n, err)
		}
	}
}

func ficheroConMetaYTorr(t *testing.T, meta string, tr Torre) *Fichero {
	t.Helper()
	b, err := CodificarTORR(tr)
	if err != nil {
		t.Fatal(err)
	}
	s := seccionesDePrueba(t)
	for i := range s {
		if s[i].Tipo == META {
			s[i].Datos = []byte(meta)
		}
	}
	ruta := filepath.Join(t.TempDir(), "x.chispa")
	if err := os.WriteFile(ruta, construir(t, append(s, Seccion{TORR, b})), 0o644); err != nil {
		t.Fatal(err)
	}
	f, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { f.Close() })
	return f
}

// La versión efectiva sale de TORR; si META la trae y discrepa, error claro; META sin el campo no se contrasta.
func TestTextoTorreEfectivo(t *testing.T) {
	v1, v2 := torrDePrueba(), torrV2DePrueba()
	casos := []struct {
		meta     string
		torr     Torre
		want     string
		fallaCon string
	}{
		{`{"version":1}`, v1, "v1", ""},
		{`{"version":1}`, v2, "v2_sin_id", ""},
		{`{"version":1,"texto_torre":"v1"}`, v1, "v1", ""},
		{`{"version":1,"texto_torre":"v2_sin_id"}`, v2, "v2_sin_id", ""},
		{`{"version":1,"texto_torre":"v2_sin_id"}`, v1, "", "no coinciden"},
		{`{"version":1,"texto_torre":"v1"}`, v2, "", "no coinciden"},
		{`{"version":1,"texto_torre":"v9"}`, v2, "", "desconocido"},
	}
	for i, c := range casos {
		got, err := ficheroConMetaYTorr(t, c.meta, c.torr).TextoTorreEfectivo()
		if c.fallaCon != "" {
			if !errors.Is(err, ErrContenido) || !strings.Contains(err.Error(), c.fallaCon) {
				t.Errorf("caso %d: %v", i, err)
			}
			continue
		}
		if err != nil || got != c.want {
			t.Errorf("caso %d: %q %v", i, got, err)
		}
	}
}

// Mismos bytes de cabecera que escribe el escritor Python (sdk/python/tests/test_torr.py test_layout_v2).
func TestTORRV2Layout(t *testing.T) {
	b, err := CodificarTORR(torrV2DePrueba())
	if err != nil {
		t.Fatal(err)
	}
	want := []byte{2, 0, 0, 0, 0, 1, 0, 0, 0x80, 0, 0, 0, 9, 0, 0, 0, 2, 0, 0, 0}
	if !bytes.Equal(b[:20], want) || string(b[20:]) != "passage: ONNX-torre-falso" {
		t.Fatalf("%x", b)
	}
}
