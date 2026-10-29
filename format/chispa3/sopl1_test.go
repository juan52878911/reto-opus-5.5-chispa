package chispa3

import (
	"bytes"
	"errors"
	"math"
	"os"
	"path/filepath"
	"testing"
)

func soplDePrueba() []EntradaSopl1 {
	esc, q := CuantizarMedia([]float32{0.5, -0.25, 0, 0.125})
	return []EntradaSopl1{{
		Hash: ClaveConj("¿p?", []string{"b", "a"}), Ids: []string{"a", "b"}, K: []uint32{3, 0},
		Escala: []float32{esc, 0}, Media: append(q, 0, 0, 0, 0),
	}}
}

func TestSOPL1IdaYVuelta(t *testing.T) {
	b, err := CodificarSopl1(4, soplDePrueba())
	if err != nil {
		t.Fatal(err)
	}
	s, err := DecodificarSopl1(b)
	if err != nil || s.Len() != 1 || s.Dim() != 4 {
		t.Fatalf("%+v %v", s, err)
	}
	e, ok := s.Buscar(ClaveConj("¿p?", []string{"a", "b"}))
	if !ok {
		t.Fatal("no encuentra la pregunta")
	}
	k, m, ok := e.Opcion("a", 4)
	if !ok || k != 3 || math.Abs(float64(m[0])-0.5) > 1e-6 || math.Abs(float64(m[1])+0.25) > 0.003 {
		t.Fatalf("a: k=%d %v", k, m)
	}
	if k, m, ok := e.Opcion("b", 4); !ok || k != 0 || m[0] != 0 {
		t.Fatalf("b: k=%d %v", k, m)
	}
	if _, _, ok := e.Opcion("z", 4); ok {
		t.Fatal("z no existe")
	}
	if _, ok := s.Buscar(ClaveConj("otra", []string{"a", "b"})); ok {
		t.Fatal("otra pregunta no está")
	}
	// Dentro de un fichero con todas las demás secciones.
	ruta := filepath.Join(t.TempDir(), "x.chispa")
	if err := os.WriteFile(ruta, construir(t, append(seccionesDePrueba(t), Seccion{SOPL1, b})), 0o644); err != nil {
		t.Fatal(err)
	}
	f, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if g, err := f.Sopl1(); err != nil || g.Len() != 1 || SOPL1.String() != "SOPL1" {
		t.Fatalf("%v %v", g, err)
	}
}

// Los .chispa sin la sección se leen igual y Sopl1() dice que no hay.
func TestSOPL1AusenteEnTestdata(t *testing.T) {
	for _, n := range []string{"urgencia", "injection", "torre"} {
		f, err := Abrir("testdata/" + n + ".chispa")
		if err != nil {
			t.Fatal(n, err)
		}
		if f.Tiene(SOPL1) {
			t.Errorf("%s: no debería traer SOPL1", n)
		}
		if _, err := f.Sopl1(); !errors.Is(err, ErrNoHay) {
			t.Errorf("%s: %v", n, err)
		}
		f.Close()
	}
}

func TestSOPL1Invalida(t *testing.T) {
	ok, _ := CodificarSopl1(4, soplDePrueba())
	malas := map[string][]byte{
		"vacía":    nil,
		"corta":    ok[:10],
		"versión":  append([]byte{9}, ok[1:]...),
		"truncada": ok[:len(ok)-1],
		"sobrante": append(append([]byte(nil), ok...), 0),
		"dim 0":    append(append([]byte(nil), ok[:4]...), append([]byte{0, 0, 0, 0}, ok[8:]...)...),
	}
	for n, b := range malas {
		if _, err := DecodificarSopl1(b); !errors.Is(err, ErrContenido) {
			t.Errorf("%s: %v", n, err)
		}
	}
	e := soplDePrueba()[0]
	e.Ids = []string{"b", "a"}
	if _, err := CodificarSopl1(4, []EntradaSopl1{e}); !errors.Is(err, ErrContenido) {
		t.Errorf("ids desordenados: %v", err)
	}
	e = soplDePrueba()[0]
	e.Media = e.Media[:7]
	if _, err := CodificarSopl1(4, []EntradaSopl1{e}); !errors.Is(err, ErrContenido) {
		t.Errorf("media corta: %v", err)
	}
}

// testdata/soporte.chispa lo escribe el escritor Python (sdk/python/tests/test_sopl1.py): los bytes de SOPL1 deben ser los de CodificarSopl1.
func TestSOPL1FicheroEscritoPorPython(t *testing.T) {
	f, err := Abrir(filepath.Join("testdata", "soporte.chispa"))
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	want, err := CodificarSopl1(4, soplDePrueba())
	if err != nil {
		t.Fatal(err)
	}
	raw, err := f.Bytes(SOPL1)
	if err != nil || !bytes.Equal(raw, want) {
		t.Fatalf("bytes distintos: %x vs %x (%v)", raw, want, err)
	}
}

func TestPesoSoporteYMezclar(t *testing.T) {
	inf, cero, dos := math.Inf(1), 0.0, 2.0
	for _, c := range []struct {
		k      int
		lambda *float64
		want   float64
	}{{3, nil, 0}, {3, &inf, 0}, {0, &dos, 0}, {2, &dos, 0.5}, {6, &dos, 0.75}, {3, &cero, 1}} {
		if got := PesoSoporte(c.k, c.lambda); got != c.want {
			t.Errorf("k=%d λ=%v: %v, quería %v", c.k, c.lambda, got, c.want)
		}
	}
	d, m := []float32{1, 0}, []float32{0, 1}
	if g := Mezclar(d, m, 0); &g[0] != &d[0] {
		t.Error("w=0 debe devolver la descripción tal cual")
	}
	g := Mezclar(d, m, 0.5)
	if math.Abs(float64(g[0])-math.Sqrt2/2) > 1e-6 || math.Abs(float64(g[1])-math.Sqrt2/2) > 1e-6 {
		t.Errorf("w=0,5: %v", g)
	}
	if g := Mezclar(d, m, 1); math.Abs(float64(g[1])-1) > 1e-6 {
		t.Errorf("w=1: %v", g)
	}
	if g := Mezclar(d, []float32{-1, 0}, 0.5); &g[0] != &d[0] {
		t.Error("mezcla nula: debe devolver la descripción")
	}
}

func TestMediaSoporteConj(t *testing.T) {
	e := &EntradaConj{K: 2, D: 2, Clases: []string{"a", "b"},
		Escala: []float32{1, 1, 0.5, 0}, Proto: []byte{2, 0, 0, 4, 2, 2, 9, 9}}
	m, ok := e.MediaSoporte("a")
	if !ok || m[0] != 1 || m[1] != 2 {
		t.Fatalf("a: %v %v", m, ok)
	}
	m, ok = e.MediaSoporte("b") // la ranura de escala 0 no entra
	if !ok || m[0] != 1 || m[1] != 1 {
		t.Fatalf("b: %v %v", m, ok)
	}
	if _, ok := e.MediaSoporte("c"); ok {
		t.Fatal("c no existe")
	}
}
