package chispamovil

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
)

// Valores de demo/wasm (README y nativo/): la huella de embeddings de las 50 frases del sondeo con el L1 recortado
// de potion-es.chispa-l1, y el sha256 de las 50 respuestas de ejemplo_pregunta.json unidas con «\n».
const (
	huellaDemoWasm     = "4ce4952c206b9b0fd561825894cec879905443f9f0f36d29fe2006dbe4f8166c"
	respuestasDemoWasm = "8ca33fe9bd2dbd307cd500d80fe08cf0ba6e5fb91a3e67b65748b911448718fd"
)

func modeloL1(t *testing.T) []byte {
	t.Helper()
	for _, r := range []string{os.Getenv("CHISPA_L1_RECORTADO"), "../../../demo/wasm/potion-es.chispa-l1"} {
		if r == "" {
			continue
		}
		if b, err := os.ReadFile(r); err == nil {
			return b
		}
	}
	t.Skip("sin L1 recortado: CHISPA_L1_RECORTADO=… o demo/wasm/potion-es.chispa-l1 (ver demo/wasm/README.md)")
	return nil
}

func frasesSondeo(t *testing.T, fichero string, n int) []string {
	t.Helper()
	f, err := os.Open(filepath.Join("../../../model/sondeo", fichero))
	if err != nil {
		t.Skip("sin model/sondeo: ", err)
	}
	defer f.Close()
	var todas []string
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<24)
	for sc.Scan() {
		var l struct {
			Texto string `json:"texto"`
		}
		if err := json.Unmarshal(sc.Bytes(), &l); err != nil {
			t.Fatal(err)
		}
		todas = append(todas, l.Texto)
	}
	out := make([]string, n)
	for i := range out { // la misma selección que prueba_node.js: paso(x, n)
		out[i] = todas[i*len(todas)/n]
	}
	return out
}

func TestMismaHuellaQueDemoWasm(t *testing.T) {
	l1b := modeloL1(t)
	fr := append(frasesSondeo(t, "whatsapp_comercio.jsonl", 25), frasesSondeo(t, "intencion.jsonl", 25)...)
	preg, err := os.ReadFile("../../../demo/wasm/ejemplo_pregunta.json")
	if err != nil {
		t.Skip(err)
	}
	c, err := Abrir(escribirV3(t, append(metaYCalib(t)[:1], chispa3.Seccion{Tipo: chispa3.L1, Datos: l1b})))
	if err != nil {
		t.Fatal(err)
	}
	defer c.Cerrar()
	js, _ := json.Marshal(fr)
	if h := c.Huella(string(js)); h != huellaDemoWasm {
		t.Fatalf("huella %s ≠ demo/wasm %s", h, huellaDemoWasm)
	}
	resp := make([]string, len(fr))
	for i, f := range fr {
		r := leer(t, c.Decidir(f, string(preg)))
		if !r.Ok || !r.Opina {
			t.Fatalf("frase %d: %+v", i, r)
		}
		resp[i] = r.Answer
	}
	s := sha256.Sum256([]byte(strings.Join(resp, "\n")))
	if h := hex.EncodeToString(s[:]); h != respuestasDemoWasm {
		t.Fatalf("respuestas %s ≠ demo/wasm %s", h, respuestasDemoWasm)
	}
}
