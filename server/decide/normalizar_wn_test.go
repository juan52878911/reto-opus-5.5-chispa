package decide

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"
)

func TestNormalizarMayusculasParidad(t *testing.T) {
	b, err := os.ReadFile("testdata/normalizacion.json")
	if err != nil {
		t.Fatal(err)
	}
	var f struct {
		Casos []struct{ Entrada, Salida string } `json:"casos"`
	}
	if err := json.Unmarshal(b, &f); err != nil {
		t.Fatal(err)
	}
	if len(f.Casos) != 16 {
		t.Fatalf("esperaba 16 casos, hay %d", len(f.Casos))
	}
	for _, c := range f.Casos {
		if g := NormalizarMayusculas(c.Entrada); g != c.Salida {
			t.Errorf("%q: %q, esperaba %q", c.Entrada, g, c.Salida)
		}
	}
}

func TestNormalizarMayusculasLimites(t *testing.T) {
	casos := map[string]string{
		"ABCDEFG":              "ABCDEFG",              // 7 letras
		"ABCDEFGH":             "abcdefgh",             // 8 letras
		"ABCDEFGhij":           "ABCDEFGhij",           // 70 % exacto
		"ABCDEFGHij":           "abcdefghij",           // 80 %
		"ABCDEFGHIJKLMNopqrst": "ABCDEFGHIJKLMNopqrst", // 70 % exacto (14/20)
		"ABCDEFGHIJKLMNOPqrst": "abcdefghijklmnopqrst", // 80 %
		"ÑANDÚ ÁRBOL":          "ñandú árbol",
		"123 ABCDEFGH 😀":       "123 abcdefgh 😀",
		"1234567890":           "1234567890",
	}
	// 71 %: 71 mayúsculas y 29 minúsculas.
	casos[strings.Repeat("A", 71)+strings.Repeat("b", 29)] = strings.Repeat("a", 71) + strings.Repeat("b", 29)
	casos[strings.Repeat("A", 70)+strings.Repeat("b", 30)] = strings.Repeat("A", 70) + strings.Repeat("b", 30)
	for in, want := range casos {
		g := NormalizarMayusculas(in)
		if g != want {
			t.Errorf("%q: %q, esperaba %q", in, g, want)
		}
		if NormalizarMayusculas(g) != g {
			t.Errorf("no idempotente en %q", in)
		}
	}
}

// tokenizador y sesión que dejan ver el texto: los ids son los bytes del mensaje, y las ranuras salen de ellos.
type tokTexto struct{ vistos *[]string }

func (k tokTexto) IDs(s string) []int64 {
	*k.vistos = append(*k.vistos, s)
	ids := []int64{0}
	for _, b := range []byte(s) {
		ids = append(ids, int64(b))
	}
	return append(ids, 2)
}

type sesionTexto struct{}

func (sesionTexto) Ranuras(ids []int64) ([][]float32, error) {
	var s float32
	for _, i := range ids {
		s += float32(i%7) / 10
	}
	return [][]float32{{s, 1}}, nil
}

func TestL2NormalizaMensajeGritado(t *testing.T) {
	vistos := []string{}
	l := l2NoulFalso(t, tokTexto{&vistos})
	dec := func(estado string) Respuesta {
		r, err := l.Decidir(context.Background(), Pregunta{Texto: "n", Estado: estado, Kind: KindNoul, Opciones: []Opcion{{ID: "true"}, {ID: "false"}}})
		if err != nil {
			t.Fatal(err)
		}
		return r
	}
	a, b := dec("CANCELAR MI TARJETA YA"), dec("cancelar mi tarjeta ya")
	if a.Probs["true"] != b.Probs["true"] {
		t.Fatalf("gritado %v != minúsculas %v", a.Probs, b.Probs)
	}
	if vistos[0] != "cancelar mi tarjeta ya" {
		t.Fatalf("el tokenizador vio %q", vistos[0])
	}
	vistos = vistos[:0]
	dec("ABCDEFG") // 7 letras: no se toca
	if vistos[0] != "ABCDEFG" {
		t.Fatalf("7 letras tocadas: %q", vistos[0])
	}
}
