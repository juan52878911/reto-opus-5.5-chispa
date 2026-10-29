package chispamovil

import (
	"bytes"
	"encoding/binary"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"chispa/runtime/tok"
)

func onnxSintetico(t *testing.T, nombre string) []byte {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("..", "..", "..", "server", "decide", "testdata", nombre))
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func abrirCon(t *testing.T, secs ...chispa3.Seccion) (*Chispa, error) {
	t.Helper()
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, append(metaYCalib(t), secs...)); err != nil {
		t.Fatal(err)
	}
	ruta := filepath.Join(t.TempDir(), "m.chispa")
	if err := os.WriteFile(ruta, buf.Bytes(), 0o600); err != nil {
		t.Fatal(err)
	}
	c, err := Abrir(ruta)
	if err == nil {
		t.Cleanup(func() { c.Cerrar() })
	}
	return c, err
}

func nIds(b []byte) int { return len(b) / 4 }

func idsU32(b []byte) []uint32 {
	o := make([]uint32, len(b)/4)
	for i := range o {
		o[i] = binary.LittleEndian.Uint32(b[4*i:])
	}
	return o
}

// El truncado de la consulta sale del metadato chispa.consulta.max_len del ONNX de L2 y el del pasaje, de max_len de TORR:
// con 256 un texto largo da 256 ids (no 128), con <s> al principio y </s> al final; sin metadatos, 128 como siempre.
func TestMaxLenDeMetadatos(t *testing.T) {
	ruta := os.Getenv("CHISPA_TOK")
	if ruta == "" {
		ruta = "/tmp/e5.chispa-tok"
	}
	if _, err := os.Stat(ruta); err != nil && os.Getenv("CHISPA_TOK") == "" {
		t.Skipf("sin .chispa-tok: %v", err)
	}
	largo := strings.Repeat("palabra · ", 900)
	torr := func(ml int) chispa3.Seccion {
		b, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 2, MaxLen: ml, Prefijo: "passage: ", ONNX: []byte("onnx-torre")})
		if err != nil {
			t.Fatal(err)
		}
		return chispa3.Seccion{Tipo: chispa3.TORR, Datos: b}
	}
	for _, c := range []struct {
		nombre   string
		onnx     string
		torrML   int
		consulta int
		pasaje   int
	}{{"sin metadatos ni TORR", "l2_sintetico.onnx", 0, 128, 128}, {"TORR 128", "l2_sintetico.onnx", 128, 128, 128},
		{"metadato 256 y TORR 256", "l2_sintetico_ml256.onnx", 256, 256, 256}, {"consulta 256, pasaje 300", "l2_sintetico_ml256.onnx", 300, 256, 300},
		{"TORR 512", "l2_sintetico.onnx", 512, 128, 512}} {
		secs := []chispa3.Seccion{{Tipo: chispa3.L2, Datos: onnxSintetico(t, c.onnx)}}
		if c.torrML > 0 {
			secs = append(secs, torr(c.torrML))
		}
		m, err := abrirCon(t, secs...)
		if err != nil {
			t.Fatalf("%s: %v", c.nombre, err)
		}
		if err := m.CargarTokenizadorE5(ruta); err != nil {
			t.Fatal(err)
		}
		if m.MaxLenConsulta() != c.consulta || m.MaxLenPasaje() != c.pasaje {
			t.Errorf("%s: MaxLen consulta %d pasaje %d", c.nombre, m.MaxLenConsulta(), m.MaxLenPasaje())
		}
		q := idsU32(m.TokenizarE5(largo))
		if len(q) != c.consulta || q[0] != 0 || q[len(q)-1] != 2 {
			t.Errorf("%s: consulta de %d ids (quería %d), extremos %d/%d", c.nombre, len(q), c.consulta, q[0], q[len(q)-1])
		}
		if c.torrML > 0 {
			p := idsU32(m.IdsPasaje(largo))
			if len(p) != c.pasaje || p[0] != 0 || p[len(p)-1] != 2 {
				t.Errorf("%s: pasaje de %d ids (quería %d)", c.nombre, len(p), c.pasaje)
			}
		}
	}
	// Un texto corto no cambia con max_len 256.
	m256, _ := abrirCon(t, chispa3.Seccion{Tipo: chispa3.L2, Datos: onnxSintetico(t, "l2_sintetico_ml256.onnx")})
	m256.CargarTokenizadorE5(ruta)
	tk, _ := tok.Abrir(ruta)
	if nIds(m256.TokenizarE5("hola mundo")) != len(tk.Tokenizar("hola mundo")) {
		t.Error("texto corto distinto")
	}
}

// Un metadato por encima del tope duro (512) hace fallar Abrir con un error claro.
func TestMaxLenSobreElTopeFallaAlAbrir(t *testing.T) {
	onnx := append(onnxSintetico(t, "l2_sintetico_ml256.onnx"), 0x72, 0x1e, 0x0a, 0x17) // metadata_props: clave, valor «513»; la última gana
	onnx = append(onnx, "chispa.consulta.max_len"...)
	onnx = append(onnx, 0x12, 0x03, '5', '1', '3')
	_, err := abrirCon(t, chispa3.Seccion{Tipo: chispa3.L2, Datos: onnx})
	if err == nil || !strings.Contains(err.Error(), "513 fuera de rango (3..512)") {
		t.Fatalf("error %v", err)
	}
}
