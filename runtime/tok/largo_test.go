package tok

import (
	"slices"
	"strings"
	"testing"
)

func seq(n int) []int32 {
	s := make([]int32, n)
	for i := range s {
		s[i] = int32(i + 10)
	}
	return s
}

func TestTrocearCabeza(t *testing.T) {
	c := seq(20)
	for _, tl := range []TextoLargo{{}, {Estrategia: EstCabeza}, {Estrategia: EstCabeza, Solape: 3, MaxTrozos: 2}} {
		v := Trocear(c, 8, tl)
		if len(v) != 1 || !slices.Equal(v[0], c[:8]) {
			t.Fatalf("%+v: %v", tl, v)
		}
	}
}

func TestTrocearQueCabeIgualEnTodas(t *testing.T) {
	c := seq(8)
	for _, e := range []string{EstCabeza, EstCabezaCola, EstTrozos} {
		v := Trocear(c, 8, TextoLargo{Estrategia: e})
		if len(v) != 1 || !slices.Equal(v[0], c) {
			t.Fatalf("%s: %v", e, v)
		}
	}
}

func TestTrocearCabezaCola(t *testing.T) {
	c := seq(30)
	v := Trocear(c, 8, TextoLargo{Estrategia: EstCabezaCola})
	want := append(slices.Clone(c[:4]), c[26:]...)
	if len(v) != 1 || !slices.Equal(v[0], want) {
		t.Fatalf("got %v want %v", v, want)
	}
	v = Trocear(c, 7, TextoLargo{Estrategia: EstCabezaCola}) // impar: 3 + 4
	if want := append(slices.Clone(c[:3]), c[26:]...); !slices.Equal(v[0], want) {
		t.Fatalf("impar: %v", v[0])
	}
}

func TestTrocearTrozos(t *testing.T) {
	c := seq(20)
	v := Trocear(c, 8, TextoLargo{Estrategia: EstTrozos})
	if len(v) != 3 || !slices.Equal(v[0], c[:8]) || !slices.Equal(v[1], c[8:16]) || !slices.Equal(v[2], c[16:]) {
		t.Fatalf("sin solape: %v", v)
	}
	v = Trocear(c, 8, TextoLargo{Estrategia: EstTrozos, Solape: 4})
	if len(v) != 4 || !slices.Equal(v[1], c[4:12]) || !slices.Equal(v[3], c[12:20]) {
		t.Fatalf("solape 4: %v", v)
	}
	v = Trocear(c, 8, TextoLargo{Estrategia: EstTrozos, MaxTrozos: 2})
	if len(v) != 2 {
		t.Fatalf("tope de trozos: %d", len(v))
	}
	if v = Trocear(c, 8, TextoLargo{Estrategia: EstTrozos, Solape: 99}); len(v) != 8 { // solape acotado a n−1: paso 1, tope 8
		t.Fatalf("solape enorme: %d trozos", len(v))
	}
}

func TestTextoLargoValidar(t *testing.T) {
	malos := []TextoLargo{{Estrategia: "x"}, {Agregacion: "min"}, {Solape: -1}, {MaxTrozos: TopeMaxTrozos + 1}, {VentanaL1: 2}}
	for _, m := range malos {
		if m.Validar() == nil {
			t.Errorf("%+v debería fallar", m)
		}
	}
	if err := (TextoLargo{Estrategia: EstTrozos, Agregacion: AggMax, Solape: 2, MaxTrozos: 4}).Validar(); err != nil {
		t.Fatal(err)
	}
}

func TestVentanasCabezaIgualQueTokenizarMax(t *testing.T) {
	tk := abrir(t)
	textos := []string{"hola", strings.Repeat("quiero cambiar mi plan de datos ", 60)}
	for _, tx := range textos {
		for _, tl := range []TextoLargo{{}, {Estrategia: EstCabeza}} {
			v, largo := tk.Ventanas(Prefijo, tx, 32, tl)
			if len(v) != 1 || !slices.Equal(v[0], tk.TokenizarMax(Prefijo, tx, 32)) {
				t.Fatalf("cabeza distinta de TokenizarMax para %q", tx[:4])
			}
			if largo != (len(tx) > 100) {
				t.Fatalf("largo=%v para %d bytes", largo, len(tx))
			}
		}
	}
}

func TestVentanasEstrategias(t *testing.T) {
	tk := abrir(t)
	tx := strings.Repeat("uno dos tres cuatro cinco seis ", 40) + "factura"
	cab := tk.TokenizarMax(Prefijo, tx, 32)
	// cabeza_cola: <s>, la mitad de la cabeza, la mitad de la cola, </s>
	v, largo := tk.Ventanas(Prefijo, tx, 32, TextoLargo{Estrategia: EstCabezaCola})
	if !largo || len(v) != 1 || len(v[0]) != 32 {
		t.Fatalf("cabeza_cola: largo=%v %v", largo, v)
	}
	todo := tk.m.TokenizarSinTope(Prefijo+tx, 0)
	want := append(append([]int32{0}, todo[:15]...), todo[len(todo)-15:]...)
	want = append(want, 2)
	if !slices.Equal(v[0], want) {
		t.Fatalf("cabeza_cola: %v quería %v", v[0], want)
	}
	if slices.Equal(v[0], cab) {
		t.Fatal("cabeza_cola igual que la cabeza")
	}
	// trozos: cada ventana lleva <s>, el prefijo y </s>; la primera es la cabeza
	z, _ := tk.Ventanas(Prefijo, tx, 32, TextoLargo{Estrategia: EstTrozos, Solape: 4, MaxTrozos: 50})
	if len(z) < 3 || !slices.Equal(z[0], cab) {
		t.Fatalf("trozos: %d ventanas", len(z))
	}
	pre := tk.m.TokenizarSinTope(Prefijo, 0)
	for i, w := range z {
		if len(w) > 32 || w[0] != 0 || w[len(w)-1] != 2 || (i > 0 && !slices.Equal(w[1:1+len(pre)], pre)) {
			t.Fatalf("ventana %d mal formada: %v", i, w)
		}
	}
	// un texto que cabe es la misma ventana en todas
	for _, e := range []string{EstCabezaCola, EstTrozos} {
		v, largo := tk.Ventanas(Prefijo, "hola", 32, TextoLargo{Estrategia: e})
		if largo || len(v) != 1 || !slices.Equal(v[0], tk.TokenizarMax(Prefijo, "hola", 32)) {
			t.Fatalf("%s con texto corto", e)
		}
	}
}

func TestAgregarProbs(t *testing.T) {
	ids := []string{"a", "b"}
	ps := []map[string]float64{{"a": 0.9, "b": 0.1}, {"a": 0.2, "b": 0.8}}
	cerca := func(a, b float64) bool { return a-b < 1e-12 && b-a < 1e-12 }
	p, ans, conf, ok := AgregarProbs("choice", ids, ps, AggMax, 0.5)
	if !ok || ans != "a" || !cerca(p["a"], 0.9/1.7) || !cerca(p["b"], 0.8/1.7) || !cerca(conf, 0.9/1.7) {
		t.Fatalf("max: %v %s %v", p, ans, conf)
	}
	p, ans, conf, _ = AgregarProbs("choice", ids, ps, AggMedia, 0.5)
	if ans != "a" || !cerca(p["a"], 0.55) || !cerca(conf, 0.55) {
		t.Fatalf("media: %v %s %v", p, ans, conf)
	}
	nu := []map[string]float64{{"true": 0.9, "false": 0.1}, {"true": 0.2, "false": 0.8}}
	if p, ans, conf, _ = AgregarProbs("noul", []string{"true", "false"}, nu, AggMedia, 0.6); ans != "false" || !cerca(p["true"], 0.55) || !cerca(conf, 0.45) {
		t.Fatalf("noul: %v %s %v", p, ans, conf)
	}
	sc := []map[string]float64{{"1": 0.7, "2": 0.2, "3": 0.1}, {"1": 0.1, "2": 0.2, "3": 0.7}}
	if _, ans, conf, _ = AgregarProbs("score", []string{"1", "2", "3"}, sc, AggMedia, 0.5); ans != "2" || !cerca(conf, 0.2) {
		t.Fatalf("score: %s %v", ans, conf)
	}
	if _, _, _, ok = AgregarProbs("choice", ids, nil, AggMax, 0.5); ok {
		t.Fatal("sin ventanas no hay nada que agregar")
	}
	if got := AgregarSims([][]float64{{1, 5}, {3, 1}}, AggMax); got[0] != 3 || got[1] != 5 {
		t.Fatal(got)
	}
	if got := AgregarSims([][]float64{{1, 5}, {3, 1}}, AggMedia); got[0] != 2 || got[1] != 3 {
		t.Fatal(got)
	}
}
