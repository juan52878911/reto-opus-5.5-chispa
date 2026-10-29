package tok

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
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
		ruta = rutaTokPorDefecto()
	}
	tk, err := Abrir(ruta)
	// Solo se salta si no hay fichero y nadie pidió uno: un .chispa-tok que existe y no abre es un fallo, no un salto.
	if _, e := os.Stat(ruta); e != nil && os.Getenv("CHISPA_TOK") == "" {
		t.Skipf("sin .chispa-tok (exportar.py; CHISPA_TOK): %v", e)
	}
	if err != nil {
		t.Fatalf("%s: %v", ruta, err)
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

// Modo «passage: » (torre de esquemas de L2) frente a ids de transformers, incluidos textos con « · » (U+00B7).
func TestIgualdadTransformersPasaje(t *testing.T) {
	tk := abrir(t)
	casos := leer(t, "testdata/ids_e5_passage.jsonl")
	if len(casos) < 2274 {
		t.Fatalf("solo %d frases", len(casos))
	}
	mal := 0
	for _, c := range casos {
		if got := tk.TokenizarPasaje(c.Texto); !slices.Equal(got, c.IDs) {
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

// El prefijo de pasaje cambia los ids respecto al de consulta, y TokenizarCon("passage: ", x) = TokenizarPasaje(x).
func TestPasajeDistintoDeConsulta(t *testing.T) {
	tk := abrir(t)
	q, p := tk.Tokenizar("hola · mundo"), tk.TokenizarPasaje("hola · mundo")
	if slices.Equal(q, p) || !slices.Equal(p, tk.TokenizarCon(PrefijoPasaje, "hola · mundo")) {
		t.Fatalf("query %v passage %v", q, p)
	}
	if got := len(tk.TokenizarPasaje(strings.Repeat("palabra · ", 300))); got != MaxTok {
		t.Fatalf("truncado a %d", got)
	}
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

// El truncado sale del llamador (metadatos del modelo), no de una constante: con 256 un texto largo se trunca a 256 y no a 128,
// y los 256 ids empiezan por <s> y acaban en </s>; el prefijo corta igual para consulta y pasaje.
func TestTokenizarMaxLen(t *testing.T) {
	tk := abrir(t)
	largo := strings.Repeat("palabra · ", 900)
	for _, n := range []int{64, 128, 256, TopeMaxLen} {
		for _, pref := range []string{Prefijo, PrefijoPasaje} {
			ids := tk.TokenizarMax(pref, largo, n)
			if len(ids) != n || ids[0] != 0 || ids[n-1] != 2 {
				t.Errorf("max_len %d (%q): %d ids, extremos %d/%d", n, pref, len(ids), ids[0], ids[len(ids)-1])
			}
			// Es un prefijo del truncado más largo: no cambia nada salvo dónde corta.
			if n > 3 && !slices.Equal(ids[:n-1], tk.TokenizarMax(pref, largo, TopeMaxLen)[:n-1]) {
				t.Errorf("max_len %d (%q): los ids no son prefijo de los de 512", n, pref)
			}
		}
	}
	// Un texto corto no se alarga ni se corta y da lo mismo con cualquier max_len ≥ su longitud.
	corto := tk.Tokenizar("hola mundo")
	if !slices.Equal(corto, tk.TokenizarMax(Prefijo, "hola mundo", 256)) {
		t.Errorf("texto corto distinto con max_len 256")
	}
	// El defecto sigue siendo MaxTok.
	if len(tk.Tokenizar(largo)) != MaxTok || len(tk.TokenizarPasaje(largo)) != MaxTok || len(tk.TokenizarCon(Prefijo, largo)) != MaxTok {
		t.Errorf("el defecto ya no es %d", MaxTok)
	}
	// Fuera de rango se acota (los llamadores validan antes con ComprobarMaxLen).
	if got := len(tk.TokenizarMax(Prefijo, largo, 10_000)); got != TopeMaxLen {
		t.Errorf("max_len 10000: %d ids, quería el tope %d", got, TopeMaxLen)
	}
	if got := len(tk.TokenizarMax(Prefijo, largo, 0)); got != 3 {
		t.Errorf("max_len 0: %d ids, quería 3", got)
	}
}

func TestComprobarMaxLen(t *testing.T) {
	for _, n := range []int{3, 128, 256, TopeMaxLen} {
		if err := ComprobarMaxLen(n); err != nil {
			t.Errorf("%d: %v", n, err)
		}
	}
	for _, n := range []int{-1, 0, 2, TopeMaxLen + 1, 8192} {
		if err := ComprobarMaxLen(n); err == nil || !strings.Contains(err.Error(), "fuera de rango") {
			t.Errorf("%d: %v", n, err)
		}
	}
}

// rutaTokPorDefecto: sin CHISPA_TOK, el .chispa-tok del usuario ($TMPDIR o su caché), nunca un /tmp compartido entre trabajos.
func rutaTokPorDefecto() string {
	if d := os.Getenv("TMPDIR"); d != "" {
		return filepath.Join(d, "e5.chispa-tok")
	}
	if d, err := os.UserCacheDir(); err == nil {
		return filepath.Join(d, "chispa", "e5.chispa-tok")
	}
	return "e5.chispa-tok"
}
