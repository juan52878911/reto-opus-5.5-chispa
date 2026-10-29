package decide

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"chispa/format/chispa3"
	"chispa/runtime/tok"
)

func leerTestdata(t *testing.T, nombre string) []byte {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("testdata", nombre))
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func tokE5Real(t *testing.T) *tok.Tokenizador {
	t.Helper()
	ruta := os.Getenv("CHISPA_TOK")
	if ruta == "" {
		ruta = "/tmp/e5.chispa-tok"
	}
	if _, err := os.Stat(ruta); err != nil && os.Getenv("CHISPA_TOK") == "" {
		t.Skipf("sin .chispa-tok (CHISPA_TOK): %v", err)
	}
	tk, err := tok.Abrir(ruta)
	if err != nil {
		t.Fatal(err)
	}
	return tk
}

// sesión que apunta cuántos ids recibe.
type sesionLongitud struct{ n *int }

func (s sesionLongitud) Ranuras(ids []int64) ([][]float32, error) {
	*s.n = len(ids)
	return [][]float32{{1, 0}}, nil
}

func ficheroL2(t *testing.T, onnx []byte, torrMaxLen int) *chispa3.Fichero {
	t.Helper()
	esq, err := chispa3.CodificarEsquemas(2, []chispa3.EntradaEsquema{ent("¿q?", []string{"a"}, 1, 1, 0), ent("¿q?", []string{"b"}, 1, 0, 1)})
	if err != nil {
		t.Fatal(err)
	}
	secs := []chispa3.Seccion{{Tipo: chispa3.L2, Datos: onnx}, {Tipo: chispa3.ESQUEMAS, Datos: esq}}
	if torrMaxLen > 0 {
		tr, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 2, MaxLen: torrMaxLen, Prefijo: "passage: ", ONNX: []byte("onnx-torre")})
		if err != nil {
			t.Fatal(err)
		}
		secs = append(secs, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tr})
	}
	return v3Tiny(t, calibTiny(), secs...)
}

// El truncado de la consulta sale del metadato chispa.consulta.max_len del ONNX de L2: con 256, un texto largo llega al ONNX
// con 256 ids (no 128); sin metadato, 128 como siempre.
func TestL2MaxLenConsultaDelONNX(t *testing.T) {
	tk := NuevoTokenizadorE5(tokE5Real(t))
	largo := strings.Repeat("palabra · ", 900)
	p := Pregunta{ID: "q", Texto: "¿q?", Kind: KindChoice, Estado: largo, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	for _, c := range []struct {
		nombre string
		onnx   string
		want   int
	}{{"sin metadato", "l2_sintetico.onnx", 128}, {"metadato 256", "l2_sintetico_ml256.onnx", 256}} {
		var n int
		mt, err := ArmarDesde(ficheroL2(t, leerTestdata(t, c.onnx), 0), NuevoL0(8), &Config{CacheEsquemas: 8}, false, tk, ConSesionS(sesionLongitud{&n}))
		if err != nil || len(mt.Avisos) != 0 {
			t.Fatalf("%s: %v %v", c.nombre, err, mt.Avisos)
		}
		if _, err := mt.L2.Decidir(context.Background(), p); err != nil {
			t.Fatalf("%s: %v", c.nombre, err)
		}
		if n != c.want {
			t.Errorf("%s: el ONNX recibió %d ids, quería %d", c.nombre, n, c.want)
		}
	}
}

// Un max_len por encima del tope duro (512) es un error claro al armar, no un truncado silencioso.
func TestL2MaxLenConsultaSobreElTope(t *testing.T) {
	onnx := append(leerTestdata(t, "l2_sintetico_ml256.onnx"), 0x72, 0x1e, 0x0a, 0x17) // un metadata_props más (len 2+23+2+3): clave y valor «513»; en protobuf la última gana
	onnx = append(onnx, "chispa.consulta.max_len"...)
	onnx = append(onnx, 0x12, 0x03, '5', '1', '3')
	_, err := ArmarDesde(ficheroL2(t, onnx, 0), NuevoL0(8), &Config{}, false, tokFalso{}, ConSesionS(sesionFalsa{[][]float32{{1, 0}}}))
	if err == nil || !strings.Contains(err.Error(), "513 fuera de rango (3..512)") || !strings.Contains(err.Error(), "chispa.consulta.max_len") {
		t.Fatalf("error %v", err)
	}
}

type tokEspia struct {
	tokFalso
	consulta, pasaje int
}

func (e *tokEspia) ConMaxLen(consulta, pasaje int) Tokenizador {
	e.consulta, e.pasaje = consulta, pasaje
	return e
}

// El pasaje sale de max_len de TORR y la consulta del metadato; sin ninguno, 128 y 128 (el tokenizador ni se toca).
func TestArmarDesdePasaMaxLenAlTokenizador(t *testing.T) {
	ses := ConSesionS(sesionFalsa{[][]float32{{1, 0}}})
	enc := ConCodificadorTorre(&codificadorPorTexto{clave: "x"})
	for _, c := range []struct {
		onnx          string
		torr          int
		consulta, pas int
	}{{"l2_sintetico.onnx", 0, 0, 0}, {"l2_sintetico.onnx", 128, 0, 0}, {"l2_sintetico.onnx", 300, 128, 300},
		{"l2_sintetico_ml256.onnx", 0, 256, 128}, {"l2_sintetico_ml256.onnx", 256, 256, 256}} {
		esp := &tokEspia{}
		if _, err := ArmarDesde(ficheroL2(t, leerTestdata(t, c.onnx), c.torr), NuevoL0(8), &Config{CacheEsquemas: 8}, false, esp, ses, enc); err != nil {
			t.Fatal(err)
		}
		if esp.consulta != c.consulta || esp.pasaje != c.pas {
			t.Errorf("%s torr=%d: consulta %d pasaje %d, quería %d y %d", c.onnx, c.torr, esp.consulta, esp.pasaje, c.consulta, c.pas)
		}
	}
	// Un tokenizador que no se puede ajustar avisa en vez de callar.
	mt, err := ArmarDesde(ficheroL2(t, leerTestdata(t, "l2_sintetico_ml256.onnx"), 0), NuevoL0(8), &Config{}, false, tokFalso{}, ses)
	if err != nil || len(mt.Avisos) != 1 || !strings.Contains(mt.Avisos[0], "no admite truncado ajustable") {
		t.Fatalf("%v %v", err, mt.Avisos)
	}
}

// TokenizadorE5: pasaje y consulta truncan cada uno a lo suyo; sin ConMaxLen, 128; el tope duro de runtime/tok y el de TORR coinciden.
func TestTokenizadorE5ConMaxLen(t *testing.T) {
	base := NuevoTokenizadorE5(tokE5Real(t))
	largo := strings.Repeat("palabra · ", 900)
	if len(base.IDs(largo)) != 128 || len(base.IDsPasaje(largo)) != 128 {
		t.Fatalf("defecto: %d y %d", len(base.IDs(largo)), len(base.IDsPasaje(largo)))
	}
	aj := base.ConMaxLen(256, 300).(TokenizadorPasaje)
	if n := len(aj.(Tokenizador).IDs(largo)); n != 256 {
		t.Errorf("consulta: %d ids", n)
	}
	if n := len(aj.IDsPasaje(largo)); n != 300 {
		t.Errorf("pasaje: %d ids", n)
	}
	if chispa3.MaxLenTope != tok.TopeMaxLen || chispa3.MaxLenDefecto != tok.MaxTok {
		t.Errorf("topes distintos: chispa3 %d/%d, tok %d/%d", chispa3.MaxLenDefecto, chispa3.MaxLenTope, tok.MaxTok, tok.TopeMaxLen)
	}
}
