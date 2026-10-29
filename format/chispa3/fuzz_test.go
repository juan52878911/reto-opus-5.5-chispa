package chispa3

import (
	"encoding/binary"
	"testing"
)

func FuzzDecodificarEsquemas(f *testing.F) {
	var h1, h2 [32]byte
	h1[0], h2[0] = 1, 2
	b, _ := CodificarEsquemas(4, []EntradaEsquema{{h1, 0.5, []int8{1, -2, 3, 4}}, {h2, 1, []int8{0, 0, 0, 0}}})
	f.Add(b)
	f.Add([]byte{})
	f.Add([]byte{255, 255, 255, 255, 255, 255, 255, 255})
	f.Add([]byte{0, 16, 0, 0, 255, 255, 255, 0})
	f.Fuzz(func(t *testing.T, data []byte) {
		e, err := DecodificarEsquemas(data)
		if err != nil {
			return
		}
		for i := 0; i < e.Len(); i++ {
			if v, _, ok := e.buscar(e.hash(i)); !ok || len(v) != e.Dim() {
				t.Fatal("Buscar no encuentra una entrada válida")
			}
		}
		var h [32]byte
		e.Buscar(h)
	})
}

func FuzzDecodificarTORR(f *testing.F) {
	b, _ := CodificarTORR(torrDePrueba())
	f.Add(b)
	f.Add([]byte{})
	f.Add(b[:torrCab])
	f.Add([]byte{1, 0, 0, 0, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 1})
	f.Fuzz(func(t *testing.T, data []byte) {
		tr, err := DecodificarTORR(data)
		if err != nil {
			return
		}
		// Ida y vuelta: lo que se decodifica se recodifica a los mismos bytes.
		again, err := CodificarTORR(tr)
		if err != nil {
			t.Fatalf("recodificar: %v", err)
		}
		if string(again) != string(data) {
			t.Fatal("la ida y vuelta de TORR no es idéntica")
		}
	})
}

// FuzzAbrirTORR muta ficheros v3 completos con TORR y ESQUEMAS, sin pasar por el sha: arregla
// CRC y sha para que las mutaciones lleguen a los decodificadores de sección.
func FuzzAbrirTORR(f *testing.F) {
	tb, _ := CodificarTORR(torrDePrueba())
	s := append(seccionesDePrueba(f), Seccion{TORR, tb})
	f.Add(construir(f, s))
	f.Add(construir(f, s[len(s)-1:]))
	lim := Limites{MaxFichero: 1 << 22, MaxSeccion: 1 << 22}
	f.Fuzz(func(t *testing.T, data []byte) {
		fi, err := Desde(data, lim)
		if err != nil {
			return
		}
		fi.Verificar()
		fi.Meta()
		fi.Calib()
		fi.Esquemas()
		fi.Torre()
		fi.Conj()
		fi.L0TF()
		fi.L1()
		fi.L2()
	})
}

// Cabeceras con longitudes enormes no deben reservar memoria sin tope.
func TestLongitudesEnormesSinReservar(t *testing.T) {
	le := binary.LittleEndian
	cab := func(n uint32, total uint64) []byte {
		b := make([]byte, tamCabecera+64)
		copy(b, magia[:])
		le.PutUint16(b[8:], Version)
		le.PutUint32(b[12:], n)
		le.PutUint64(b[16:], total)
		return b
	}
	for _, c := range [][]byte{cab(1<<32-1, 1<<63), cab(1<<32-1, 1<<64-1), cab(1, 1<<62), cab(0, 0)} {
		if _, err := Desde(c, Limites{}); err == nil {
			t.Error("cabecera hostil aceptada")
		}
	}
	allocs := testing.AllocsPerRun(5, func() {
		DecodificarEsquemas([]byte{0, 16, 0, 0, 255, 255, 255, 255})
		DecodificarTORR([]byte{1, 0, 0, 0, 0, 16, 0, 0, 255, 255, 0, 0, 255, 255, 255, 255, 1})
		DecodificarConj([]byte{ConjVersion, 0, 0, 0, 255, 255, 255, 255})
		DecodificarL0TF([]byte{L0TFVersion, 0, 0, 0, 255, 255, 255, 255, 255, 255, 255, 255, 0, 0, 0, 0})
	})
	if allocs > 30 {
		t.Errorf("%v reservas con cabeceras enormes", allocs)
	}
}
