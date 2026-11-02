package main

import (
	"bytes"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"chispa/format/chispa3"
)

func escribirChispa(t *testing.T, dir, nombre string, tipo chispa3.Tipo, n int) string {
	t.Helper()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, []chispa3.Seccion{{Tipo: tipo, Datos: make([]byte, n)}}); err != nil {
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
	a := escribirChispa(t, d, "a.chispa", chispa3.L0, 3000)
	b := escribirChispa(t, d, "b.chispa", chispa3.L1, 3000)
	out := filepath.Join(d, "o.chispa")

	// la entrada no cabe en el tope
	if err := fusionar([]string{a, b}, out, chispa3.Limites{MaxFichero: 1000}); !errors.Is(err, chispa3.ErrTamano) {
		t.Fatalf("entrada con tope 1000: quería ErrTamano, salió %v", err)
	}
	// cada entrada cabe, la unión no
	if err := fusionar([]string{a, b}, out, chispa3.Limites{MaxFichero: 4000}); !errors.Is(err, chispa3.ErrTamano) {
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
