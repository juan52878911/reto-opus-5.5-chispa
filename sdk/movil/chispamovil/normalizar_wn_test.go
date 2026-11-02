package chispamovil

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"os"
	"slices"
	"strings"
	"testing"

	"chispa/runtime/tok"
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
	if len(f.Casos) != 15 {
		t.Fatalf("esperaba 15 casos, hay %d", len(f.Casos))
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

// El tokenizador del móvil es puro: no normaliza, así que es idéntico a runtime/tok. La normalización la aplica quien llama a L2
// (Kotlin y Swift, con NormalizarMayusculas): normalizado y minúsculas dan los mismos ids; sin normalizar, no. Necesita el .chispa-tok.
func chispaConTok(t *testing.T) *Chispa {
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
	return c
}

func TestNormalizaAntesDeTokenizarE5(t *testing.T) {
	c := chispaConTok(t)
	g := NormalizarMayusculas("CANCELAR MI TARJETA YA")
	if !bytes.Equal(c.TokenizarE5(g), c.TokenizarE5("cancelar mi tarjeta ya")) {
		t.Fatal("normalizado y minúsculas deben dar los mismos ids")
	}
	if !bytes.Equal(c.TrozosE5(g), c.TrozosE5("cancelar mi tarjeta ya")) {
		t.Fatal("TrozosE5: normalizado y minúsculas deben dar los mismos ids")
	}
	if NormalizarMayusculas("ABCDEFG") != "ABCDEFG" || !bytes.Equal(c.TokenizarE5(NormalizarMayusculas("ABCDEFG")), c.TokenizarE5("ABCDEFG")) {
		t.Fatal("7 letras en mayúsculas no se tocan")
	}
}

func TestTokenizarE5NoNormaliza(t *testing.T) {
	c := chispaConTok(t)
	ruta := os.Getenv("CHISPA_TOK")
	if ruta == "" {
		ruta = rutaTokPorDefecto()
	}
	ref, err := tok.Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	b := c.TokenizarE5("HOLA MUNDO GRITADO")
	got := make([]int32, len(b)/4)
	for i := range got {
		got[i] = int32(binary.LittleEndian.Uint32(b[4*i:]))
	}
	if !slices.Equal(got, ref.Tokenizar("HOLA MUNDO GRITADO")) {
		t.Fatal("TokenizarE5 debe ser igual a runtime/tok sin normalizar")
	}
	if bytes.Equal(c.TokenizarE5("HOLA MUNDO GRITADO"), c.TokenizarE5("hola mundo gritado")) {
		t.Fatal("TokenizarE5 no debe normalizar: debe coincidir con runtime/tok sin normalizar")
	}
	if bytes.Equal(c.TrozosE5("HOLA MUNDO GRITADO"), c.TrozosE5("hola mundo gritado")) {
		t.Fatal("TrozosE5 no debe normalizar")
	}
}
