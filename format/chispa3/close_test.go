package chispa3

import (
	"bytes"
	"errors"
	"runtime"
	"sync"
	"testing"
)

func ficheroPrueba(t testing.TB, n int) []byte {
	t.Helper()
	var b bytes.Buffer
	if err := Escribir(&b, []Seccion{{Tipo: L0, Datos: bytes.Repeat([]byte{7}, n)}}); err != nil {
		t.Fatal(err)
	}
	return b.Bytes()
}

func TestCloseIdempotenteYSuelta(t *testing.T) {
	f, err := Desde(ficheroPrueba(t, 1024), Limites{})
	if err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
	if err := f.Close(); err != nil {
		t.Fatal(err)
	}
	if f.data != nil || f.sec != nil || f.orden != nil || f.cerrar != nil {
		t.Fatal("Close no soltó los datos")
	}
	if _, err := f.Bytes(L0); !errors.Is(err, ErrCerrado) {
		t.Fatalf("Bytes tras Close: %v", err)
	}
	if f.Tiene(L0) || len(f.Tipos()) != 0 {
		t.Fatal("Tiene/Tipos tras Close deben estar vacíos")
	}
	_ = f.Verificar()
}

func TestCloseConcurrente(t *testing.T) {
	f, _ := Desde(ficheroPrueba(t, 4096), Limites{})
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for j := 0; j < 200; j++ {
				f.Bytes(L0)
				f.Tiene(L0)
				f.Tipos()
				f.Verificar()
			}
		}()
	}
	for i := 0; i < 4; i++ {
		wg.Add(1)
		go func() { defer wg.Done(); f.Close() }()
	}
	wg.Wait()
}

// Tras 200 recargas (abrir + usar + cerrar, conservando los *Fichero) el heap no crece: tolerancia amplia (el doble
// de un fichero de 1 MiB, frente a los 200 MiB que quedarían retenidos).
func TestRecargasNoRetienenMemoria(t *testing.T) {
	data := ficheroPrueba(t, 1<<20)
	var viejos []*Fichero
	heap := func() uint64 {
		runtime.GC()
		runtime.GC()
		var m runtime.MemStats
		runtime.ReadMemStats(&m)
		return m.HeapAlloc
	}
	base := heap()
	for i := 0; i < 200; i++ {
		cp := append([]byte(nil), data...)
		f, err := Desde(cp, Limites{})
		if err != nil {
			t.Fatal(err)
		}
		if _, err := f.Bytes(L0); err != nil {
			t.Fatal(err)
		}
		f.Close()
		viejos = append(viejos, f)
	}
	fin := heap()
	runtime.KeepAlive(viejos)
	if fin > base+8<<20 {
		t.Fatalf("heap creció %d MiB tras 200 recargas", (fin-base)>>20)
	}
}
