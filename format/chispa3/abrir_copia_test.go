//go:build unix

package chispa3

import (
	"os"
	"testing"
)

// Reescribir y truncar el fichero en uso no debe tocar los datos abiertos por defecto (con Mmap daría SIGBUS).
func TestAbrirSobrevivePisarElFichero(t *testing.T) {
	orig, err := os.ReadFile("testdata/urgencia.chispa")
	if err != nil {
		t.Fatal(err)
	}
	ruta := t.TempDir() + "/m.chispa"
	if err := os.WriteFile(ruta, orig, 0o600); err != nil {
		t.Fatal(err)
	}
	f, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	grande := func() []byte {
		var g []byte
		for _, tp := range f.Tipos() {
			if d, err := f.Bytes(tp); err == nil && len(d) > len(g) {
				g = d
			}
		}
		return g
	}
	copia := append([]byte(nil), grande()...)
	if err := os.Truncate(ruta, 0); err != nil {
		t.Fatal(err)
	}
	tras := grande()
	if len(tras) == 0 || string(tras) != string(copia) {
		t.Fatal("los datos cambiaron al truncar el fichero")
	}
}

// Con Mmap explícito se conserva el mapeo (comprobado solo que abre y valida).
func TestAbrirMmapOpcional(t *testing.T) {
	f, err := AbrirCon("testdata/urgencia.chispa", Limites{Mmap: true})
	if err != nil {
		t.Fatal(err)
	}
	f.Close()
}
