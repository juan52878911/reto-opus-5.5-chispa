package tok

import (
	"bufio"
	"encoding/json"
	"os"
	"slices"
	"strings"
	"testing"
	"unicode/utf8"
)

type caso struct {
	Texto string  `json:"texto"`
	IDs   []int32 `json:"ids"`
}

func abrir(t testing.TB) *Tokenizador {
	ruta := os.Getenv("CHISPA_TOK")
	if ruta == "" {
		ruta = "/tmp/e5.chispa-tok"
	}
	tk, err := Abrir(ruta)
	if err != nil {
		t.Skipf("sin .chispa-tok (exportar.py; CHISPA_TOK): %v", err)
	}
	return tk
}

func leer(t testing.TB, ruta string) []caso {
	f, err := os.Open(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	var out []caso
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<24)
	for sc.Scan() {
		var c caso
		if err := json.Unmarshal(sc.Bytes(), &c); err != nil {
			t.Fatal(err)
		}
		out = append(out, c)
	}
	return out
}

func comparar(t *testing.T, tk *Tokenizador, casos []caso) {
	mal := 0
	for _, c := range casos {
		if got := tk.Tokenizar(c.Texto); !slices.Equal(got, c.IDs) {
			mal++
			if mal <= 8 {
				t.Errorf("texto %q\n  go : %v\n  py : %v", c.Texto, got, c.IDs)
			}
		}
	}
	t.Logf("%d frases, %d distintas", len(casos), mal)
	if mal > 0 {
		t.Fail()
	}
}

// Sondeo (2274 frases de model/sondeo) y frases difíciles frente a ids de transformers.
func TestIgualdadTransformers(t *testing.T) {
	casos := leer(t, "testdata/ids_e5.jsonl")
	if len(casos) < 2274 {
		t.Fatalf("solo %d frases", len(casos))
	}
	comparar(t, abrir(t), casos)
}

// Fuzz opcional contra un fichero de `referencia.py <dir> <salida> --fuzz N` (CHISPA_TOK_FUZZ).
func TestFuzzContraPython(t *testing.T) {
	ruta := os.Getenv("CHISPA_TOK_FUZZ")
	if ruta == "" {
		t.Skip("define CHISPA_TOK_FUZZ")
	}
	comparar(t, abrir(t), leer(t, ruta))
}

func TestForma(t *testing.T) {
	tk := abrir(t)
	for _, s := range []string{"", "hola", strings.Repeat("palabra ", 900)} {
		ids := tk.Tokenizar(s)
		if ids[0] != 0 || ids[len(ids)-1] != 2 || len(ids) > MaxTok {
			t.Errorf("%.20q: forma %v", s, ids)
		}
	}
	if got := len(tk.Tokenizar(strings.Repeat("palabra ", 900))); got != MaxTok {
		t.Errorf("truncado: %d", got)
	}
}

func FuzzTokenizar(f *testing.F) {
	tk := abrir(f)
	for _, s := range []string{"", "hola", "😀 é", "a▁b", "<s>x</s>", "\x00\xff", "a  b\tc"} {
		f.Add(s)
	}
	f.Fuzz(func(t *testing.T, s string) {
		ids := tk.Tokenizar(s)
		if len(ids) < 2 || len(ids) > MaxTok || ids[0] != 0 || ids[len(ids)-1] != 2 {
			t.Fatalf("forma %v", ids)
		}
		for _, id := range ids {
			if id < 0 || id > 250001 {
				t.Fatalf("id %d fuera de rango", id)
			}
		}
		if !slices.Equal(ids, tk.Tokenizar(s)) {
			t.Fatal("no determinista")
		}
		_ = utf8.ValidString(s)
	})
}
