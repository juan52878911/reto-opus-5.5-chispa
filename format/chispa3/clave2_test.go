package chispa3

import (
	"encoding/hex"
	"encoding/json"
	"os"
	"testing"
)

type vectorClave2 struct {
	Nombre   string `json:"nombre"`
	Pregunta string `json:"pregunta"`
	Kind     string `json:"kind"`
	Opciones []struct {
		ID          string `json:"id"`
		Description string `json:"description"`
	} `json:"opciones"`
	Hash string `json:"hash"`
}

func cargarVectores2(t *testing.T) []vectorClave2 {
	b, err := os.ReadFile("vectores-clave-v2.json")
	if err != nil {
		t.Fatal(err)
	}
	var f struct {
		Vectores []vectorClave2 `json:"vectores"`
	}
	if err := json.Unmarshal(b, &f); err != nil {
		t.Fatal(err)
	}
	return f.Vectores
}

func (v vectorClave2) ops() []OpcionClave {
	var o []OpcionClave
	for _, x := range v.Opciones {
		o = append(o, OpcionClave{x.ID, x.Description})
	}
	return o
}

func TestHashEsquema2Vectores(t *testing.T) {
	vs := cargarVectores2(t)
	if len(vs) < 4 {
		t.Fatalf("solo %d vectores", len(vs))
	}
	vistos := map[string]string{}
	for _, v := range vs {
		h := HashEsquema2(v.Pregunta, v.Kind, v.ops())
		if got := hex.EncodeToString(h[:]); got != v.Hash {
			t.Errorf("%s: %s, esperado %s", v.Nombre, got, v.Hash)
		}
		if c := ClaveConj2(v.Pregunta, v.Kind, v.ops()); c != h {
			t.Errorf("%s: ClaveConj2 distinta", v.Nombre)
		}
		if o, ok := vistos[v.Hash]; ok && !(o == "choice_con_descripciones" && v.Nombre == "choice_opciones_desordenadas") {
			t.Errorf("%s colisiona con %s", v.Nombre, o)
		}
		vistos[v.Hash] = v.Nombre
	}
	// El desordenado da la misma clave que el ordenado; la otra descripción, otra distinta.
	por := map[string]string{}
	for _, v := range vs {
		por[v.Nombre] = v.Hash
	}
	if por["choice_con_descripciones"] != por["choice_opciones_desordenadas"] {
		t.Error("el orden de las opciones cambia la clave")
	}
	if por["choice_con_descripciones"] == por["choice_otra_descripcion"] {
		t.Error("la descripción no cambia la clave")
	}
}

func TestHashEsquema2KindYNoMuta(t *testing.T) {
	o := []OpcionClave{{"b", "x"}, {"a", "y"}}
	a := HashEsquema2("q", "choice", o)
	if o[0].ID != "b" {
		t.Error("ordenó el argumento")
	}
	if a == HashEsquema2("q", "multi", o) {
		t.Error("kind no entra en la clave")
	}
}

func TestEsquemasV2IdaYVuelta(t *testing.T) {
	h1 := HashEsquema2("q", "choice", []OpcionClave{{"a", "d"}})
	h2 := HashEsquema2("q", "choice", []OpcionClave{{"a", "otra"}})
	b, err := CodificarEsquemas2(2, []EntradaEsquema2{{h1, 0.5, []int8{1, -2}}, {h2, 0.25, []int8{3, 4}}})
	if err != nil {
		t.Fatal(err)
	}
	e, err := DecodificarEsquemas(b)
	if err != nil {
		t.Fatal(err)
	}
	if e.Version() != 2 || e.Len() != 2 || e.Dim() != 2 {
		t.Fatalf("v%d len %d dim %d", e.Version(), e.Len(), e.Dim())
	}
	if v, s, ok := e.Buscar2(h1); !ok || s != 0.5 || int8(v[1]) != -2 {
		t.Error("h1")
	}
	if v, s, ok := e.Buscar2(h2); !ok || s != 0.25 || int8(v[0]) != 3 {
		t.Error("h2")
	}
	// Las claves de las dos versiones no se mezclan.
	if _, _, ok := e.Buscar(HashEsquema("q", []string{"a"})); ok {
		t.Error("v2 respondió a una clave v1")
	}
	// v1 intacto: la misma entrada en v1 no responde a Buscar2 y su primera palabra es dim.
	b1, _ := CodificarEsquemas(2, []EntradaEsquema{{HashEsquema("q", []string{"a"}), 1, []int8{1, 2}}})
	e1, err := DecodificarEsquemas(b1)
	if err != nil || e1.Version() != 1 {
		t.Fatal(err)
	}
	if _, _, ok := e1.Buscar2(h1); ok {
		t.Error("v1 respondió a una clave v2")
	}
	if _, _, ok := e1.Buscar(HashEsquema("q", []string{"a"})); !ok {
		t.Error("v1 no encuentra su clave")
	}
	if _, err := CodificarEsquemas2(2, []EntradaEsquema2{{h1, 1, []int8{1, 2}}, {h1, 1, []int8{1, 2}}}); err == nil {
		t.Error("hash repetido aceptado")
	}
	b[2] = 9 // versión 9
	if _, err := DecodificarEsquemas(b); err == nil {
		t.Error("versión desconocida aceptada")
	}
}

func entradaConjPrueba(c int) EntradaConj {
	cl := []string{"a", "b"}[:c]
	return EntradaConj{Cabeza: CabezaLR, K: 1, D: 2, T: 0.05, Beta: 1, Esc: [3]float32{1, 1, 1}, W: make([]float32, ConjPesosLR),
		Clases: cl, Escala: make([]float32, c), Proto: make([]byte, c*2)}
}

func TestConjV2IdaYVuelta(t *testing.T) {
	ops := []OpcionClave{{"a", "da"}, {"b", "db"}}
	e := entradaConjPrueba(2)
	e.Hash2 = ClaveConj2("q", "choice", ops)
	otra := entradaConjPrueba(2)
	otra.Hash2 = ClaveConj2("q", "choice", []OpcionClave{{"a", "da"}, {"b", "distinta"}})
	b, err := CodificarConj2([]EntradaConj{e, otra})
	if err != nil {
		t.Fatal(err)
	}
	c, err := DecodificarConj(b)
	if err != nil {
		t.Fatal(err)
	}
	if c.Version() != 2 || c.Len() != 2 {
		t.Fatalf("v%d len %d", c.Version(), c.Len())
	}
	if _, ok := c.Buscar2(e.Hash2); !ok {
		t.Error("no encuentra la clave v2")
	}
	if _, ok := c.Buscar([32]byte{}); ok {
		t.Error("v2 respondió a una clave v1")
	}
	// v1 sigue igual.
	e1 := entradaConjPrueba(2)
	e1.Hash = ClaveConj("q", []string{"a", "b"})
	b1, err := CodificarConj([]EntradaConj{e1})
	if err != nil {
		t.Fatal(err)
	}
	c1, err := DecodificarConj(b1)
	if err != nil || c1.Version() != 1 {
		t.Fatal(err)
	}
	if _, ok := c1.Buscar(e1.Hash); !ok {
		t.Error("v1 no encuentra su clave")
	}
	if _, ok := c1.Buscar2(e.Hash2); ok {
		t.Error("v1 respondió a una clave v2")
	}
	if _, err := CodificarConj2([]EntradaConj{e, e}); err == nil {
		t.Error("hash repetido aceptado")
	}
}
