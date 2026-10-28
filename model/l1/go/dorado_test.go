package dorado_test

import (
	"bufio"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"sync"
	"testing"

	l1 "chispa/runtime/l1"
)

// Test dorado del L1 propio: el .chispa-l1 exportado (CHISPA_L1_PROPIO, por defecto el de 256 dimensiones en
// /tmp/l1propio) debe dar el hash del cuerpo y el hash de los 200 primeros embeddings que fija
// testdata/dorado-<dim>.json, generado por la referencia independiente `python -m model.l1.dorado`.
func abrir(t *testing.T) (*l1.Modelo, string) {
	t.Helper()
	ruta := os.Getenv("CHISPA_L1_PROPIO")
	if ruta == "" {
		ruta = "/tmp/l1propio/d256/propio-256.chispa-l1"
	}
	if _, err := os.Stat(ruta); err != nil {
		t.Skipf("falta %s (python -m model.l1.destilar): este test NO se ha ejecutado", ruta)
	}
	m, err := l1.Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { m.Cerrar() })
	return m, ruta
}

type dorado struct {
	Dim            int    `json:"dim"`
	HashCuerpo     string `json:"hash_cuerpo"`
	N              int    `json:"n"`
	HashEmbeddings string `json:"hash_embeddings"`
}

func leerDorado(t *testing.T, dim int) dorado {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("testdata", "dorado-"+itoa(dim)+".json"))
	if err != nil {
		t.Fatal(err)
	}
	var d dorado
	if err := json.Unmarshal(b, &d); err != nil {
		t.Fatal(err)
	}
	return d
}

func itoa(n int) string { b, _ := json.Marshal(n); return string(b) }

func frases(t *testing.T, n int) []string {
	t.Helper()
	f, err := os.Open("../../../runtime/l1/testdata/ids_sondeo.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(nil, 1<<24)
	var out []string
	for sc.Scan() && len(out) < n {
		var c struct{ Texto string }
		if err := json.Unmarshal(sc.Bytes(), &c); err != nil {
			t.Fatal(err)
		}
		out = append(out, c.Texto)
	}
	return out
}

func hashEmbeddings(m *l1.Modelo, textos []string) string {
	h := sha256.New()
	out := make([]float32, m.Dim())
	buf := make([]byte, 4)
	for _, s := range textos {
		m.Embed(s, out)
		for _, f := range out {
			binary.LittleEndian.PutUint32(buf, math.Float32bits(f))
			h.Write(buf)
		}
	}
	return hex.EncodeToString(h.Sum(nil))
}

func TestDoradoCuerpo(t *testing.T) {
	m, _ := abrir(t)
	d := leerDorado(t, m.Dim())
	h := m.Hash()
	if got := hex.EncodeToString(h[:]); got != d.HashCuerpo {
		t.Fatalf("hash del cuerpo %s, esperado %s", got, d.HashCuerpo)
	}
	if err := m.Verificar(); err != nil {
		t.Fatal(err)
	}
}

func TestDoradoEmbeddings(t *testing.T) {
	m, _ := abrir(t)
	d := leerDorado(t, m.Dim())
	if got := hashEmbeddings(m, frases(t, d.N)); got != d.HashEmbeddings {
		t.Fatalf("hash de %d embeddings %s, esperado %s (referencia Python)", d.N, got, d.HashEmbeddings)
	}
}

func TestDoradoConcurrente(t *testing.T) {
	m, _ := abrir(t)
	d := leerDorado(t, m.Dim())
	fs := frases(t, d.N)
	var wg sync.WaitGroup
	for g := 0; g < 4; g++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if got := hashEmbeddings(m, fs); got != d.HashEmbeddings {
				t.Errorf("hash concurrente %s, esperado %s", got, d.HashEmbeddings)
			}
		}()
	}
	wg.Wait()
}
