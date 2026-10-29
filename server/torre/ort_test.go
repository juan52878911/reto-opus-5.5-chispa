//go:build ort

package torre

import (
	"encoding/json"
	"math"
	"os"
	"sync"
	"testing"

	"chispa/format/chispa3"
)

// ONNX sintético (testdata/sintetico.py): h de Go con ORT = h de onnxruntime de Python, y un segundo ONNX convive en el
// mismo proceso (el de L2 lo abre decide.NuevaSesionORT con el mismo entorno, ver IniciarORT).
// CHISPA_ORT_LIB fija libonnxruntime.so si no está en el sistema.
func TestSinteticoORT(t *testing.T) {
	if p := os.Getenv("CHISPA_ORT_LIB"); p != "" {
		RutaORT = p
	}
	onnx, err := os.ReadFile("testdata/sintetico.onnx")
	if err != nil {
		t.Fatal(err)
	}
	var ref []struct {
		IDs []int64   `json:"ids"`
		H   []float32 `json:"h"`
	}
	b, err := os.ReadFile("testdata/sintetico_ref.json")
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(b, &ref); err != nil {
		t.Fatal(err)
	}
	ses, err := abrirSesion(onnx)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := abrirSesion(onnx); err != nil { // segundo modelo en el mismo proceso
		t.Fatal("segunda sesión:", err)
	}
	var wg sync.WaitGroup
	for _, r := range ref {
		wg.Add(1)
		go func() {
			defer wg.Done()
			mask := make([]int64, len(r.IDs))
			for i := range mask {
				mask[i] = 1
			}
			h, err := ses.Embeber(r.IDs, mask)
			if err != nil || len(h) != len(r.H) {
				t.Errorf("%v: %v (%d)", r.IDs, err, len(h))
				return
			}
			var d float64
			for i := range h {
				d = math.Max(d, math.Abs(float64(h[i]-r.H[i])))
			}
			if d > 1e-5 {
				t.Errorf("%v: |Δh| máx %g", r.IDs, d)
			}
		}()
	}
	wg.Wait()
}

func TestCodificadorSinteticoORT(t *testing.T) {
	onnx, _ := os.ReadFile("testdata/sintetico.onnx")
	c, err := Abrir(chispa3.Torre{Dim: 256, MaxLen: 128, Prefijo: "passage: ", ONNX: onnx}, &tokFalso{})
	if err != nil {
		t.Fatal(err)
	}
	h, err := c.Torre("passage: ¿p? · a · ")
	if err != nil || len(h) != 256 {
		t.Fatalf("%d %v", len(h), err)
	}
	var n float64
	for _, x := range h {
		n += float64(x) * float64(x)
	}
	if math.Abs(n-1) > 1e-4 {
		t.Fatalf("‖h‖² = %v", n)
	}
}
