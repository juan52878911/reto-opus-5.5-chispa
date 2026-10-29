//go:build ort

package decide

import (
	"encoding/json"
	"os"
	"testing"

	"chispa/format/chispa3"
	"github.com/juan52878911/chispa/server/torre"
)

func TestMain(m *testing.M) {
	if p := os.Getenv("CHISPA_ORT_LIB"); p != "" {
		RutaORT = p
		torre.RutaORT = p
	}
	os.Exit(m.Run())
}

// tokORT da ids fijos en consulta y ids derivados del texto en pasaje (la torre sintética solo promedia embeddings).
type tokORT struct{}

func (tokORT) IDs(string) []int64 { return []int64{0, 5, 40000, 2} }
func (tokORT) IDsPasaje(t string) []int64 {
	ids := []int64{0}
	for _, r := range t {
		ids = append(ids, int64(r)%250000+3)
	}
	return append(ids, 2)
}

// L2 real (ONNX sintético de consulta) + torre real (sintetico.onnx) en el mismo proceso, con un solo entorno ORT:
// esquema nuevo por /v1/decide, torres al vuelo, segunda petición desde la caché.
func TestL2TorreORTEsquemaNuevo(t *testing.T) {
	l2onnx, err := os.ReadFile("testdata/l2_sintetico.onnx")
	if err != nil {
		t.Fatal(err)
	}
	torreonnx, err := os.ReadFile("../torre/testdata/sintetico.onnx")
	if err != nil {
		t.Fatal(err)
	}
	vec := make([]int8, 256)
	vec[0] = 1
	esq, err := chispa3.CodificarEsquemas(256, []chispa3.EntradaEsquema{ent("solo en ESQUEMAS", []string{"a"}, 1, vec...)})
	if err != nil {
		t.Fatal(err)
	}
	tr, err := chispa3.CodificarTORR(chispa3.Torre{Dim: 256, MaxLen: 128, Prefijo: "passage: ", ONNX: torreonnx})
	if err != nil {
		t.Fatal(err)
	}
	calib := calibTiny()
	calib.Tipos["score3"] = chispa3.ParamsTipo{T: 1, A: 1, B: 0, Theta: 0.5}
	calib.Tipos["score3#1"] = chispa3.ParamsTipo{T: 1, A: 1}
	f := v3Tiny(t, calib, chispa3.Seccion{Tipo: chispa3.L2, Datos: l2onnx},
		chispa3.Seccion{Tipo: chispa3.ESQUEMAS, Datos: esq}, chispa3.Seccion{Tipo: chispa3.TORR, Datos: tr})
	cfg := Config{CacheEsquemas: 64}
	mt, err := ArmarDesde(f, NuevoL0(8), &cfg, false, tokORT{})
	if err != nil || len(mt.Avisos) != 0 {
		t.Fatalf("%v %v", err, mt.Avisos)
	}
	l2, ok := mt.L2.(*L2)
	if !ok || l2.torres == nil {
		t.Fatalf("L2 %T sin torres", mt.L2)
	}
	if _, ok := l2.ses.(*sesionORT); !ok {
		t.Fatalf("sesión %T, esperaba ORT real", l2.ses)
	}
	casc, err := NuevaCascada([]Capa{{"L2", 0}}, []Decisor{mt.L2}, NuevasMetricas())
	if err != nil {
		t.Fatal(err)
	}
	h := NuevoServidor(casc, NuevasMetricas(), 0).Handler()
	cuerpo := `{"state":"me cobraron dos veces","questions":[{"id":"q1","kind":"choice","question":"¿De qué trata?",
	  "options":[{"id":"ventas","description":"compras"},{"id":"quejas","description":"reclamos"}]},
	 {"id":"q2","kind":"noul","question":"¿Es una queja?","options":[{"id":"false"},{"id":"true","description":"quejas"}]},
	 {"id":"q3","kind":"score","question":"¿Qué tan molesto?","options":[{"id":"1"},{"id":"2"},{"id":"3"}]}]}`
	run := func() string {
		rr := post(h, cuerpo)
		if rr.Code != 200 {
			t.Fatalf("%d %s", rr.Code, rr.Body)
		}
		var out struct {
			Results []struct {
				ID, Answer, Layer string
			} `json:"results"`
		}
		if err := json.Unmarshal(rr.Body.Bytes(), &out); err != nil || len(out.Results) != 3 {
			t.Fatalf("%v %s", err, rr.Body)
		}
		s := ""
		for _, r := range out.Results {
			if r.Layer != "L2" || r.Answer == "" {
				t.Fatalf("%+v", r)
			}
			s += r.ID + "=" + r.Answer + ";"
		}
		return s
	}
	a := run()
	if l2.Misses.Load() != 3 {
		t.Fatalf("fallos %d, aciertos %d", l2.Misses.Load(), l2.Hits.Load())
	}
	if b := run(); a != b || l2.Hits.Load() != 3 {
		t.Fatalf("segunda petición %q ≠ %q, aciertos %d", b, a, l2.Hits.Load())
	}
}
