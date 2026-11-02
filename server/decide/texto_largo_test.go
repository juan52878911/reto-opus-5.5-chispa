package decide

import (
	"context"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"

	"chispa/format/chispa3"
)

func l1Largo(t *testing.T, tl *TextoLargo) *L1 {
	t.Helper()
	cfg := Config{CacheEsquemas: 16, CacheRespuestas: 16, L1ShrinkageApagado: true, TextoLargo: tl}
	mt, err := ArmarDesde(v3Tiny(t, calibTiny()), NuevoL0(8), &cfg, false, nil)
	if err != nil {
		t.Fatal(err)
	}
	return mt.L1.(*L1)
}

func preguntasL1(estado string) []Pregunta {
	return []Pregunta{
		{Kind: KindChoice, Texto: "¿Qué área?", Opciones: opsReembolso(), Estado: estado},
		{Kind: KindScore, Texto: "¿Qué área?", Opciones: nivelesScore(), Estado: estado},
		{Kind: KindNoul, Texto: "¿Es de envíos?", Opciones: []Opcion{{ID: "true"}, {ID: "false"}}, Estado: estado},
	}
}

// Sin texto_largo, con «cabeza» (con cualquier otro parámetro) y con una estrategia cuando el texto cabe en la ventana, L1 da
// exactamente lo de siempre, también con textos que pasan de max_tokens.
func TestTextoLargoL1NoRegresion(t *testing.T) {
	base := l1Largo(t, nil)
	variantes := map[string]*L1{
		"cabeza":            l1Largo(t, &TextoLargo{Estrategia: "cabeza"}),
		"cabeza con topes":  l1Largo(t, &TextoLargo{Estrategia: "cabeza", Agregacion: "max", Solape: 3, MaxTrozos: 2, VentanaL1: 4}),
		"vacía":             l1Largo(t, &TextoLargo{}),
		"cabeza_cola cabe":  l1Largo(t, &TextoLargo{Estrategia: "cabeza_cola"}),
		"trozos cabe (512)": l1Largo(t, &TextoLargo{Estrategia: "trozos", Agregacion: "max"}),
	}
	for _, estado := range []string{"factura cobro", "paquete retraso envio", "hola gracias", "", strings.Repeat("pedido dinero pago ", 150)} {
		for _, q := range preguntasL1(estado) {
			want, err := base.Decidir(context.Background(), q)
			if err != nil {
				t.Fatal(err)
			}
			for n, l := range variantes {
				got, err := l.Decidir(context.Background(), q)
				if err != nil || !reflect.DeepEqual(got, want) {
					t.Fatalf("%s, %.20q (%s): %+v ≠ %+v (%v)", n, estado, q.Kind, got, want, err)
				}
			}
		}
	}
}

// cabeza_cola con ventana de 4 tokens decide como el texto formado por los 2 primeros y los 2 últimos tokens.
func TestTextoLargoL1CabezaCola(t *testing.T) {
	l := l1Largo(t, &TextoLargo{Estrategia: "cabeza_cola", VentanaL1: 4})
	base := l1Largo(t, nil)
	largo := "factura cobro hola gracias hola gracias pedido envio paquete retraso"
	resumen := "factura cobro paquete retraso"
	for i, q := range preguntasL1(largo) {
		got, _ := l.Decidir(context.Background(), q)
		q.Estado = resumen
		want, _ := base.Decidir(context.Background(), q)
		if !reflect.DeepEqual(got, want) {
			t.Fatalf("%d (%s): %+v ≠ %+v", i, q.Kind, got, want)
		}
		q.Estado = "factura cobro hola gracias" // la cabeza de 4 tokens
		if cab, _ := base.Decidir(context.Background(), q); q.Kind != KindNoul && cab.Conf == want.Conf && reflect.DeepEqual(cab.Probs, want.Probs) {
			t.Fatalf("el caso no distingue la cabeza de cabeza_cola (%s): %+v", q.Kind, cab)
		}
	}
}

// trozos = decidir cada ventana (en bloques de 4 tokens) y agregar las probabilidades: max o media.
func TestTextoLargoL1TrozosAgrega(t *testing.T) {
	base := l1Largo(t, nil)
	trozos := []string{"factura cobro pago dinero", "hola gracias hola gracias", "paquete retraso envio pedido"}
	largo := strings.Join(trozos, " ")
	for _, agg := range []string{"max", "media"} {
		l := l1Largo(t, &TextoLargo{Estrategia: "trozos", Agregacion: agg, VentanaL1: 4})
		for _, q := range preguntasL1(largo) {
			got, err := l.Decidir(context.Background(), q)
			if err != nil {
				t.Fatal(err)
			}
			var rs []Respuesta
			for _, tx := range trozos {
				q.Estado = tx
				r, _ := base.Decidir(context.Background(), q)
				rs = append(rs, r)
			}
			want := agregarRespuestas(q, rs, agg, 0.5)
			if q.Kind == KindNoul {
				want = agregarRespuestas(q, rs, agg, calibTiny().Tipos["noul"].Theta)
			}
			if !reflect.DeepEqual(got, want) {
				t.Fatalf("%s %s: %+v ≠ %+v", agg, q.Kind, got, want)
			}
		}
	}
}

func TestAgregarRespuestas(t *testing.T) {
	p := Pregunta{Kind: KindChoice, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
	rs := []Respuesta{
		{Probs: map[string]float64{"a": 0.9, "b": 0.1}, Answer: "a", Conf: 0.9},
		{Probs: map[string]float64{"a": 0.2, "b": 0.8}, Answer: "b", Conf: 0.8},
	}
	cerca := func(a, b float64) bool { return math.Abs(a-b) < 1e-12 }
	if r := agregarRespuestas(p, rs, "max", 0.5); r.Answer != "a" || !cerca(r.Probs["a"], 0.9/1.7) || !cerca(r.Probs["b"], 0.8/1.7) || !cerca(r.Conf, 0.9/1.7) {
		t.Fatalf("max: %+v", r)
	}
	if r := agregarRespuestas(p, rs, "media", 0.5); r.Answer != "a" && r.Answer != "b" || !cerca(r.Probs["a"], 0.55) || !cerca(r.Probs["b"], 0.45) || r.Answer != "a" {
		t.Fatalf("media: %+v", r)
	}
	rs[1].Probs = map[string]float64{"a": 0.1, "b": 0.9}
	if r := agregarRespuestas(p, rs, "media", 0.5); r.Answer != "a" || !cerca(r.Probs["a"], 0.5) && r.Probs["a"] != 0.5 {
		// 0,5 a 0,5: gana la primera opción (desempate del orden de la pregunta)
		t.Fatalf("empate: %+v", r)
	}
	// noul: true agregado, false = 1−true y θ decide
	pn := Pregunta{Kind: KindNoul, Opciones: []Opcion{{ID: "true"}, {ID: "false"}}}
	ns := []Respuesta{{Probs: map[string]float64{"true": 0.9, "false": 0.1}, Conf: 0.9}, {Probs: map[string]float64{"true": 0.2, "false": 0.8}, Conf: 0.8}}
	if r := agregarRespuestas(pn, ns, "max", 0.5); r.Answer != "true" || !cerca(r.Probs["true"], 0.9) || !cerca(r.Conf, 0.9) {
		t.Fatalf("noul max: %+v", r)
	}
	if r := agregarRespuestas(pn, ns, "media", 0.6); r.Answer != "false" || !cerca(r.Probs["true"], 0.55) || !cerca(r.Conf, 0.45) {
		t.Fatalf("noul media θ=0,6: %+v", r)
	}
	// score: la mediana de la distribución agregada
	ps := Pregunta{Kind: KindScore, Opciones: []Opcion{{ID: "1"}, {ID: "2"}, {ID: "3"}}}
	ss := []Respuesta{{Probs: map[string]float64{"1": 0.7, "2": 0.2, "3": 0.1}, Conf: 0.7}, {Probs: map[string]float64{"1": 0.1, "2": 0.2, "3": 0.7}, Conf: 0.7}}
	if r := agregarRespuestas(ps, ss, "media", 0.5); r.Answer != "2" || !cerca(r.Conf, 0.2) {
		t.Fatalf("score media: %+v", r)
	}
	// sin opinión o una sola ventana: la primera, sin tocar
	if r := agregarRespuestas(p, []Respuesta{{}, rs[0]}, "max", 0.5); !reflect.DeepEqual(r, Respuesta{}) {
		t.Fatalf("sin opinión: %+v", r)
	}
	if got := agregarSims([][]float64{{1, 5}, {3, 1}}, "max"); !reflect.DeepEqual(got, []float64{3, 5}) {
		t.Fatalf("sims max %v", got)
	}
	if got := agregarSims([][]float64{{1, 5}, {3, 1}}, "media"); !reflect.DeepEqual(got, []float64{2, 3}) {
		t.Fatalf("sims media %v", got)
	}
}

func TestTextoLargoL1Metricas(t *testing.T) {
	m := NuevasMetricas()
	l := l1Largo(t, &TextoLargo{Estrategia: "trozos", VentanaL1: 4})
	l.UsaMetricas(m)
	q := preguntasL1("factura cobro")[0]
	l.Decidir(context.Background(), q) // cabe: no cuenta
	q.Estado = "factura cobro pago dinero reembolso envio paquete"
	l.Decidir(context.Background(), q)
	if m.TextoLargoL1.Load() != 1 || m.TrozosL1.Load() != 2 {
		t.Fatalf("L1: %d textos largos, %d trozos", m.TextoLargoL1.Load(), m.TrozosL1.Load())
	}
	var sb strings.Builder
	m.Escribe(&sb)
	if !strings.Contains(sb.String(), `chispa_texto_largo_total{capa="L1"} 1`) {
		t.Fatalf("falta la métrica:\n%s", sb.String())
	}
}

func TestConfigTextoLargo(t *testing.T) {
	d := t.TempDir()
	cargar := func(js string) error {
		f := filepath.Join(d, "c.json")
		os.WriteFile(f, []byte(js), 0o600)
		_, err := CargarConfig(f)
		return err
	}
	if err := cargar(`{"texto_largo":{"estrategia":"trozos","agregacion":"max","solape":16,"max_trozos":4}}`); err != nil {
		t.Fatal(err)
	}
	for _, malo := range []string{`{"texto_largo":{"estrategia":"mitad"}}`, `{"texto_largo":{"agregacion":"min"}}`, `{"texto_largo":{"solape":-1}}`,
		`{"texto_largo":{"max_trozos":1000}}`, `{"texto_largo":{"trozos":3}}`} {
		if cargar(malo) == nil {
			t.Fatalf("%s debería fallar", malo)
		}
	}
	var c Config
	json.Unmarshal([]byte(`{}`), &c)
	if c.TextoLargo != nil {
		t.Fatal("ausente debe ser nil")
	}
}

// --- L2 ---

// sesionMarca devuelve S = {1,0} (la opción «a») si algún id es la marca y S = {0,0} (sin opinión) si no; apunta los ids.
type sesionMarca struct {
	marca    int64
	vistos   *[][]int64
	llamadas *atomic.Int32
}

func (s sesionMarca) Ranuras(ids []int64) ([][]float32, error) {
	*s.vistos = append(*s.vistos, ids)
	s.llamadas.Add(1)
	for _, id := range ids {
		if id == s.marca {
			return [][]float32{{1, 0}}, nil
		}
	}
	return [][]float32{{0, 0}}, nil
}

func l2Largo(t *testing.T, tl *TextoLargo, maxLen string) (*L2, *[][]int64, *Metricas, int64) {
	t.Helper()
	tk := tokE5Real(t)
	ids := tk.Tokenizar("zqxjvk")
	marca := int64(ids[len(ids)-2]) // la última pieza de una palabra rara
	var vistos [][]int64
	var n atomic.Int32
	met := NuevasMetricas()
	onnx := "l2_sintetico.onnx"
	if maxLen != "" {
		onnx = maxLen
	}
	mt, err := ArmarDesde(ficheroL2(t, leerTestdata(t, onnx), 0), NuevoL0(8), &Config{CacheEsquemas: 8, TextoLargo: tl}, false,
		NuevoTokenizadorE5(tk), ConSesionS(sesionMarca{marca, &vistos, &n}))
	if err != nil {
		t.Fatal(err)
	}
	l2 := mt.L2.(*L2)
	l2.UsaMetricas(met)
	return l2, &vistos, met, marca
}

func preguntaL2(estado string) Pregunta {
	return Pregunta{ID: "q", Texto: "¿q?", Kind: KindChoice, Estado: estado, Opciones: []Opcion{{ID: "a"}, {ID: "b"}}}
}

// La señal está solo al final de un texto largo: la cabeza no la ve (S sin opinión: 0,5/0,5, escala), cabeza_cola y trozos sí.
func TestTextoLargoL2SenalAlFinal(t *testing.T) {
	relleno := strings.Repeat("palabra · ", 500)
	estado := relleno + "zqxjvk"
	for _, c := range []struct {
		nombre string
		tl     *TextoLargo
		decide bool
	}{
		{"sin config", nil, false}, {"cabeza", &TextoLargo{Estrategia: "cabeza"}, false},
		{"cabeza_cola", &TextoLargo{Estrategia: "cabeza_cola"}, true},
		{"trozos max", &TextoLargo{Estrategia: "trozos", Agregacion: "max", MaxTrozos: 64}, true},
		{"trozos media", &TextoLargo{Estrategia: "trozos", Agregacion: "media", MaxTrozos: 64}, true},
	} {
		l2, _, _, _ := l2Largo(t, c.tl, "")
		r, err := l2.Decidir(context.Background(), preguntaL2(estado))
		if err != nil {
			t.Fatalf("%s: %v", c.nombre, err)
		}
		if c.decide != (r.Answer == "a" && r.Conf > 0.5) {
			t.Fatalf("%s: %+v", c.nombre, r)
		}
	}
}

// Los ids que recibe el ONNX con «cabeza» (y sin config) son los de siempre, bit a bit; las ventanas respetan max_len y el tope
// de trozos; los textos largos se cuentan.
func TestTextoLargoL2IdsTopeYMetrica(t *testing.T) {
	tk := tokE5Real(t)
	largo := strings.Repeat("palabra · ", 900)
	for _, tl := range []*TextoLargo{nil, {Estrategia: "cabeza", Solape: 5, MaxTrozos: 3}} {
		l2, vistos, met, _ := l2Largo(t, tl, "")
		l2.Decidir(context.Background(), preguntaL2(largo))
		l2.Decidir(context.Background(), preguntaL2("hola"))
		want := NuevoTokenizadorE5(tk).IDs(largo)
		if len(*vistos) != 2 || !reflect.DeepEqual((*vistos)[0], want) || len((*vistos)[0]) != 128 {
			t.Fatalf("cabeza distinta de IDs: %d ventanas, %d ids", len(*vistos), len((*vistos)[0]))
		}
		if met.TextoLargoL2.Load() != 1 || met.TrozosL2.Load() != 1 {
			t.Fatalf("métricas: %d, %d", met.TextoLargoL2.Load(), met.TrozosL2.Load())
		}
	}
	l2, vistos, met, _ := l2Largo(t, &TextoLargo{Estrategia: "trozos", Solape: 8, MaxTrozos: 3}, "")
	l2.Decidir(context.Background(), preguntaL2(largo))
	if len(*vistos) != 3 || met.TrozosL2.Load() != 3 || met.TextoLargoL2.Load() != 1 {
		t.Fatalf("tope de trozos: %d ventanas, métricas %d/%d", len(*vistos), met.TextoLargoL2.Load(), met.TrozosL2.Load())
	}
	for i, ids := range *vistos {
		if len(ids) != 128 || ids[0] != 0 || ids[len(ids)-1] != 2 {
			t.Fatalf("ventana %d: %d ids", i, len(ids))
		}
	}
	if !reflect.DeepEqual((*vistos)[0], NuevoTokenizadorE5(tk).IDs(largo)) {
		t.Fatal("la primera ventana debe ser la cabeza")
	}
	// con max_len 256 del ONNX las ventanas son de 256
	l2, vistos, _, _ = l2Largo(t, &TextoLargo{Estrategia: "trozos", MaxTrozos: 2}, "l2_sintetico_ml256.onnx")
	l2.Decidir(context.Background(), preguntaL2(largo))
	if len(*vistos) != 2 || len((*vistos)[1]) != 256 {
		t.Fatalf("max_len 256: %d ventanas de %d", len(*vistos), len((*vistos)[len(*vistos)-1]))
	}
}

// ventanasFalsas es una fuente de similitudes con varias ventanas (lo que da L2 con trozos).
type ventanasFalsas struct{ vs []ventana }

func (v ventanasFalsas) Similitudes(context.Context, Pregunta) ([][]float32, []float64, bool, error) {
	return v.vs[0].S, v.vs[0].sims, true, nil
}

func (v ventanasFalsas) similitudesVentanas(context.Context, Pregunta) ([]ventana, []torreDin, bool, error) {
	return v.vs, nil, true, nil
}

// L2c con trozos: la cabeza conjunta decide cada ventana con las mismas probabilidades de L0 y se agregan; con una ventana es lo de siempre.
func TestTextoLargoL2cAgregaVentanas(t *testing.T) {
	exacto(t)
	fx, conj, p := leerFixtureConj(t)
	c0, c1 := fx.Casos[0], fx.Casos[1]
	esq, _ := chispa3.DecodificarEsquemas(mustEsq(t))
	mk := func(agg string, vs ...ventana) *L2c {
		base := NuevoL2Con(sesionFalsa{c0.S}, esq, chispa3.Calib{}, tokFalso{}).ConTextoLargo(TextoLargo{Estrategia: "trozos", Agregacion: agg})
		return NuevoL2cCon(base, ventanasFalsas{vs}, conj)
	}
	v0, v1 := ventana{c0.S, c0.Sims}, ventana{c1.S, c1.Sims}
	ctx := context.Background()
	solo, err := mk("media", v0).DecidirCon(ctx, p, conL0(c0.L0))
	if err != nil || solo.Conf == 0 {
		t.Fatalf("%+v %v", solo, err)
	}
	r0 := solo
	r1, _ := mk("media", v1).DecidirCon(ctx, p, conL0(c0.L0))
	for _, agg := range []string{"max", "media"} {
		got, err := mk(agg, v0, v1).DecidirCon(ctx, p, conL0(c0.L0))
		if err != nil {
			t.Fatal(err)
		}
		want := agregarRespuestas(p, []Respuesta{r0, r1}, agg, 0.5)
		want.EsquemaNuevo = got.EsquemaNuevo // lo pone marcarNuevo (esta ESQUEMAS no trae las torres del fixture)
		if got.Answer != want.Answer || math.Abs(got.Conf-want.Conf) > 1e-9 {
			t.Fatalf("%s: %+v ≠ %+v", agg, got, want)
		}
		for id, p := range want.Probs {
			if math.Abs(got.Probs[id]-p) > 1e-9 {
				t.Fatalf("%s %s: %v ≠ %v", agg, id, got.Probs[id], p)
			}
		}
	}
}
