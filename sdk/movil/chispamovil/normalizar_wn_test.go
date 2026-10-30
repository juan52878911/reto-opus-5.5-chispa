package chispamovil

import (
	"bytes"
	"encoding/json"
	"os"
	"strings"
	"testing"
)

func TestNormalizarMayusculasParidad(t *testing.T) {
	b, err := os.ReadFile("../../../server/decide/testdata/normalizacion.json")
	if err != nil {
		t.Fatal(err)
	}
	var f struct {
		Casos []struct{ Entrada, Salida string } `json:"casos"`
	}
	if err := json.Unmarshal(b, &f); err != nil {
		t.Fatal(err)
	}
	if len(f.Casos) != 12 {
		t.Fatalf("esperaba 12 casos, hay %d", len(f.Casos))
	}
	for _, c := range f.Casos {
		if g := NormalizarMayusculas(c.Entrada); g != c.Salida {
			t.Errorf("%q: %q, esperaba %q", c.Entrada, g, c.Salida)
		}
	}
}

func TestNormalizarMayusculasLimites(t *testing.T) {
	casos := map[string]string{
		"ABCDEFG":              "ABCDEFG",
		"ABCDEFGH":             "abcdefgh",
		"ABCDEFGhij":           "ABCDEFGhij",
		"ABCDEFGHij":           "abcdefghij",
		"ABCDEFGHIJKLMNopqrst": "ABCDEFGHIJKLMNopqrst", // 70 % exacto
		"ABCDEFGHIJKLMNOPqrst": "abcdefghijklmnopqrst",
		"ÑANDÚ ÁRBOL":          "ñandú árbol",
		"123 ABCDEFGH 😀":       "123 abcdefgh 😀",
		"1234567890":           "1234567890",
	}
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

// L2: el mensaje gritado y su minúscula dan los mismos ids; con 7 letras en mayúsculas no se toca. Necesita el .chispa-tok.
func TestTokenizarE5NormalizaMayusculas(t *testing.T) {
	ruta := os.Getenv("CHISPA_TOK")
	if ruta == "" {
		ruta = rutaTokPorDefecto()
	}
	if _, e := os.Stat(ruta); e != nil && os.Getenv("CHISPA_TOK") == "" {
		t.Skipf("sin .chispa-tok (CHISPA_TOK): %v", e)
	}
	c := &Chispa{}
	if err := c.CargarTokenizadorE5(ruta); err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(c.TokenizarE5("CANCELAR MI TARJETA YA"), c.TokenizarE5("cancelar mi tarjeta ya")) {
		t.Fatal("gritado y minúsculas deben dar los mismos ids")
	}
	if !bytes.Equal(c.TrozosE5("CANCELAR MI TARJETA YA"), c.TrozosE5("cancelar mi tarjeta ya")) {
		t.Fatal("TrozosE5: gritado y minúsculas deben dar los mismos ids")
	}
	if bytes.Equal(c.TokenizarE5("ABCDEFG"), c.TokenizarE5("abcdefg")) {
		t.Fatal("7 letras en mayúsculas no se tocan")
	}
}
