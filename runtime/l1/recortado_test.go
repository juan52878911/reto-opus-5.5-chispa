package l1

import (
	"math"
	"os"
	"sort"
	"testing"
)

// TestRecortado compara el L1 recortado (exportar.py --vocab) con el completo en las frases del sondeo.
// CHISPA_L1_RECORTADO: ruta del recortado; sin ella el test se salta.
func TestRecortado(t *testing.T) {
	ruta := os.Getenv("CHISPA_L1_RECORTADO")
	if ruta == "" {
		t.Skip("define CHISPA_L1_RECORTADO (salida de exportar.py --vocab): este test NO se ha ejecutado")
	}
	completo := abrirModelo(t)
	rec, err := Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	defer rec.Cerrar()
	if err := rec.Verificar(); err != nil {
		t.Fatal(err)
	}
	if fi, _ := os.Stat(ruta); fi.Size() > 30<<20 {
		t.Errorf("el recortado pesa %d bytes (> 30 MB)", fi.Size())
	}
	a, b := make([]float32, completo.Dim()), make([]float32, rec.Dim())
	var cos []float64
	var cero int
	for _, c := range leerIDs(t, "testdata/ids_sondeo.jsonl") {
		oka, okb := completo.Embed(c.Texto, a), rec.Embed(c.Texto, b)
		if !oka {
			continue // sin vector en el completo: no hay coseno
		}
		if !okb {
			cero++
			cos = append(cos, 0)
			continue
		}
		var s float64
		for i := range a {
			s += float64(a[i]) * float64(b[i])
		}
		cos = append(cos, s)
	}
	sort.Float64s(cos)
	var media float64
	bajo := 0
	for _, c := range cos {
		media += c
		if c < 0.99 {
			bajo++
		}
	}
	media /= float64(len(cos))
	t.Logf("frases %d · coseno medio %.6f · mínimo %.6f · p1 %.6f · < 0,99: %d · vector cero en el recortado: %d · tamaño %d B",
		len(cos), media, cos[0], cos[len(cos)/100], bajo, cero, func() int64 { fi, _ := os.Stat(ruta); return fi.Size() }())
	if math.IsNaN(media) || media < 0.99 {
		t.Errorf("coseno medio %.4f < 0,99", media)
	}
}
