package l1

import (
	"bufio"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"math"
	"os"
	"slices"
	"testing"
)

// rutaModelo: el .chispa-l1 pesa cientos de MB y no va a git; se genera con exportar.py.
func abrirModelo(t testing.TB) *Modelo {
	t.Helper()
	ruta := os.Getenv("CHISPA_L1")
	if ruta == "" {
		ruta = "/tmp/potion.chispa-l1"
	}
	if _, err := os.Stat(ruta); err != nil {
		t.Skipf("falta el modelo %s (genéralo con exportar.py o define CHISPA_L1): este test NO se ha ejecutado", ruta)
	}
	m, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { m.Cerrar() })
	return m
}

type casoIDs struct {
	Texto string  `json:"texto"`
	IDs   []int32 `json:"ids"`
}

func leerIDs(t testing.TB, ruta string) []casoIDs {
	t.Helper()
	f, err := os.Open(ruta)
	if err != nil {
		t.Skipf("falta %s", ruta)
	}
	defer f.Close()
	var out []casoIDs
	sc := bufio.NewScanner(f)
	sc.Buffer(nil, 1<<24)
	for sc.Scan() {
		var c casoIDs
		if err := json.Unmarshal(sc.Bytes(), &c); err != nil {
			t.Fatal(err)
		}
		out = append(out, c)
	}
	return out
}

func compararIDs(t *testing.T, m *Modelo, casos []casoIDs) {
	mal := 0
	for _, c := range casos {
		if got := m.Tokenizar(c.Texto); !slices.Equal(got, c.IDs) {
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

// Los ids de ≥2000 frases de model/sondeo deben coincidir con los de tokenizers.
func TestTokenizadorSondeo(t *testing.T) {
	casos := leerIDs(t, "testdata/ids_sondeo.jsonl")
	if len(casos) < 2000 {
		t.Fatalf("solo %d frases", len(casos))
	}
	compararIDs(t, abrirModelo(t), casos)
}

// Fuzz opcional contra un fichero generado con `referencia.py ids ... --fuzz N` (CHISPA_L1_FUZZ).
func TestTokenizadorFuzz(t *testing.T) {
	ruta := os.Getenv("CHISPA_L1_FUZZ")
	if ruta == "" {
		t.Skip("define CHISPA_L1_FUZZ para correr el fuzz contra Python")
	}
	compararIDs(t, abrirModelo(t), leerIDs(t, ruta))
}

// hash200 es el sha256 de los embeddings float32 (little endian) de las 200 primeras frases de
// testdata/ids_sondeo.jsonl, calculados con referencia.py (Python, enteros + float64) sobre el .chispa-l1
// exportado con exportar.py. Debe salir igual en amd64 y arm64.
const hash200 = "f70784322c226eb1ae28718134a16e4b19573be88743ed1a4e7ad11542ed7ac8"

// hashCuerpo es el sha256 del cuerpo del .chispa-l1 de potion-multilingual-128M (versión 1 del formato).
const hashCuerpo = "01fe1e57dc1bb1917757723e35264b146c25c4d81a3950a8ec7bb0f6a4ba8808"

func TestHashCuerpo(t *testing.T) {
	m := abrirModelo(t)
	h := m.Hash()
	if got := hex.EncodeToString(h[:]); got != hashCuerpo {
		t.Fatalf("hash del cuerpo %s, esperado %s", got, hashCuerpo)
	}
	if err := m.Verificar(); err != nil {
		t.Fatal(err)
	}
}

func TestEmbeddingDorado(t *testing.T) {
	m := abrirModelo(t)
	casos := leerIDs(t, "testdata/ids_sondeo.jsonl")[:200]
	h := sha256.New()
	out := make([]float32, m.Dim())
	buf := make([]byte, 4)
	for _, c := range casos {
		m.Embed(c.Texto, out)
		for _, f := range out {
			binary.LittleEndian.PutUint32(buf, math.Float32bits(f))
			h.Write(buf)
		}
	}
	if got := hex.EncodeToString(h.Sum(nil)); got != hash200 {
		t.Fatalf("hash de 200 embeddings %s, esperado %s", got, hash200)
	}
}

// Con CHISPA_L1_REF (salida de `referencia.py emb`) compara bit a bit los embeddings de todas las frases.
func TestEmbeddingIdenticoAPython(t *testing.T) {
	ruta := os.Getenv("CHISPA_L1_REF")
	if ruta == "" {
		t.Skip("define CHISPA_L1_REF para comparar con la referencia int8 de Python")
	}
	m := abrirModelo(t)
	f, err := os.Open(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(nil, 1<<24)
	out := make([]float32, m.Dim())
	n, mal := 0, 0
	for sc.Scan() {
		var c struct{ Texto, Emb string }
		if err := json.Unmarshal(sc.Bytes(), &c); err != nil {
			t.Fatal(err)
		}
		want, _ := hex.DecodeString(c.Emb)
		m.Embed(c.Texto, out)
		for j, v := range out {
			if math.Float32bits(v) != binary.LittleEndian.Uint32(want[4*j:]) {
				mal++
				t.Errorf("texto %q dim %d: go %v", c.Texto, j, v)
				break
			}
		}
		n++
	}
	t.Logf("%d frases, %d distintas de la referencia", n, mal)
}

func TestEmbeddingNormalizado(t *testing.T) {
	m := abrirModelo(t)
	out := make([]float32, m.Dim())
	if !m.Embed("hola, ¿qué tal?", out) {
		t.Fatal("sin tokens")
	}
	var s float64
	for _, v := range out {
		s += float64(v) * float64(v)
	}
	if math.Abs(s-1) > 1e-6 {
		t.Fatalf("norma² = %v", s)
	}
	if m.Embed("", out) || out[0] != 0 {
		t.Fatal("texto vacío debe dar ceros")
	}
}

func TestConcurrente(t *testing.T) {
	m := abrirModelo(t)
	casos := leerIDs(t, "testdata/ids_sondeo.jsonl")[:100]
	ref := make([][]float32, len(casos))
	for i, c := range casos {
		ref[i] = make([]float32, m.Dim())
		m.Embed(c.Texto, ref[i])
	}
	done := make(chan bool)
	for g := 0; g < 4; g++ {
		go func() {
			out := make([]float32, m.Dim())
			ok := true
			for i, c := range casos {
				m.Embed(c.Texto, out)
				ok = ok && slices.Equal(out, ref[i])
			}
			done <- ok
		}()
	}
	for g := 0; g < 4; g++ {
		if !<-done {
			t.Error("resultado distinto entre goroutines")
		}
	}
}
