package torre

import (
	"errors"
	"math"
	"os"
	"slices"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"chispa/runtime/tok"
)

type tokFalso struct{ textos []string }

func (t *tokFalso) IDsPasaje(texto string) []int64 {
	t.textos = append(t.textos, texto)
	ids := []int64{0}
	for range strings.Fields(texto) {
		ids = append(ids, 9)
	}
	return append(ids, 2)
}

type sesionFalsa struct {
	ids, mascara []int64
	h            []float32
	err          error
}

func (s *sesionFalsa) Embeber(ids, mascara []int64) ([]float32, error) {
	s.ids, s.mascara = ids, mascara
	return s.h, s.err
}

func meta(dim, maxLen int) chispa3.Torre {
	return chispa3.Torre{Dim: dim, MaxLen: maxLen, Prefijo: "passage: "}
}

func TestTorreUnaVezElPrefijo(t *testing.T) {
	tk, ses := &tokFalso{}, &sesionFalsa{h: []float32{1, 0}}
	c := Nuevo(ses, tk, meta(2, 128))
	for _, in := range []string{"passage: ¿p? · a · d", "¿p? · a · d"} {
		if _, err := c.Torre(in); err != nil {
			t.Fatal(err)
		}
	}
	// El tokenizador recibe el texto sin prefijo (lo antepone él): nunca «passage: passage: ».
	if tk.textos[0] != "¿p? · a · d" || tk.textos[1] != "¿p? · a · d" {
		t.Fatalf("%q", tk.textos)
	}
	if len(ses.mascara) != len(ses.ids) || slices.Contains(ses.mascara, 0) {
		t.Fatalf("máscara %v para %v", ses.mascara, ses.ids)
	}
}

func TestTorreTruncaYValida(t *testing.T) {
	ses := &sesionFalsa{h: []float32{1, 0}}
	c := Nuevo(ses, &tokFalso{}, meta(2, 5))
	if _, err := c.Torre(strings.Repeat("x ", 50)); err != nil {
		t.Fatal(err)
	}
	if !slices.Equal(ses.ids, []int64{0, 9, 9, 9, 2}) { // max_len de la sección = 5, con </s> al final
		t.Fatalf("ids %v", ses.ids)
	}
	ses.h = []float32{1}
	if _, err := c.Torre("a"); err == nil {
		t.Fatal("dimensión mala aceptada")
	}
	ses.h = []float32{float32(math.NaN()), 0}
	if _, err := c.Torre("a"); err == nil {
		t.Fatal("NaN aceptado")
	}
	ses.h, ses.err = []float32{1, 0}, errors.New("boom")
	if _, err := c.Torre("a"); err == nil {
		t.Fatal("error de la sesión perdido")
	}
}

// Sin ORT, Abrir lo dice en vez de entrar en pánico.
func TestAbrirSinORT(t *testing.T) {
	_, err := Abrir(chispa3.Torre{Dim: 2, MaxLen: 8, Prefijo: "passage: ", ONNX: []byte{1}}, &tokFalso{})
	if err == nil {
		t.Skip("compilado con ORT")
	}
	if !errors.Is(err, ErrSinORT) {
		t.Fatal(err)
	}
	if _, err := Abrir(chispa3.Torre{}, nil); err == nil {
		t.Fatal("sin tokenizador")
	}
}

// tokReal adapta runtime/tok (si hay .chispa-tok) y comprueba que el texto con U+00B7 llega a la sesión con ids de pasaje.
type tokReal struct{ t *tok.Tokenizador }

func (r tokReal) IDsPasaje(s string) []int64 {
	out := []int64{}
	for _, v := range r.t.TokenizarPasaje(s) {
		out = append(out, int64(v))
	}
	return out
}

func TestTorreConTokenizadorReal(t *testing.T) {
	ruta := os.Getenv("CHISPA_TOK")
	if ruta == "" {
		ruta = "/tmp/e5.chispa-tok"
	}
	tk, err := tok.Abrir(ruta)
	if err != nil {
		t.Skip("sin .chispa-tok:", err)
	}
	ses := &sesionFalsa{h: []float32{1, 0}}
	c := Nuevo(ses, tokReal{tk}, meta(2, 128))
	txt := "passage: ¿Es una queja? · true · "
	if _, err := c.Torre(txt); err != nil {
		t.Fatal(err)
	}
	want := tokReal{tk}.IDsPasaje("¿Es una queja? · true · ")
	if !slices.Equal(ses.ids, want) || ses.ids[0] != 0 || ses.ids[len(ses.ids)-1] != 2 {
		t.Fatalf("ids %v, esperaba %v", ses.ids, want)
	}
}
