package decide

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"math"
	"math/rand"
	"os"
	"sort"
	"testing"

	"chispa/format/chispa3"
)

type fixtureL0TF struct {
	Etiquetas []string `json:"etiquetas"`
	Frases    []struct {
		Texto string    `json:"texto"`
		Probs []float64 `json:"probs"`
	} `json:"frases"`
}

func cargarFixtureL0TF(t testing.TB, modelo string) (*chispa3.L0TFModelo, fixtureL0TF) {
	t.Helper()
	b, err := os.ReadFile("testdata/l0tf/" + modelo)
	if err != nil {
		t.Fatal(err)
	}
	m, err := chispa3.DecodificarL0TF(b)
	if err != nil {
		t.Fatal(err)
	}
	var fx fixtureL0TF
	j, err := os.ReadFile("testdata/l0tf/frases.json")
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(j, &fx); err != nil {
		t.Fatal(err)
	}
	return m, fx
}

// maxDelta es el mayor |Δp| entre el L0TF de Go y el predict_proba de sklearn del fixture.
func maxDelta(t testing.TB, modelo string) float64 {
	m, fx := cargarFixtureL0TF(t, modelo)
	if fmt.Sprint(m.Etiquetas) != fmt.Sprint(fx.Etiquetas) {
		t.Fatalf("etiquetas %v ≠ %v", m.Etiquetas, fx.Etiquetas)
	}
	var mx float64
	for _, f := range fx.Frases {
		p := m.Probs(f.Texto)
		for i := range p {
			mx = math.Max(mx, math.Abs(p[i]-f.Probs[i]))
		}
	}
	return mx
}

func TestL0TFParidadConSklearn(t *testing.T) {
	_, fx := cargarFixtureL0TF(t, "modelo.l0tf")
	if len(fx.Frases) < 200 {
		t.Fatalf("el fixture trae %d frases", len(fx.Frases))
	}
	d := maxDelta(t, "modelo.l0tf")
	t.Logf("f32: %d frases, |Δp| máx = %.3g", len(fx.Frases), d)
	if d > 1e-5 {
		t.Fatalf("|Δp| = %g > 1e-5", d)
	}
	d16 := maxDelta(t, "modelo_f16.l0tf")
	t.Logf("f16: |Δp| máx = %.3g", d16)
	if d16 > 5e-2 {
		t.Fatalf("f16: |Δp| = %g", d16)
	}
}

// Con L0TF_REAL=directorio (modelo.l0tf y frases.json de un entrenamiento real, p. ej. massive o clinc150) mide la paridad
// con sklearn sobre esos datos. No va en el repositorio: los datos son grandes.
func TestL0TFParidadReal(t *testing.T) {
	dir := os.Getenv("L0TF_REAL")
	if dir == "" {
		t.Skip("sin L0TF_REAL")
	}
	b, err := os.ReadFile(dir + "/modelo.l0tf")
	if err != nil {
		t.Fatal(err)
	}
	m, err := chispa3.DecodificarL0TF(b)
	if err != nil {
		t.Fatal(err)
	}
	j, _ := os.ReadFile(dir + "/frases.json")
	var fx fixtureL0TF
	if err := json.Unmarshal(j, &fx); err != nil {
		t.Fatal(err)
	}
	var mx float64
	for _, f := range fx.Frases {
		for i, x := range m.Probs(f.Texto) {
			mx = math.Max(mx, math.Abs(x-f.Probs[i]))
		}
	}
	t.Logf("%d n-gramas × %d clases, %d frases: |Δp| máx = %.3g", m.NumNGramas(), m.NumClases(), len(fx.Frases), mx)
	if mx > 1e-5 {
		t.Fatalf("|Δp| = %g", mx)
	}
}

func TestL0TFComoCapaL0(t *testing.T) {
	m, fx := cargarFixtureL0TF(t, "modelo.l0tf")
	l0 := NuevoL0(4)
	if err := l0.AnadirTF("tf", m); err != nil {
		t.Fatal(err)
	}
	if err := l0.AnadirTF("otra", m); err == nil {
		t.Fatal("dos modelos con las mismas etiquetas")
	}
	ops := opcionesDe(fx.Etiquetas)
	// En otro orden de opciones también casa (firma por conjunto).
	sort.Slice(ops, func(i, j int) bool { return ops[i].ID > ops[j].ID })
	f := fx.Frases[1]
	r, err := l0.Decidir(context.Background(), Pregunta{Kind: KindChoice, Texto: "q", Opciones: ops, Estado: f.Texto})
	if err != nil {
		t.Fatal(err)
	}
	top := 0
	for i, x := range f.Probs {
		if x > f.Probs[top] {
			top = i
		}
	}
	if r.Answer != fx.Etiquetas[top] || math.Abs(r.Conf-f.Probs[top]) > 1e-5 || len(r.Probs) != len(ops) {
		t.Fatalf("respuesta %+v", r)
	}
	// Con otras opciones, no opina.
	r, _ = l0.Decidir(context.Background(), Pregunta{Kind: KindChoice, Opciones: []Opcion{{ID: "x"}, {ID: "y"}}, Estado: "hola"})
	if r.Conf != 0 {
		t.Fatal("sin modelo debía no opinar")
	}
}

// El .chispa con L0TF usa el tfidf; sin él, ArmarDesde sigue con la sección L0 (los tests de modelo ya lo cubren).
func TestArmarDesdeConL0TF(t *testing.T) {
	m, fx := cargarFixtureL0TF(t, "modelo.l0tf")
	b, _ := os.ReadFile("testdata/l0tf/modelo.l0tf")
	var buf bytes.Buffer
	if err := chispa3.Escribir(&buf, []chispa3.Seccion{{Tipo: chispa3.L0TF, Datos: b}}); err != nil {
		t.Fatal(err)
	}
	f, err := chispa3.Desde(buf.Bytes(), chispa3.Limites{})
	if err != nil {
		t.Fatal(err)
	}
	l0 := NuevoL0(4)
	cfg := Config{}
	if _, err := ArmarDesde(f, l0, &cfg, false, nil); err != nil {
		t.Fatal(err)
	}
	if l0.NumModelos() != 1 || l0.modelos[0].tf == nil {
		t.Fatal("debía haber un L0 tfidf")
	}
	r, err := l0.Decidir(context.Background(), Pregunta{Kind: KindChoice, Opciones: opcionesDe(fx.Etiquetas), Estado: fx.Frases[0].Texto})
	if err != nil || r.Conf == 0 || len(r.Probs) != len(m.Etiquetas) {
		t.Fatalf("%+v %v", r, err)
	}
}

func opcionesDe(ids []string) []Opcion {
	var ops []Opcion
	for _, e := range ids {
		ops = append(ops, Opcion{ID: e})
	}
	return ops
}

// modeloGrande arma un L0TF de 150 clases con un vocabulario del tamaño del de clinc150 podado (80 000 n-gramas, f32).
func modeloGrande(tb testing.TB) *chispa3.L0TFModelo {
	rng := rand.New(rand.NewSource(1))
	const v, c = 80000, 150
	set := map[string]bool{}
	letras := []rune("abcdefghijklmnopqrstuvwxyzáéíóúñ ")
	for len(set) < v {
		n := 2 + rng.Intn(4)
		g := make([]rune, n)
		for i := range g {
			g[i] = letras[rng.Intn(len(letras))]
		}
		set[string(g)] = true
	}
	d := &chispa3.DatosL0TF{}
	for g := range set {
		d.Vocab = append(d.Vocab, g)
	}
	sort.Strings(d.Vocab)
	for i := 0; i < c; i++ {
		d.Etiquetas = append(d.Etiquetas, fmt.Sprintf("clase_%03d", i))
		d.Inter = append(d.Inter, float32(rng.NormFloat64()))
	}
	for range d.Vocab {
		d.IDF = append(d.IDF, 1+float32(rng.Float64())*6)
	}
	for i := 0; i < v*c; i++ {
		d.Coef = append(d.Coef, float32(rng.NormFloat64()))
	}
	b, err := chispa3.CodificarL0TF(d)
	if err != nil {
		tb.Fatal(err)
	}
	m, err := chispa3.DecodificarL0TF(b)
	if err != nil {
		tb.Fatal(err)
	}
	return m
}

// BenchmarkL0TF150Clases: una consulta de ~10 palabras contra 80 000 n-gramas × 150 clases.
func BenchmarkL0TF150Clases(b *testing.B) {
	m := modeloGrande(b)
	q := "quiero saber cuándo vence la factura de mi tarjeta de crédito de este mes"
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		m.Probs(q)
	}
}
