package chispa3

import (
	"bytes"
	"encoding/hex"
	"os"
	"sort"
	"testing"
)

// Contenido determinista de los ficheros testdata/claves-v2.chispa (lo escribe Python: sdk/python/tests/test_claves_v2.py)
// y testdata/claves-v2-go.chispa (lo escribe este test con CHISPA_GEN=1; Python lo lee y compara). Misma receta en los dos:
// una entrada por hash distinto de los vectores, en el orden del JSON; dim 4.
func seccionesClavesV2(t *testing.T) (esq, conj []byte) {
	var es []EntradaEsquema2
	var cs []EntradaConj
	vistos := map[string]bool{}
	for i, v := range cargarVectores2(t) {
		if vistos[v.Hash] {
			continue
		}
		vistos[v.Hash] = true
		raw, _ := hex.DecodeString(v.Hash)
		h := [16]byte(raw)
		es = append(es, EntradaEsquema2{h, 0.5 * float32(i+1), []int8{int8(i + 1), -int8(i + 1), 2, -2}})
		var ids []string
		for _, o := range v.Opciones {
			ids = append(ids, o.ID)
		}
		sort.Strings(ids)
		c := len(ids)
		e := EntradaConj{Hash2: h, Cabeza: CabezaLR, K: 1, D: 4, T: 0.05, Beta: 1, Esc: [3]float32{1, 1, 1},
			W: []float32{1, 0.5, 0.25, 0, 0, 0}, Clases: ids, Escala: make([]float32, c), Proto: make([]byte, c*4)}
		for j := range e.Escala {
			e.Escala[j] = 0.5
		}
		for j := range e.Proto {
			e.Proto[j] = byte(int8(j + 1 - 4))
		}
		cs = append(cs, e)
	}
	var err error
	if esq, err = CodificarEsquemas2(4, es); err != nil {
		t.Fatal(err)
	}
	if conj, err = CodificarConj2(cs); err != nil {
		t.Fatal(err)
	}
	return
}

func TestFicheroV2EscritoPorGo(t *testing.T) {
	esq, conj := seccionesClavesV2(t)
	const ruta = "testdata/claves-v2-go.chispa"
	if os.Getenv("CHISPA_GEN") != "" {
		f, err := os.Create(ruta)
		if err != nil {
			t.Fatal(err)
		}
		if err := Escribir(f, []Seccion{{Tipo: ESQUEMAS, Datos: esq}, {Tipo: CONJ, Datos: conj}}); err != nil {
			t.Fatal(err)
		}
		f.Close()
	}
	leerYComparar(t, ruta, esq, conj)
}

func TestFicheroV2EscritoPorPython(t *testing.T) {
	esq, conj := seccionesClavesV2(t)
	leerYComparar(t, "testdata/claves-v2.chispa", esq, conj)
}

func leerYComparar(t *testing.T, ruta string, esq, conj []byte) {
	f, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	for tipo, want := range map[Tipo][]byte{ESQUEMAS: esq, CONJ: conj} {
		got, err := f.Bytes(tipo)
		if err != nil || !bytes.Equal(got, want) {
			t.Errorf("%s: bytes distintos de los de Go (err %v)", tipo, err)
		}
	}
	e, err := f.Esquemas()
	if err != nil || e.Version() != 2 {
		t.Fatalf("ESQUEMAS: %v", err)
	}
	c, err := f.Conj()
	if err != nil || c.Version() != 2 {
		t.Fatalf("CONJ: %v", err)
	}
	for _, v := range cargarVectores2(t) {
		raw, _ := hex.DecodeString(v.Hash)
		if _, _, ok := e.Buscar2([16]byte(raw)); !ok {
			t.Errorf("ESQUEMAS sin %s", v.Nombre)
		}
		if _, ok := c.Buscar2([16]byte(raw)); !ok {
			t.Errorf("CONJ sin %s", v.Nombre)
		}
	}
}
