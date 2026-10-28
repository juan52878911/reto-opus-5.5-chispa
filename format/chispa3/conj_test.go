package chispa3

import (
	"bytes"
	"encoding/binary"
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func entradaConj(nombre string, c, k, d int) EntradaConj {
	e := EntradaConj{Hash: HashEsquema(nombre, []string{"a", "b"}), Cabeza: CabezaLR, K: k, D: d, T: 0.02, Beta: 1.5,
		Esc: [3]float32{1, 2, 3}, W: []float32{1, 1, 1, 0.1, -0.2, 0.3}}
	for i := 0; i < c; i++ {
		e.Clases = append(e.Clases, string(rune('a'+i))+"ñ")
	}
	for i := 0; i < c*k; i++ {
		e.Escala = append(e.Escala, float32(i)/100)
	}
	for i := 0; i < c*k*d; i++ {
		e.Proto = append(e.Proto, byte(i*7))
	}
	return e
}

func conjDePrueba(t testing.TB) []byte {
	t.Helper()
	b, err := CodificarConj([]EntradaConj{entradaConj("q2", 3, 2, 4), entradaConj("q1", 2, 2, 4)})
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func TestConjIdaYVuelta(t *testing.T) {
	// Un fichero sin CONJ sigue cargando igual; con CONJ añade la sección y las demás no cambian.
	sin := seccionesDePrueba(t)
	con := append(append([]Seccion(nil), sin...), Seccion{CONJ, conjDePrueba(t)})
	ruta := filepath.Join(t.TempDir(), "x.chispa")
	if err := os.WriteFile(ruta, construir(t, sin), 0o644); err != nil {
		t.Fatal(err)
	}
	f, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	if f.Tiene(CONJ) || len(f.Tipos()) != 6 {
		t.Fatalf("tipos %v", f.Tipos())
	}
	if _, err := f.Conj(); !errors.Is(err, ErrNoHay) {
		t.Fatal(err)
	}
	f.Close()
	// Las seis secciones antiguas siguen en los mismos bytes: CONJ va al final del enum y de la tabla.
	if !bytes.Equal(construir(t, sin)[tamCabecera+6*tamEntrada:], construir(t, con)[tamCabecera+7*tamEntrada:][:len(construir(t, sin))-tamCabecera-6*tamEntrada]) {
		t.Fatal("las secciones previas cambian de bytes")
	}
	if err := os.WriteFile(ruta, construir(t, con), 0o644); err != nil {
		t.Fatal(err)
	}
	f, err = Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	if err := f.Verificar(); err != nil {
		t.Fatal(err)
	}
	c, err := f.Conj()
	if err != nil || c.Len() != 2 {
		t.Fatal(c, err)
	}
	e, ok := c.Buscar(HashEsquema("q2", []string{"a", "b"}))
	want := entradaConj("q2", 3, 2, 4)
	if !ok || e.K != 2 || e.D != 4 || e.T != 0.02 || e.Beta != 1.5 || e.Esc != want.Esc ||
		len(e.Clases) != 3 || e.Clases[2] != "cñ" || !bytes.Equal(e.Proto, want.Proto) || e.Escala[5] != 0.05 || e.W[5] != 0.3 {
		t.Fatalf("%+v", e)
	}
	if _, ok := c.Buscar(HashEsquema("q3", nil)); ok {
		t.Fatal("hash ausente encontrado")
	}
	if CONJ.String() != "CONJ" || CONJ != 7 {
		t.Fatal("CONJ debe ser el tipo 7")
	}
}

func TestConjInvalido(t *testing.T) {
	ok := conjDePrueba(t)
	pon := func(off int, v uint32) []byte {
		b := append([]byte(nil), ok...)
		binary.LittleEndian.PutUint32(b[off:], v)
		return b
	}
	casos := map[string][]byte{
		"vacío": nil, "versión": pon(0, 2), "n enorme": pon(4, 1<<30), "n mayor": pon(4, 3), "n menor": pon(4, 1),
		"cabeza": pon(8+32, 9), "K cero": pon(8+32+4, 0), "d enorme": pon(8+32+8, 1<<20), "C enorme": pon(8+32+12, 1<<30),
		"nw": pon(8+32+16, 5), "T cero": pon(8+32+20, 0), "nan": pon(8+32+24, 0x7fc00000),
		"esc cero": pon(8+32+28, 0), "truncado": ok[:len(ok)-1], "sobrante": append(append([]byte(nil), ok...), 0),
	}
	for n, b := range casos {
		if _, err := DecodificarConj(b); !errors.Is(err, ErrContenido) {
			t.Errorf("%s: %v", n, err)
		}
	}
	a, b := entradaConj("q", 2, 1, 2), entradaConj("q", 2, 1, 2)
	if _, err := CodificarConj([]EntradaConj{a, b}); !errors.Is(err, ErrContenido) {
		t.Errorf("hash repetido: %v", err)
	}
	a.Clases = []string{"b", "a"}
	if _, err := CodificarConj([]EntradaConj{a}); !errors.Is(err, ErrContenido) {
		t.Errorf("clases desordenadas: %v", err)
	}
}

func FuzzConj(f *testing.F) {
	f.Add(conjDePrueba(f))
	b, _ := CodificarConj([]EntradaConj{entradaConj("z", 1, 1, 1)})
	f.Add(b)
	f.Add([]byte{})
	f.Add([]byte{1, 0, 0, 0, 0, 0, 0, 0})
	f.Fuzz(func(t *testing.T, data []byte) {
		c, err := DecodificarConj(data)
		if err != nil {
			return
		}
		// Lo que se decodifica se vuelve a codificar idéntico y cada entrada se encuentra.
		for i := range c.es {
			if e, ok := c.Buscar(c.es[i].Hash); !ok || e != &c.es[i] {
				t.Fatal("Buscar no encuentra una entrada válida")
			}
		}
		if re, err := CodificarConj(c.es); err != nil || !bytes.Equal(re, data) {
			t.Fatalf("no es canónico: %v", err)
		}
	})
}
