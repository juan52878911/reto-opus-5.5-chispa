package chispa3

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ModelProto mínimo a mano: ir_version (varint, campo 1), un campo 7 (grafo) de relleno y metadata_props (campo 14).
func onnxConMeta(props ...[2]string) []byte {
	b := []byte{0x08, 0x08, 0x3a, 0x03, 'g', 'g', 'g'} // ir_version=8, graph="ggg"
	for _, p := range props {
		e := append([]byte{0x0a, byte(len(p[0]))}, p[0]...)
		e = append(append(e, 0x12, byte(len(p[1]))), p[1]...)
		b = append(append(b, 0x72, byte(len(e))), e...) // campo 14, tipo 2
	}
	return b
}

func TestMaxLenConsulta(t *testing.T) {
	for _, c := range []struct {
		nombre string
		onnx   []byte
		want   int
		err    string
	}{
		{"sin metadatos", onnxConMeta(), 128, ""},
		{"otra clave", onnxConMeta([2]string{"chispa.torre.max_len", "64"}), 128, ""},
		{"256", onnxConMeta([2]string{"chispa.consulta.max_len", "256"}), 256, ""},
		{"tope", onnxConMeta([2]string{"chispa.consulta.max_len", "512"}), 512, ""},
		{"gana la última", onnxConMeta([2]string{"chispa.consulta.max_len", "64"}, [2]string{"chispa.consulta.max_len", "192"}), 192, ""},
		{"513", onnxConMeta([2]string{"chispa.consulta.max_len", "513"}), 0, "513 fuera de rango (3..512)"},
		{"cero", onnxConMeta([2]string{"chispa.consulta.max_len", "0"}), 0, "fuera de rango"},
		{"no entero", onnxConMeta([2]string{"chispa.consulta.max_len", "mucho"}), 0, "no es un entero"},
		{"no es un ONNX: ORT dará su error", []byte("onnx"), 128, ""},
		{"vacío", nil, 128, ""},
	} {
		got, err := MaxLenConsulta(c.onnx)
		if c.err == "" && (err != nil || got != c.want) {
			t.Errorf("%s: %d, %v (quería %d)", c.nombre, got, err, c.want)
		}
		if c.err != "" && (err == nil || !strings.Contains(err.Error(), c.err) || !strings.Contains(err.Error(), ClaveMaxLenConsulta)) {
			t.Errorf("%s: error %v, quería %q", c.nombre, err, c.err)
		}
	}
}

// El ONNX sintético de server/decide/testdata (l2_sintetico.py --max-len 256 --vocab 1000, escrito con la librería onnx) lleva la
// clave; el de siempre, no.
func TestMaxLenConsultaONNXSintetico(t *testing.T) {
	dir := filepath.Join("..", "..", "server", "decide", "testdata")
	b, err := os.ReadFile(filepath.Join(dir, "l2_sintetico_ml256.onnx"))
	if err != nil {
		t.Fatal(err)
	}
	if n, err := MaxLenConsulta(b); err != nil || n != 256 {
		t.Fatalf("ml256: %d, %v", n, err)
	}
	b, err = os.ReadFile(filepath.Join(dir, "l2_sintetico.onnx"))
	if err != nil {
		t.Fatal(err)
	}
	if n, err := MaxLenConsulta(b); err != nil || n != MaxLenDefecto {
		t.Fatalf("sin metadato: %d, %v", n, err)
	}
}

func TestTorrMaxLenTope(t *testing.T) {
	t0 := Torre{Dim: 4, MaxLen: 256, Prefijo: "passage: ", ONNX: []byte("x")}
	b, err := CodificarTORR(t0)
	if err != nil {
		t.Fatal(err)
	}
	if g, err := DecodificarTORR(b); err != nil || g.MaxLen != 256 {
		t.Fatalf("256: %+v %v", g, err)
	}
	t0.MaxLen = MaxLenTope + 1
	if _, err := CodificarTORR(t0); err == nil || !strings.Contains(err.Error(), "tope 512") {
		t.Fatalf("513: %v", err)
	}
	b, _ = CodificarTORR(Torre{Dim: 4, MaxLen: MaxLenTope, Prefijo: "passage: ", ONNX: []byte("x")})
	b[8], b[9] = 0x01, 0x02 // max_len = 513
	if _, err := DecodificarTORR(b); err == nil || !strings.Contains(err.Error(), "tope 512") {
		t.Fatalf("decodificar 513: %v", err)
	}
}
