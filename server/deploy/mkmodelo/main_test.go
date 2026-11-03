package main

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

func escribirChispa(t *testing.T, dir, nombre string, tipo chispa3.Tipo, n int) string {
	t.Helper()
	datos := make([]byte, n)
	if tipo == chispa3.L0 { // el L0 se valida al unir: uno real de testdata
		datos = leerTestdata(t, "injection.chispa")
	}
	return escribirSecciones(t, dir, nombre, chispa3.Seccion{Tipo: tipo, Datos: datos})
}

func leerTestdata(t *testing.T, n string) []byte {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("..", "..", "testdata", n))
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func escribirSecciones(t *testing.T, dir, nombre string, secs ...chispa3.Seccion) string {
	t.Helper()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, secs); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(dir, nombre)
	if err := os.WriteFile(ruta, buf.Bytes(), 0o644); err != nil {
		t.Fatal(err)
	}
	return ruta
}

func TestFusionarRespetaElTope(t *testing.T) {
	d := t.TempDir()
	a := escribirChispa(t, d, "a.chispa", chispa3.L0, 0)
	b := escribirChispa(t, d, "b.chispa", chispa3.L1, 9000)
	out := filepath.Join(d, "o.chispa")

	// la entrada no cabe en el tope
	if err := fusionar([]string{a, b}, out, chispa3.Limites{MaxFichero: 1000}); !errors.Is(err, chispa3.ErrTamano) {
		t.Fatalf("entrada con tope 1000: quería ErrTamano, salió %v", err)
	}
	// cada entrada cabe, la unión no
	if err := fusionar([]string{a, b}, out, chispa3.Limites{MaxFichero: 12000}); !errors.Is(err, chispa3.ErrTamano) {
		t.Fatalf("unión con tope 4000: quería ErrTamano, salió %v", err)
	}
	if _, err := os.Stat(out); err == nil {
		t.Error("no debe escribirse una unión que supera el tope")
	}
	// tope suficiente y por defecto (0)
	for _, tope := range []int64{1 << 20, 0} {
		if err := fusionar([]string{a, b}, out, chispa3.Limites{MaxFichero: tope}); err != nil {
			t.Fatalf("tope %d: %v", tope, err)
		}
		f, err := chispa3.Abrir(out)
		if err != nil {
			t.Fatal(err)
		}
		if !f.Tiene(chispa3.L0) || !f.Tiene(chispa3.L1) {
			t.Errorf("tope %d: faltan secciones", tope)
		}
		f.Close()
	}
}

func TestUnirVariosL0(t *testing.T) {
	d := t.TempDir()
	inj, urg, int_ := leerTestdata(t, "injection.chispa"), leerTestdata(t, "urgencia.chispa"), leerTestdata(t, "intencion.chispa")
	a := escribirSecciones(t, d, "a.chispa", chispa3.Seccion{Tipo: chispa3.L0, Datos: inj}, chispa3.Seccion{Tipo: chispa3.L1, Datos: make([]byte, 100)})
	b := escribirSecciones(t, d, "b.chispa", chispa3.Seccion{Tipo: chispa3.L0, Datos: urg})
	c := escribirSecciones(t, d, "c.chispa", chispa3.Seccion{Tipo: chispa3.L0, Datos: int_})
	out := filepath.Join(d, "o.chispa")

	// uno solo: sigue siendo L0, como antes
	if err := fusionar([]string{a}, out, chispa3.Limites{}); err != nil {
		t.Fatal(err)
	}
	f, err := chispa3.Abrir(out)
	if err != nil {
		t.Fatal(err)
	}
	if !f.Tiene(chispa3.L0) || f.Tiene(chispa3.L0MULTI) || !f.Tiene(chispa3.L1) {
		t.Errorf("un L0: secciones %v", f.Tipos())
	}
	f.Close()

	// varios: L0MULTI, y L1 se conserva
	if err := fusionar([]string{a, b, c}, out, chispa3.Limites{}); err != nil {
		t.Fatal(err)
	}
	f, err = chispa3.Abrir(out)
	if err != nil {
		t.Fatal(err)
	}
	if f.Tiene(chispa3.L0) || !f.Tiene(chispa3.L0MULTI) || !f.Tiene(chispa3.L1) {
		t.Errorf("tres L0: secciones %v", f.Tipos())
	}
	ms, err := f.L0Todos()
	if err != nil || len(ms) != 3 {
		t.Fatalf("L0Todos: %d %v", len(ms), err)
	}
	f.Close()

	// un L0MULTI como entrada se desempaqueta y se une con otro: se aplana, no se anida
	if err := fusionar([]string{out, a}, filepath.Join(d, "p.chispa"), chispa3.Limites{}); err == nil {
		t.Fatal("a ya está dentro de out: etiquetas repetidas")
	}
	d2 := escribirSecciones(t, d, "d.chispa", chispa3.Seccion{Tipo: chispa3.L0, Datos: inj})
	err = fusionar([]string{a, d2}, filepath.Join(d, "q.chispa"), chispa3.Limites{})
	if err == nil || !strings.Contains(err.Error(), "a.chispa") || !strings.Contains(err.Error(), "d.chispa") {
		t.Fatalf("debe nombrar los dos orígenes: %v", err)
	}
	if _, err := os.Stat(filepath.Join(d, "q.chispa")); err == nil {
		t.Error("no debe escribirse una unión rechazada")
	}
}
